from __future__ import annotations

import json
import logging
import os
from datetime import date

import requests

from src.models import DigestData, Paper

logger = logging.getLogger(__name__)


def _safe(text: str, default: str = "信息不足") -> str:
    text = (text or "").strip()
    return text if text else default


def _template_digest(today: str, paper: Paper | None) -> DigestData:
    if not paper:
        sections = {
            "今日论文": "今日未检索到高相关新论文。",
            "为什么值得读": "可以扩展检索关键词，或将 days_back 调大后重跑。",
            "核心问题": "暂无。",
            "方法直觉": "暂无。",
            "和 ExNet / AFNet / MVDR / post-filtering 的关系": "暂无直接对比。",
            "对我自己课题的启发": "检查检索源连通性与关键词覆盖。",
            "如果要精读，优先看哪几部分": "暂无。",
            "3 个关键词": "多通道语音增强, 神经波束形成, 后滤波",
            "论文链接": "N/A",
        }
        return DigestData(date_str=today, paper=None, sections=sections)

    sections = {
        "今日论文": f"{paper.title} ({paper.venue or paper.source}, {paper.year or 'N/A'})",
        "为什么值得读": f"与研究方向相关，综合分 {paper.score:.3f}。{paper.relevance_reason}",
        "核心问题": "该工作试图提升复杂噪声/混响场景下的语音增强或分离性能。",
        "方法直觉": _safe(paper.abstract[:300]) + ("..." if len(paper.abstract) > 300 else ""),
        "和 ExNet / AFNet / MVDR / post-filtering 的关系": "可重点对照其前端波束形成与后端后滤波衔接方式。",
        "对我自己课题的启发": "可借鉴其损失设计、阵列建模假设和泛化评估设置。",
        "如果要精读，优先看哪几部分": "建议优先看方法章节、实验设置与消融实验。",
        "3 个关键词": "神经波束形成, 多通道增强, 鲁棒后滤波",
        "论文链接": f"paper: {_safe(paper.url, 'N/A')} | arXiv: {_safe(paper.arxiv_url or '', 'N/A')} | DOI: {_safe(paper.doi or '', 'N/A')}",
    }
    return DigestData(date_str=today, paper=paper, sections=sections)


def _llm_digest(today: str, paper: Paper, api_key: str) -> DigestData | None:
    prompt = f"""
你是“资深语音增强研究助理”。请根据元数据写给研究者的中文解读，风格要有洞察、有重点，不是泛泛摘要。
硬性要求：不要复制受版权保护的原文，不要编造论文未提供的实验细节。
请严格按以下 Markdown 结构输出：
# 今日论文
## 为什么值得读
## 核心问题
## 方法直觉
## 和 ExNet / AFNet / MVDR / post-filtering 的关系
## 对我自己课题的启发
## 如果要精读，优先看哪几部分
## 3 个关键词
## 论文链接

论文信息：
标题: {paper.title}
摘要: {paper.abstract}
会议/期刊: {paper.venue}
年份: {paper.year}
链接: {paper.url}
arXiv: {paper.arxiv_url}
DOI: {paper.doi}
相关性说明: {paper.relevance_reason}
""".strip()

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [
                    {"role": "system", "content": "你是严谨的学术助手。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
            },
            timeout=45,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.warning("OpenAI generation failed, fallback to template: %s", exc)
        return None

    sections = {
        "今日论文": paper.title,
        "为什么值得读": "见下方生成内容",
        "核心问题": "见下方生成内容",
        "方法直觉": "见下方生成内容",
        "和 ExNet / AFNet / MVDR / post-filtering 的关系": "见下方生成内容",
        "对我自己课题的启发": "见下方生成内容",
        "如果要精读，优先看哪几部分": "见下方生成内容",
        "3 个关键词": "见下方生成内容",
        "论文链接": f"paper: {_safe(paper.url, 'N/A')} | arXiv: {_safe(paper.arxiv_url or '', 'N/A')} | DOI: {_safe(paper.doi or '', 'N/A')}\n\n{content}",
    }
    return DigestData(date_str=today, paper=paper, sections=sections)


def generate_digest(paper: Paper | None) -> DigestData:
    today = str(date.today())
    api_key = os.getenv("OPENAI_API_KEY")
    if paper and api_key:
        llm_result = _llm_digest(today, paper, api_key)
        if llm_result:
            return llm_result
    return _template_digest(today, paper)


def render_markdown(digest: DigestData) -> str:
    s = digest.sections
    return "\n".join(
        [
            f"# 每日论文速递 - {digest.date_str}",
            "",
            f"## 今日论文\n{s.get('今日论文', '')}",
            "",
            "## 论文元数据",
            f"- source: {digest.paper.source if digest.paper else 'N/A'}",
            f"- venue: {digest.paper.venue if digest.paper else 'N/A'}",
            f"- year: {digest.paper.year if digest.paper else 'N/A'}",
            f"- relevance score: {digest.paper.score if digest.paper else 0.0:.3f}",
            f"- relevance reasons: {digest.paper.relevance_reason if digest.paper else 'N/A'}",
            "",
            f"## 为什么值得读\n{s.get('为什么值得读', '')}",
            "",
            f"## 核心问题\n{s.get('核心问题', '')}",
            "",
            f"## 方法直觉\n{s.get('方法直觉', '')}",
            "",
            f"## 和 ExNet / AFNet / MVDR / post-filtering 的关系\n{s.get('和 ExNet / AFNet / MVDR / post-filtering 的关系', '')}",
            "",
            f"## 对我自己课题的启发\n{s.get('对我自己课题的启发', '')}",
            "",
            f"## 如果要精读，优先看哪几部分\n{s.get('如果要精读，优先看哪几部分', '')}",
            "",
            f"## 3 个关键词\n{s.get('3 个关键词', '')}",
            "",
            f"## 论文链接\n{s.get('论文链接', '')}",
            "",
        ]
    )
