from __future__ import annotations

import json
from pathlib import Path

import yaml

from src.models import SeedPaper


def load_seed_papers(path: str = "seed_papers.yaml") -> list[SeedPaper]:
    seed_path = Path(path)
    if not seed_path.exists():
        return []

    if seed_path.suffix.lower() == ".json":
        raw = json.loads(seed_path.read_text(encoding="utf-8"))
    else:
        raw = yaml.safe_load(seed_path.read_text(encoding="utf-8"))

    if not raw:
        return []

    items = raw.get("seed_papers", raw) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []

    seeds: list[SeedPaper] = []
    for item in items:
        try:
            seeds.append(SeedPaper.model_validate(item))
        except Exception:
            continue
    return seeds
