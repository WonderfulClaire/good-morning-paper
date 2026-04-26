from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from urllib.parse import quote_plus

import requests

from src.models import Paper

logger = logging.getLogger(__name__)

BASE_URL = "http://export.arxiv.org/api/query"


def search_arxiv(query: str, max_results: int, days_back: int) -> list[Paper]:
    cutoff = date.today() - timedelta(days=days_back)
    params = {
        "search_query": f"all:{quote_plus(query)}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    try:
        resp = requests.get(BASE_URL, params=params, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except (requests.RequestException, ET.ParseError) as exc:
        logger.warning("arXiv query failed: %s", exc)
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    papers: list[Paper] = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").replace("\n", " ").strip()
        abstract = (entry.findtext("atom:summary", default="", namespaces=ns) or "").replace("\n", " ").strip()
        updated = entry.findtext("atom:updated", default="", namespaces=ns)
        pub_date = None
        if updated:
            try:
                pub_date = datetime.strptime(updated[:10], "%Y-%m-%d").date()
            except ValueError:
                pub_date = None

        if pub_date and pub_date < cutoff:
            continue

        links = entry.findall("atom:link", ns)
        paper_url = ""
        for link in links:
            href = link.attrib.get("href", "")
            if href and "abs" in href:
                paper_url = href
                break

        authors = [
            a.findtext("atom:name", default="", namespaces=ns)
            for a in entry.findall("atom:author", ns)
            if a.findtext("atom:name", default="", namespaces=ns)
        ]

        papers.append(
            Paper(
                source="arxiv",
                title=title,
                abstract=abstract,
                authors=authors,
                venue="arXiv",
                year=pub_date.year if pub_date else None,
                published_date=pub_date,
                url=paper_url,
                arxiv_url=paper_url,
            )
        )
    return papers
