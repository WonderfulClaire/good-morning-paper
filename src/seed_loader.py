from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from src.models import SeedPaper

logger = logging.getLogger(__name__)


def load_seed_papers(path: str = "seed_papers.yaml") -> list[SeedPaper]:
    seed_path = Path(path)
    if not seed_path.exists():
        logger.info("Seed file not found: %s", path)
        return []

    try:
        if seed_path.suffix.lower() == ".json":
            raw = json.loads(seed_path.read_text(encoding="utf-8"))
        else:
            raw = yaml.safe_load(seed_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse %s: %s", path, exc)
        return []

    if not raw:
        logger.warning("Seed file %s is empty. Expected a list or {seed_papers: [...]} format.", path)
        return []

    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("seed_papers")
    else:
        logger.warning("Invalid seed file structure in %s. Expected a list or {seed_papers: [...]} format.", path)
        return []

    if not isinstance(items, list):
        logger.warning("Invalid seed file structure in %s. Expected a list under seed_papers.", path)
        return []

    seeds: list[SeedPaper] = []
    for item in items:
        try:
            seeds.append(SeedPaper.model_validate(item))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping invalid seed paper entry in %s: %s", path, exc)
            continue
    logger.info("Loaded %s seed papers from %s", len(seeds), path)
    return seeds
