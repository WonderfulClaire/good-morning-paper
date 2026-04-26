from __future__ import annotations

from datetime import date

from src.models import Paper, SeedPaper


def _contains_any(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for t in terms if t.lower() in lowered)


def _venue_score(venue: str, high_priority_venues: list[str]) -> float:
    if not venue:
        return 0.0
    venue_l = venue.lower()
    return 1.0 if any(v.lower() in venue_l for v in high_priority_venues) else 0.0


def _recency_score(published_date: date | None, year: int | None) -> float:
    if published_date:
        days_old = max((date.today() - published_date).days, 0)
        return max(0.0, 1.0 - min(days_old / 365.0, 1.0))
    if year:
        return max(0.0, 1.0 - min((date.today().year - year) / 5.0, 1.0))
    return 0.2


def _tokenize(text: str) -> set[str]:
    return {t for t in text.lower().replace("/", " ").replace("-", " ").split() if len(t) >= 3}


def _seed_similarity(candidate: Paper, seeds: list[SeedPaper]) -> float:
    if not seeds:
        return 0.0
    cand_tokens = _tokenize(f"{candidate.title} {candidate.abstract}")
    if not cand_tokens:
        return 0.0
    best = 0.0
    for seed in seeds:
        seed_text = f"{seed.title} {seed.abstract} {seed.notes} {' '.join(seed.authors)}"
        seed_tokens = _tokenize(seed_text)
        if not seed_tokens:
            continue
        overlap = len(cand_tokens & seed_tokens) / len(seed_tokens)
        best = max(best, overlap)
    return min(best, 1.0)


def rank_papers(papers: list[Paper], config: dict, seed_papers: list[SeedPaper] | None = None) -> list[Paper]:
    profile = config["user_profile"]
    ranking = config["ranking"]
    weights = ranking["weights"]

    topics = profile["focus_topics"]
    frontier = profile.get("frontier_topics", [])
    venues = config["venues"]["high_priority"]
    seeds = seed_papers or []
    seed_weight = weights.get("seed_similarity", 0.0)

    for p in papers:
        text = f"{p.title} {p.abstract}"
        keyword_hits = _contains_any(text, topics)
        frontier_hits = _contains_any(text, frontier)
        title_hits = _contains_any(p.title, topics)
        abstract_hits = _contains_any(p.abstract, topics)

        keyword_match = min(keyword_hits / max(len(topics) / 3, 1), 1.0)
        venue_priority = _venue_score(p.venue, venues)
        recency = _recency_score(p.published_date, p.year)
        title_abstract_relevance = min((title_hits * 2 + abstract_hits) / 8.0, 1.0)
        frontier_bonus = min(frontier_hits / 2.0, 1.0)
        seed_score = _seed_similarity(p, seeds)

        p.score = (
            keyword_match * weights["keyword_match"]
            + venue_priority * weights["venue_priority"]
            + recency * weights["recency"]
            + title_abstract_relevance * weights["title_abstract_relevance"]
            + frontier_bonus * weights["frontier_bonus"]
            + seed_score * seed_weight
        )
        p.relevance_reason = (
            f"关键词命中 {keyword_hits}，优先会议/期刊分 {venue_priority:.1f}，"
            f"新近性分 {recency:.2f}，前沿加分 {frontier_bonus:.2f}，种子论文相似度 {seed_score:.2f}"
        )

    return sorted(papers, key=lambda x: x.score, reverse=True)
