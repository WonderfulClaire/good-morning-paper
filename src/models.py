from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class Paper(BaseModel):
    source: str
    title: str
    abstract: str = ""
    authors: list[str] = Field(default_factory=list)
    venue: str = ""
    year: Optional[int] = None
    published_date: Optional[date] = None
    url: str
    arxiv_url: Optional[str] = None
    doi: Optional[str] = None
    relevance_reason: str = ""
    score: float = 0.0


class SeedPaper(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    venue: str = ""
    year: Optional[int] = None
    abstract: str = ""
    url: str = ""
    notes: str = ""


class DigestData(BaseModel):
    date_str: str
    paper: Optional[Paper] = None
    sections: dict[str, str] = Field(default_factory=dict)
