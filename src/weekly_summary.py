from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


def build_weekly_summary(days: int = 7) -> Path | None:
    digest_dir = Path("digests")
    digest_dir.mkdir(exist_ok=True)

    today = date.today()
    candidates: list[Path] = []
    for i in range(days):
        d = today - timedelta(days=i)
        p = digest_dir / f"{d}.md"
        if p.exists():
            candidates.append(p)

    if len(candidates) < 2:
        logger.info("Weekly summary skipped: fewer than 2 digest files in last %s days.", days)
        return None

    weekly_dir = Path("weekly")
    weekly_dir.mkdir(parents=True, exist_ok=True)
    output = weekly_dir / f"{today}.md"

    lines = [f"# 每周论文回顾 - {today}", "", "## 本周收录", ""]
    for fp in sorted(candidates):
        content = fp.read_text(encoding="utf-8")
        paper_line = "(未找到论文标题)"
        for line in content.splitlines():
            if line.startswith("## 今日论文"):
                # next non-empty line
                continue
        content_lines = content.splitlines()
        for idx, line in enumerate(content_lines):
            if line.startswith("## 今日论文"):
                for j in range(idx + 1, min(idx + 6, len(content_lines))):
                    if content_lines[j].strip():
                        paper_line = content_lines[j].strip()
                        break
                break
        lines.append(f"- {fp.stem}: {paper_line}")

    lines.extend(["", "## 观察", "- 本周重点可围绕阵列建模、波束形成与后滤波协同设计。", "- 建议优先精读和自己研究方向最贴近的 1-2 篇论文。", ""])
    output.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Weekly summary saved to %s", output)
    return output
