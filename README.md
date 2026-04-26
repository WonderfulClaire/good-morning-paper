# good-morning-paper

面向多通道语音增强/阵列语音增强/神经波束形成方向的每日论文助手。

> Python: **3.11+**（GitHub Actions 默认 3.12）

## 设计说明（借鉴与取舍）

本项目在思路上参考了：
- TideDra/zotero-arxiv-daily（强调自动化工作流、个性化推荐、低部署门槛）
- NN0202/arxiv_daily_paper_push（强调结构化中文解读与易读输出）

我们借鉴的是**产品形态与流程设计**，不是直接复制实现代码：
- 借鉴：定时自动化、可手动触发、配置化、个性化输入、结构化输出。
- 避免：重依赖某单一外部系统（如本轮不引入 Zotero API）、硬编码密钥、把“摘要”写成无个性模板。

## 功能

- 从 Semantic Scholar / OpenAlex / arXiv 检索近期论文元数据。
- 支持个性化排序：
  - 关键词匹配（config.yaml）
  - 种子论文相似度（seed_papers.yaml）
  - 会议期刊优先级、时效性、前沿主题加分
- 每日选择 1 篇主论文，输出中文 digest 到 `digests/YYYY-MM-DD.md`。
- Digest 包含：论文元数据、相关性分数、相关性理由、来源、结构化解读。
- 可选邮件发送（SMTP 配置齐全时发送）。
- 支持每周汇总：`python main.py --weekly-summary` 输出到 `weekly/YYYY-MM-DD.md`。

## 项目结构

```text
main.py
config.yaml
seed_papers.yaml
requirements.txt
README.md
digests/.gitkeep
weekly/.gitkeep
src/
  config_loader.py
  models.py
  seed_loader.py
  search_semantic_scholar.py
  search_openalex.py
  search_arxiv.py
  rank_papers.py
  generate_digest.py
  send_email.py
  weekly_summary.py
.github/workflows/daily.yml
```

## 种子论文配置（个性化）

编辑 `seed_papers.yaml`：

```yaml
seed_papers:
  - title: "Example Seed Paper on Neural Beamforming"
    authors: ["Author A", "Author B"]
    venue: "ICASSP"
    year: 2024
    abstract: "..."
    url: "https://example.org/seed-paper"
    notes: "你为什么关注这篇"
```

字段支持：`title, authors, venue, year, abstract, url, notes`。

若文件不存在或为空，系统自动回退到关键词排序，不会报错退出。

## 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 日常模式（写 digest + 可选发邮件）

```bash
python main.py
```

### Dry-run（仅预览，不写文件，不发邮件）

```bash
python main.py --dry-run
```

### 每周汇总模式

```bash
python main.py --weekly-summary
```

如果最近 7 天少于 2 个 digest 文件，会打印清晰提示并安全退出。

## GitHub Actions

工作流：`.github/workflows/daily.yml`

- `schedule`：每天 UTC 12:00（约等于纽约时间早 8 点，DST 时段）。
- `workflow_dispatch`：手动触发，并可选择 mode：
  - `daily`
  - `dry-run`
  - `weekly-summary`

工作流会在成功后自动执行：
- `git add digests/ weekly/`
- 有变化才 commit
- push 回当前分支

## 环境变量（均可选）

- `OPENAI_API_KEY`：启用 LLM 更高质量中文解读
- `OPENAI_MODEL`：默认 `gpt-4o-mini`
- `SEMANTIC_SCHOLAR_API_KEY`：提升 Semantic Scholar 配额
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO`：启用邮件发送

> Baseline 无任何 key 也可运行（只是模板解读 + 不发邮件）。

## 注意事项

- 不抓取全文 PDF，不复制受版权保护的大段原文。
- 仅使用元数据、摘要、链接与模型生成评论。
