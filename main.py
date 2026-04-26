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
    query = build_query(config)
    days_back = int(config["search"]["days_back"])
    max_per_source = int(config["search"]["max_results_per_source"])
    max_total = int(config["search"]["max_candidates_total"])

    logger.info("Running paper digest pipeline with query: %s", query)

    papers = []
    ss_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    papers.extend(search_semantic_scholar(query, max_per_source, days_back, api_key=ss_key))
    papers.extend(search_openalex(query, max_per_source, days_back))
    papers.extend(search_arxiv(query, max_per_source, days_back))

    unique = {}
    for p in papers:
        key = (p.title.strip().lower(), (p.year or 0))
        if key not in unique:
            unique[key] = p

    seed_papers = load_seed_papers("seed_papers.yaml")
    if not seed_papers:
        logger.info("No seed papers loaded. Falling back to keyword-only ranking.")
    else:
        logger.info("Loaded %s seed papers for personalized ranking.", len(seed_papers))

    ranked = rank_papers(list(unique.values())[:max_total], config, seed_papers=seed_papers)
    top_paper = ranked[0] if ranked else None

    digest = generate_digest(top_paper)
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
