from __future__ import annotations

import argparse
import logging
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from src.config_loader import load_config
from src.generate_digest import generate_digest, render_markdown
from src.rank_papers import rank_papers
from src.seed_loader import load_seed_papers
from src.search_arxiv import search_arxiv
from src.search_openalex import search_openalex
from src.search_semantic_scholar import search_semantic_scholar
from src.send_email import send_email_if_configured
from src.weekly_summary import build_weekly_summary

QUERY_VARIANTS = [
    "multi-channel speech enhancement",
    "multichannel speech enhancement",
    "microphone array speech enhancement",
    "neural beamforming",
    "MVDR speech enhancement",
    "GEV speech enhancement",
    "relative transfer function speech enhancement",
    "RTF speech enhancement",
    "deep spatial filtering",
    "speech dereverberation microphone array",
    "audio-visual speech enhancement",
    "hearing aid speech enhancement beamforming",
]


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def build_query(config: dict) -> str:
    topics = config["user_profile"]["focus_topics"]
    return " ".join(topics[:8])


def save_digest(markdown: str) -> Path:
    out_dir = Path("digests")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date.today()}.md"
    out_path.write_text(markdown, encoding="utf-8")
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily paper digest bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print selection and digest preview; do not save markdown or send email.",
    )
    parser.add_argument(
        "--weekly-summary",
        action="store_true",
        help="Generate a weekly summary from recent digest markdown files.",
    )
    return parser.parse_args()


def _log_selected_paper(logger: logging.Logger, top_paper) -> None:
    if not top_paper:
        logger.info("Selected paper title: N/A")
        logger.info("Selected paper source: N/A")
        logger.info("Selected paper relevance score: 0.000")
        return
    logger.info("Selected paper title: %s", top_paper.title)
    logger.info("Selected paper source: %s", top_paper.source)
    logger.info("Selected paper relevance score: %.3f", top_paper.score)


def _dedupe_papers(papers: list) -> list:
    unique = {}
    for p in papers:
        key = (p.title.strip().lower(), (p.year or 0))
        if key not in unique:
            unique[key] = p
    return list(unique.values())


def _filter_from_year(papers: list, year_from: int) -> list:
    filtered = []
    for p in papers:
        if p.year and p.year >= year_from:
            filtered.append(p)
            continue
        if p.published_date and p.published_date.year >= year_from:
            filtered.append(p)
    return filtered


def _search_all_sources(query_variants: list[str], max_results_each: int, days_back: int, ss_key: str | None) -> tuple[list, dict]:
    all_papers = []
    counts = {"semantic_scholar": 0, "openalex": 0, "arxiv": 0}
    for q in query_variants:
        ss = search_semantic_scholar(q, max_results_each, days_back, api_key=ss_key)
        oa = search_openalex(q, max_results_each, days_back)
        ax = search_arxiv(q, max_results_each, days_back)
        counts["semantic_scholar"] += len(ss)
        counts["openalex"] += len(oa)
        counts["arxiv"] += len(ax)
        all_papers.extend(ss + oa + ax)
    return all_papers, counts


def main() -> None:
    setup_logging()
    logger = logging.getLogger("main")
    args = parse_args()

    load_dotenv()
    if args.weekly_summary:
        weekly_path = build_weekly_summary(days=7)
        if weekly_path:
            logger.info("Output markdown path: %s", weekly_path)
        else:
            logger.info("Output markdown path: (weekly summary not created)")
        logger.info("Email status: skipped (weekly-summary)")
        return

    config = load_config("config.yaml")
    days_back = int(config["search"]["days_back"])
    max_per_source = int(config["search"]["max_results_per_source"])
    max_total = int(config["search"]["max_candidates_total"])

    logger.info("Running paper digest pipeline with %s query variants.", len(QUERY_VARIANTS))
    ss_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    per_query_limit = max(2, max_per_source // max(len(QUERY_VARIANTS), 1))
    diagnostics: dict[str, str] = {}

    fallback_levels = [
        ("recent_days", days_back, None),
        ("30_days", 30, None),
        ("180_days", 180, None),
        ("year_2023_plus", 3650, 2023),
    ]

    selected_candidates = []
    source_counts = {"semantic_scholar": 0, "openalex": 0, "arxiv": 0}
    used_level = "none"
    for level_name, window, year_floor in fallback_levels:
        logger.info("Search fallback level: %s", level_name)
        papers, counts = _search_all_sources(QUERY_VARIANTS, per_query_limit, window, ss_key)
        deduped = _dedupe_papers(papers)
        if year_floor:
            deduped = _filter_from_year(deduped, year_floor)

        logger.info("Candidates from Semantic Scholar: %s", counts["semantic_scholar"])
        logger.info("Candidates from OpenAlex: %s", counts["openalex"])
        logger.info("Candidates from arXiv: %s", counts["arxiv"])
        logger.info("Candidates after deduplication: %s", len(deduped))

        if deduped:
            selected_candidates = deduped
            source_counts = counts
            used_level = level_name
            break

    seed_papers = load_seed_papers("seed_papers.yaml")
    seed_file_exists = Path("seed_papers.yaml").exists()
    if not seed_papers and not seed_file_exists:
        logger.info("No seed papers loaded. Falling back to keyword-only ranking.")
    elif not seed_papers and seed_file_exists:
        logger.warning("seed_papers.yaml exists but no valid seed papers were loaded.")
    else:
        logger.info("Loaded %s seed papers for personalized ranking.", len(seed_papers))

    ranked = rank_papers(selected_candidates[:max_total], config, seed_papers=seed_papers)
    for idx, p in enumerate(ranked[:5], start=1):
        logger.info("Top %s: %.3f | %s", idx, p.score, p.title)
    top_paper = ranked[0] if ranked else None

    diagnostics = {
        "fallback_level": used_level,
        "semantic_scholar_count": str(source_counts["semantic_scholar"]),
        "openalex_count": str(source_counts["openalex"]),
        "arxiv_count": str(source_counts["arxiv"]),
        "deduped_count": str(len(selected_candidates)),
        "top_candidates": "; ".join([f"{p.score:.3f}:{p.title}" for p in ranked[:5]]) or "N/A",
    }
    digest = generate_digest(top_paper, diagnostics=diagnostics)
    markdown = render_markdown(digest)
    _log_selected_paper(logger, top_paper)

    if args.dry_run:
        logger.info("Dry-run mode enabled: markdown file will not be saved and email will not be sent.")
        preview = markdown[:800] + ("..." if len(markdown) > 800 else "")
        logger.info("Digest preview:\n%s", preview)
        logger.info("Output markdown path: (dry-run not saved)")
        logger.info("Email status: skipped (dry-run)")
        return

    output_path = save_digest(markdown)
    logger.info("Output markdown path: %s", output_path)

    sent = send_email_if_configured(subject=f"每日论文速递 {date.today()}", body_markdown=markdown)
    if sent:
        logger.info("Email status: sent")
    else:
        logger.info("Email status: skipped")


if __name__ == "__main__":
    main()
