from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta

import requests

from src.models import Paper

logger = logging.getLogger(__name__)

API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


def search_semantic_scholar(
    query: str,
    max_results: int,
    days_back: int,
    api_key: str | None = None,
) -> list[Paper]:
    fields = "title,abstract,authors,venue,year,url,externalIds,publicationDate"
    cutoff = date.today() - timedelta(days=days_back)
    headers = {"x-api-key": api_key} if api_key else {}
    params = {"query": query, "limit": max_results, "fields": fields}

    data = []
    for attempt in range(3):
        try:
            resp = requests.get(API_URL, params=params, headers=headers, timeout=20)
            if resp.status_code == 429:
                wait_seconds = 1 + attempt * 2
                logger.warning("Semantic Scholar rate-limited (429). Retry in %ss (attempt %s/3).", wait_seconds, attempt + 1)
                time.sleep(wait_seconds)
                continue
            resp.raise_for_status()
            data = resp.json().get("data", [])
            break
        except requests.RequestException as exc:
            logger.warning("Semantic Scholar query failed: %s", exc)
            return []
    if not data:
        logger.warning("Semantic Scholar returned no data for query after retries: %s", query)
        return []

    papers: list[Paper] = []
    for item in data:
        pub_date = None
        date_str = item.get("publicationDate")
        if date_str:
            try:
                pub_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pub_date = None

        if pub_date and pub_date < cutoff:
            continue

        ext = item.get("externalIds") or {}
        authors = [a.get("name", "") for a in item.get("authors", []) if a.get("name")]
        papers.append(
            Paper(
                source="semantic_scholar",
                title=item.get("title", ""),
                abstract=item.get("abstract") or "",
                authors=authors,
                venue=item.get("venue") or "",
                year=item.get("year"),
                published_date=pub_date,
                url=item.get("url") or "",
                arxiv_url=f"https://arxiv.org/abs/{ext.get('ArXiv')}" if ext.get("ArXiv") else None,
                doi=ext.get("DOI"),
            )
        )
    return papers
