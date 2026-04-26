from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from urllib.parse import quote_plus

import requests

from src.models import Paper

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openalex.org/works"


def _abstract_from_inverted_index(index: dict | None) -> str:
    if not index:
        return ""
    pos_to_word: dict[int, str] = {}
    for word, positions in index.items():
        for p in positions:
            pos_to_word[p] = word
    return " ".join(pos_to_word[p] for p in sorted(pos_to_word.keys()))


def search_openalex(query: str, max_results: int, days_back: int) -> list[Paper]:
    cutoff = date.today() - timedelta(days=days_back)
    params = {
        "search": query,
        "per-page": max_results,
        "sort": "publication_date:desc",
        "select": "display_name,abstract_inverted_index,publication_year,publication_date,primary_location,authorships,doi,ids",
    }
    try:
        resp = requests.get(BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except requests.RequestException as exc:
        logger.warning("OpenAlex query failed: %s", exc)
        return []

    papers: list[Paper] = []
    for item in results:
        pub_date = None
        if item.get("publication_date"):
            try:
                pub_date = datetime.strptime(item["publication_date"], "%Y-%m-%d").date()
            except ValueError:
                pub_date = None

        if pub_date and pub_date < cutoff:
            continue

        primary_loc = item.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        landing = primary_loc.get("landing_page_url") or ""
        venue = source.get("display_name") or ""
        authors = [a.get("author", {}).get("display_name", "") for a in item.get("authorships", [])]
        ids = item.get("ids") or {}
        arxiv_id = ids.get("arxiv")
        arxiv_url = None
        if arxiv_id:
            arxiv_url = f"https://arxiv.org/abs/{quote_plus(arxiv_id.split('/')[-1])}"

        papers.append(
            Paper(
                source="openalex",
                title=item.get("display_name") or "",
                abstract=_abstract_from_inverted_index(item.get("abstract_inverted_index")),
                authors=[a for a in authors if a],
                venue=venue,
                year=item.get("publication_year"),
                published_date=pub_date,
                url=landing,
                arxiv_url=arxiv_url,
                doi=item.get("doi"),
            )
        )
    return papers
