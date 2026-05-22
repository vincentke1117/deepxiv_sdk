# deepxiv-sdk

**DeepXiv is an agent-first paper search and progressive reading tool.**

Install it with `pip`, start using it immediately, and let the CLI auto-register an API token on first use — no setup needed before your first query.

> ### 🚦 Service status — [live status page](https://data.rag.ac.cn/status)
>
> - 🟢 **arXiv retrieval & reading** — online. We aim for a T+1 sync with arXiv (subject to arXiv's own ~1-day API latency).
> - 🔴 **bioRxiv / medRxiv** — **temporarily down due to a server-side issue. We're working to restore it as soon as possible.** Related commands return `503` in the meantime.
> - 🔑 Lost your token? Recover it at [data.rag.ac.cn/token-lookup](https://data.rag.ac.cn/token-lookup) (Google sign-in supported).
> - ℹ️ Data processing is currently trying a broader mix of models. If a TLDR looks off (e.g. truncated thinking content), please open an issue — we'll fix it.

- **🚦 Live Status**: [https://data.rag.ac.cn/status](https://data.rag.ac.cn/status)
- **📚 API Documentation**: [https://data.rag.ac.cn/api/docs](https://data.rag.ac.cn/api/docs)
- **📄 Technical Report**: [![arxiv](https://img.shields.io/badge/arXiv-2603.00084-b31b1b)](https://arxiv.org/abs/2603.00084)
- **📖 中文文档**: [README.zh.md](README.zh.md)

<p align="center">
  <img src="./assets/demo.gif" width="60%">
</p>

> 🚀 **Live Demo**: built on the deepxiv CLI in ~1 hour with vibe coding — try the [DeepResearch demo](https://demo.rag.ac.cn/). A full-stack research platform is on the way.

---

## What DeepXiv Does

DeepXiv is built around two workflows that matter for agents:

1. **Search + progressive content access** — read papers in layers, not all at once.
2. **Trending + popularity signals** — find what's worth reading right now.

The core idea: an agent should **search first, judge quickly, then read only the most valuable parts** — instead of blindly loading full papers.

## Quick Start

```bash
pip install deepxiv-sdk
```

On first use, deepxiv auto-registers a free anonymous token (1,000 requests/day) and saves it to `~/.env`:

```bash
deepxiv search "agentic memory" --limit 5
```

For the full stack (MCP server + built-in research agent):

```bash
pip install "deepxiv-sdk[all]"
```

## Progressive Reading: search → judge → read

The CLI is the primary interface. A few flags drive layered reading so agents don't load full papers unless they truly need to:

```bash
deepxiv search "agentic memory" --limit 5     # 1. find candidates
deepxiv paper 2409.05591 --brief              # 2. decide if it's worth reading
deepxiv paper 2409.05591 --head               # 3. inspect structure & token distribution
deepxiv paper 2409.05591 --section Method     # 4. read only the valuable parts
```

- `--brief` — title, TLDR, keywords, citations, GitHub URL
- `--head` — sections overview and token distribution
- `--section NAME` — read a single section (e.g. `Introduction`, `Method`, `Experiments`)
- `--preview` / `--raw` / *(no flag)* — ~10k-char preview / full markdown / full paper

---

## CLI Reference

### Search papers

Basic search (arXiv by default):

```bash
deepxiv search "transformer" --limit 10
deepxiv search "agentic memory" --limit 20 --format json
```

**Filter by author, org, and category** (comma-separated):

```bash
deepxiv search "image generation" \
  --authors "Shitao Xiao,Zheng Liu" \
  --orgs "Beijing Academy of Artificial Intelligence" \
  --categories cs.CV \
  --limit 5
```

> `--authors` and `--orgs` are filters *and* ranking signals; `--categories` is a pure filter.

**Filter by venue** (`--venue` is repeatable; common aliases match automatically):

```bash
deepxiv search "diffusion model" --venue NeurIPS --limit 5
deepxiv search "language model" --venue NeurIPS --venue ICLR --limit 5

# Add a conference year (when the venue's year is indexed for those papers):
deepxiv search "diffusion model" --venue NeurIPS --venue-year 2025 --limit 5
```

> `--venue NeurIPS` also matches `NIPS` / `Neural Information Processing Systems`
> (likewise `ICLR` ↔ `International Conference on Learning Representations`,
> `CVPR` ↔ `Computer Vision and Pattern Recognition`, …). Matching results carry
> `venue` and `venue_year` fields.

**Filter by date and citations.** `--date-from` / `--date-to` accept `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`:

```bash
# Papers from June 2025 onward
deepxiv search "image generation" --date-from 2025-06 --limit 5

# A date floor plus a citation floor
deepxiv search "diffusion models" --date-from 2024-01 --min-citations 50 --limit 5
```

> ⚠️ Filters stack with `AND`. A narrow single-month window combined with a high
> citation floor on a very specific query can legitimately return **0 results** —
> if a search comes back empty, broaden the date range or lower `--min-citations`.

**Advanced date filter** (`exact` / `after` / `before` / `between`):

```bash
# exact month
deepxiv search "image generation" --date-search-type exact --date-str 2025-06 --limit 5

# between: pass --date-str twice (start, end)
deepxiv search "image generation" \
  --date-search-type between --date-str 2025-06-01 --date-str 2025-07-01 --limit 5
```

**Pagination and reranking:**

```bash
deepxiv search "LLM alignment" --limit 10 --offset 10        # page 2
deepxiv search "transformer model" --use-fine-rerank --limit 10   # opt-in fine rerank (off by default)
```

The JSON payload follows `{status, total_count, result: [...]}` — see [Python SDK](#python-sdk).

### Read a paper

```bash
deepxiv paper 2409.05591                       # full paper
deepxiv paper 2409.05591 --brief               # quick summary
deepxiv paper 2409.05591 --head                # metadata + sections
deepxiv paper 2409.05591 --section Introduction
deepxiv paper 2409.05591 --preview             # ~10k chars
```

### Trending and popularity

```bash
deepxiv trending --days 7 --limit 30      # hottest recent papers (social signals)
deepxiv paper 2409.05591 --popularity     # per-paper views, tweets, likes, replies
```

### Web search

```bash
deepxiv wsearch "karpathy"
deepxiv wsearch "karpathy" --json
```

Each `wsearch` request costs **20 scores** (other requests cost **1**). An anonymous token gets **1,000 scores/day** (~50 web searches); a [registered token](https://data.rag.ac.cn/register) gets **10,000/day** (~500 web searches).

### Semantic Scholar metadata by ID

```bash
deepxiv sc 258001
deepxiv sc 258001 --json
```

Useful when your workflow already holds Semantic Scholar IDs. A Semantic Scholar **search** service (returning these IDs directly) is coming soon.

### PMC biomedical papers

```bash
deepxiv pmc PMC544940 --head
deepxiv pmc PMC544940
```

### bioRxiv & medRxiv preprints

> 🔴 **Temporarily unavailable.** The bioRxiv / medRxiv service is down due to a
> server-side issue and currently returns `503`. We're working to restore it as
> soon as possible — see the [live status page](https://data.rag.ac.cn/status).
> The commands below are documented for when it's back online.

Preprint search shares the unified retrieve endpoint with arXiv (same filters as above):

```bash
# Search
deepxiv search "protein design" --biorxiv --limit 5
deepxiv search "Alzheimer" --medrxiv --date-from 2024-01

# Fetch a paper by DOI
deepxiv biorxiv 10.1101/2021.02.26.433129
deepxiv biorxiv 10.1101/2021.02.26.433129 --format text
deepxiv biorxiv 10.1101/2021.02.26.433129 --section Introduction,Methods
deepxiv medrxiv 10.1101/2025.08.11.25333149 --format text

# Or via flags on the paper command
deepxiv paper 10.1101/2021.02.26.433129 --biorxiv --section Introduction
```

---

## Agent Workflows

Two ready-to-use workflows ship as reusable skills:

**Review recent hot papers** → [skills/deepxiv-trending-digest/SKILL.md](skills/deepxiv-trending-digest/SKILL.md)

```bash
deepxiv trending --days 7 --limit 30 --json
# then: --brief each → --head the promising ones → read key sections → write a report
```

**Enter a new research topic** → [skills/deepxiv-baseline-table/SKILL.md](skills/deepxiv-baseline-table/SKILL.md)

```bash
deepxiv search "agentic memory" --date-from 2026-03-01 --limit 100 --format json
# then: batch-brief → prioritize GitHub links → --head experiments → build a baseline table
```

---

## Python SDK

```python
from deepxiv_sdk import Reader

reader = Reader()

# Unified retrieve endpoint; arXiv by default.
results = reader.search("agent memory", size=5)
for paper in results["result"]:
    print(paper["arxiv_id"], paper["score"], paper["title"])

# Progressive reading
brief = reader.brief("2409.05591")
head = reader.head("2409.05591")
intro = reader.section("2409.05591", "Introduction")

# Other endpoints
web = reader.websearch("karpathy")
sc_meta = reader.semantic_scholar("258001")
```

### `reader.search()` parameters

```python
reader.search(
    query,
    size=10,                  # → upstream top_k (1~100); you can also pass top_k=
    offset=0,                 # 0~10000
    source="arxiv",           # "arxiv" | "biorxiv" | "medrxiv"
    categories=None,          # list[str]; filter only
    authors=None,             # list[str]; filter + ranking signal
    orgs=None,                # list[str]; filter + ranking signal
    venue=None,               # str | list[str]; aliases match (NeurIPS↔NIPS)
    venues=None,              # plural alias for venue; merged with it
    venue_year=None,          # int | str; e.g. 2025
    min_citation=None,
    date_from=None,           # convenience; "YYYY" / "YYYY-MM" / "YYYY-MM-DD"
    date_to=None,
    date_search_type=None,    # advanced: "between" | "exact" | "after" | "before"
    date_str=None,            # advanced: str or [start, end]
    use_fine_rerank=False,    # SDK default off (cheaper); set True for better ordering
)
```

Response shape:

```jsonc
{
  "status": "success",
  "total_count": 3,
  "result": [
    {
      "arxiv_id": "2506.18871",    // biorxiv_id / medrxiv_id when source != arxiv
      "title": "...", "score": 0.9475, "abstract": "...", "tldr": "...",
      "authors": [{ "name": "...", "orgs": ["..."] }],
      "url": "...", "date": "2025-06-23T17:38:54Z",
      "citation_count": 217, "categories": ["cs.CV"],
      "venue": "NeurIPS", "venue_year": 2025   // present when venue data exists
    }
  ]
}
```

### Reader methods

```python
reader.brief(arxiv_id)             # title, TLDR, keywords, citations, GitHub URL
reader.head(arxiv_id)              # metadata + sections overview
reader.section(arxiv_id, name)     # one section
reader.preview(arxiv_id)           # ~10k-char preview
reader.raw(arxiv_id)               # full markdown
reader.json(arxiv_id)              # structured JSON
reader.websearch(query)            # web search (costs 20 scores)
reader.semantic_scholar(sc_id)     # metadata by Semantic Scholar ID
reader.trending(days=7, limit=30)  # trending papers
reader.social_impact(arxiv_id)     # popularity metrics
reader.pmc_head(pmc_id)            # PMC metadata
reader.pmc_json(pmc_id)            # full PMC JSON
```

> 🔴 bioRxiv / medRxiv access — `reader.search(source="biorxiv"|"medrxiv")`,
> `reader.biomed_data(...)`, and `reader.biomed_search(...)` — is **temporarily
> down** (server-side issue). See the status banner above.

<details>
<summary><b>Search API changes (2026-04)</b> — migration notes from the old Elasticsearch-style interface</summary>

The search backend moved to the unified `/arxiv/?type=retrieve` service. The SDK keeps parameter names where possible:

| Parameter | Status | Notes |
|---|---|---|
| `size` | kept | Mapped to upstream `top_k`. `top_k=` also accepted. |
| `offset` | kept | Capped at `0~10000`. |
| `categories`, `authors`, `min_citation` | kept | Same semantics. |
| `source` | new | `"arxiv"` (default), `"biorxiv"`, `"medrxiv"`. `reader.biomed_search()` is now a thin wrapper. |
| `orgs` | new | Org filter; also influences ranking. |
| `venue` / `venues` / `venue_year` | new | Filter by publication venue (str or list; aliases like `NeurIPS`↔`NIPS` match automatically) and conference year. `venue` and `venues` are equivalent. |
| `date_search_type` / `date_str` | new | `between` / `exact` / `after` / `before`. |
| `date_from` / `date_to` | kept (mapped) | Auto-converted to `date_search_type` + `date_str`; now also accept `YYYY` / `YYYY-MM`. |
| `use_fine_rerank` | new | Upstream default `True`; **SDK defaults to `False`**. |
| `search_mode` / `bm25_weight` / `vector_weight` | **deprecated** | Accepted but ignored (warning logged). |
| `search_funcs`, `return_contents`, `return_roc` | not exposed | Always default. Use `reader.raw()` / `section()` / `json()` for content. |

Response migration: `{total, took, results}` → `{status, total_count, result}`; per-item ID is `arxiv_id` / `biorxiv_id` / `medrxiv_id`; `paper["citation"]` → `paper["citation_count"]`. On the CLI, `--limit` maps to `size`, `--mode` is a deprecated no-op, and `--biorxiv` / `--medrxiv` switch the source.
</details>

---

## Agent Integration

DeepXiv works well inside Codex, Claude Code, OpenClaw, and similar agent runtimes.

### MCP Server

Add to your Claude Desktop MCP config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "deepxiv": {
      "command": "deepxiv",
      "args": ["serve"],
      "env": { "DEEPXIV_TOKEN": "your_token_here" }
    }
  }
}
```

Available MCP tools:

| Tool | Description |
|------|-------------|
| `search_papers` | Search arXiv papers |
| `get_paper_brief` | Quick summary |
| `get_paper_metadata` | Full metadata |
| `get_paper_section` | Read specific section |
| `get_full_paper` | Complete paper |
| `get_paper_preview` | Paper preview |
| `get_pmc_metadata` | PMC paper metadata |
| `get_pmc_full` | Complete PMC paper |

### CLI Skill

```bash
mkdir -p $CODEX_HOME/skills
ln -s "$(pwd)/skills/deepxiv-cli" $CODEX_HOME/skills/deepxiv-cli
```

For frameworks without native skill support, load [skills/deepxiv-cli/SKILL.md](skills/deepxiv-cli/SKILL.md) as operating instructions.

### Built-in Research Agent

If you don't want to compose workflows yourself, the CLI ships a ReAct agent (install with `pip install "deepxiv-sdk[all]"`). It works with any OpenAI-compatible API (OpenAI, DeepSeek, OpenRouter, local Ollama, …) and runs multi-turn search → read → reason.

```bash
deepxiv agent config   # configure LLM API (stored locally only)
deepxiv agent query "What are the latest papers about agent memory?" --verbose
```

```python
from deepxiv_sdk import Agent

agent = Agent(api_key="your_key", base_url="https://api.deepseek.com/v1", model="deepseek-chat")
print(agent.query("Compare key ideas in transformers and attention mechanisms"))
```

---

## Token Management

deepxiv resolves the token from (in order) the `--token` option, the `DEEPXIV_TOKEN` env var, then `~/.env`. On first use it auto-registers one for you.

```bash
deepxiv search "agent"                          # auto-register on first use (recommended)
deepxiv config --token YOUR_TOKEN               # save to ~/.env
export DEEPXIV_TOKEN="your_token"               # or use an env var
deepxiv paper 2409.05591 --token YOUR_TOKEN     # or pass per command
```

| Token type | Daily limit | How to get |
|---|---|---|
| Auto-registered (anonymous) | 1,000 requests | Automatic on first CLI use |
| Registered | 10,000 requests | [data.rag.ac.cn/register](https://data.rag.ac.cn/register) |
| Custom / higher | Contact us | Email `tommy[at]chien.io` with your use case |

**Free test papers** (no token required) — arXiv: `2409.05591`, `2504.21776`; PMC: `PMC544940`, `PMC514704`.

## Error Handling

```python
from deepxiv_sdk import (
    Reader,
    AuthenticationError,  # 401 - invalid or expired token
    RateLimitError,       # 429 - daily limit reached
    NotFoundError,        # 404 - paper not found
    ServerError,          # 5xx - server error
    APIError,             # other API errors
)

try:
    paper = reader.brief("2409.05591")
except AuthenticationError:
    print("Please update your token")
except RateLimitError:
    print("Daily limit reached")
except NotFoundError:
    print("Paper not found")
except APIError as e:
    print(f"API error: {e}")
```

## Troubleshooting

- **Do I need a token?** No — some papers are free, and a token is auto-created on first use.
- **Max search results?** 100 per request; use `--offset` / `offset=` to paginate.
- **A search returns 0 results?** Loosen filters — stacked `--date-*` + `--min-citations` constraints can over-narrow the result set.
- **Timeouts?** The Reader retries (max 3) with exponential backoff. Customize with `Reader(timeout=120, max_retries=5)`.
- **Can I cache content?** Yes — cache locally after fetching; paper content doesn't change.
- **Which LLMs does the agent support?** Any OpenAI-compatible API (OpenAI, DeepSeek, OpenRouter, local Ollama, …).
- **Agent errors with `Reasoning content is only supported as the last assistant message`?** Thinking/reasoning models (MiMo, DeepSeek-R1, …) need thinking disabled for multi-round tool use. Use `deepxiv agent query "…" --disable-thinking`, or in Python `Agent(..., enable_thinking=False)` (equivalently `extra_body={"enable_thinking": False}`).
- **Agent keeps retrying a failing tool?** When the data service is down, the agent now trips a circuit breaker after a few consecutive service failures and returns a best-effort answer instead of looping. Tune with `Agent(..., max_consecutive_failures=N)` (`0` disables it).
- **`agent.add_paper()` on a brand-new paper?** It returns `False` (instead of raising) when the paper isn't found or isn't indexed yet — very recent papers (<1–3 days old) often aren't. Genuine errors (auth, rate limit, 5xx) still raise. To handle the exception directly: `from deepxiv_sdk import NotFoundError` (also available as `from deepxiv_sdk.exceptions import NotFoundError`).
- **bioRxiv / medRxiv returns `503`?** Known outage — see the [status page](https://data.rag.ac.cn/status).

## Examples

See [examples/](examples/): `quickstart.py`, `example_reader.py`, `example_agent.py`, `example_advanced.py`, `example_error_handling.py`.

## Roadmap & Coverage

DeepXiv is moving toward an **academic paper data interface at 100M+ scale**, increasingly using Semantic Scholar metadata as the base layer:

1. Full arXiv coverage with T+1 automatic updates
2. anyXiv coverage (bioRxiv, medRxiv, …)
3. Full open-access literature coverage

| Source | Status |
|---|---|
| arXiv | ✅ online — primary source |
| PubMed Central (PMC) | ✅ online — biomedical & life sciences |
| bioRxiv / medRxiv | 🔴 temporarily down (server-side issue, recovering soon) |
| Semantic Scholar metadata | 🔄 expanding as the metadata foundation |

> DeepXiv focuses on open-access literature so agents can work on unrestricted paper data instead of getting blocked by subscription walls.

## License & Support

MIT License — see [LICENSE](LICENSE).

- 🚦 **Status**: [data.rag.ac.cn/status](https://data.rag.ac.cn/status)
- 🐛 **GitHub Issues**: [github.com/qhjqhj00/deepxiv_sdk/issues](https://github.com/qhjqhj00/deepxiv_sdk/issues)
- 📚 **API Documentation**: [data.rag.ac.cn/api/docs](https://data.rag.ac.cn/api/docs)
- 📧 **Higher limits**: [register](https://data.rag.ac.cn/register) for 10,000 requests/day, or email `tommy[at]chien.io` to describe your use case for a custom limit
</content>
</invoke>
