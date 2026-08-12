# DeepXiv 1.0 — filling in the data layer that agentic search is missing

Agents can reason. What they lack is a substrate to reason *over*: full paper text, real citations, and a retrieval loop that doesn't hand back ten blue links. DeepXiv is that layer — ask a question, get an answer grounded in sources you can verify.

```bash
pip install deepxiv-sdk
```

- **🌐 Live System**: [deepxiv.com](https://deepxiv.com) — the official research platform, built on deepxiv-sdk
- **📚 API Documentation**: [data.rag.ac.cn/api/docs](https://data.rag.ac.cn/api/docs)
- **🚦 Live Status**: [data.rag.ac.cn/status](https://data.rag.ac.cn/status)
- **📄 Technical Report**: [![arxiv](https://img.shields.io/badge/arXiv-2603.00084-b31b1b)](https://arxiv.org/abs/2603.00084)
- **📖 中文文档**: [README.zh.md](README.zh.md)

<p align="center">
  <img src="./assets/demo.gif" width="100%">
  <br>
  <em><code>deepxiv ask</code> — a question in, a cited answer streaming out</em>
</p>

---

## What's new in 1.0: agentic search

Two endpoints, same shape. A question goes in; the service picks its own tools, reads sources when it needs to, and streams back an answer with citations.

```bash
deepxiv ask "what speedup does speculative decoding report on HumanEval"
deepxiv ask "Anthropic Claude API pricing tiers" --web
```

| | Backend | Answers with | Best for |
|---|---|---|---|
| **`deepxiv ask`** | Local full-text arXiv corpus (Qdrant hybrid retrieval + paper bodies) | `[arXiv:2512.15176]` — real IDs | Methods, numbers, experimental results |
| **`deepxiv ask --web`** | Google + cached page bodies | Markdown links to real URLs | Current events, products, pricing, anything non-academic |

Neither is a wrapper around a web search box. The arXiv side reads actual paper sections; the web side reads cached page bodies.

### ⚠️ Registered accounts only

Agentic search needs a key from **[data.rag.ac.cn/register](https://data.rag.ac.cn/register)**. The token deepxiv auto-registers on first use is *not* eligible and returns `403`.

**Every account currently gets 30 agentic calls per day, free.** That quota is separate from your general daily limit — regular search and paper reading are unaffected by it, and vice versa. Need more? Email `tommy[at]chien.io` with your use case.

```bash
deepxiv config --token YOUR_REGISTERED_KEY
```

### What an answer looks like

```
$ deepxiv ask "what speedup does DEER report on HumanEval"

DEER reports a 5.54× speedup on HumanEval (with Qwen3-30B-A3B as the target
model), compared to EAGLE-3's 2.41× on the same benchmark [arXiv:2512.15176].

📚 Sources (1 cited, 10 retrieved — use --all-sources for the rest):
  1. [2512.15176] DEER: Draft with Diffusion, Verify with Autoregressive Models
     https://arxiv.org/abs/2512.15176
```

The answer goes to **stdout**, sources and progress to **stderr** — so `deepxiv ask "…" > answer.md` captures just the answer.

### Effort levels

| `--effort` | Gather rounds | First token (arXiv) | First token (web) |
|---|---|---|---|
| `default` *(default)* | 1–2 | **3–4s** | 5–9s |
| `high` | 3 | 7–8s | ≈13s |
| `xhigh` | 4–5 | 9–13s | longer |

Rounds are a ceiling, not a floor — the service converges early once it has enough evidence. Web is slower because Google cache misses cost 1.7–4.3s and aren't under our control.

### Writing queries that work

This is worth more than any flag.

- **Be specific.** The service assumes your query is already refined. `"what compression ratio does KV cache eviction report on LongBench"` beats `"kv cache"` by a wide margin.
- **Ask for numbers if you want numbers.** Saying "what speedup" or "which benchmark" pushes the service to read source text instead of skimming abstracts and snippets.
- **Chinese works directly.** arXiv queries are rewritten to English technical terms for retrieval; web switches to a Chinese locale. The answer comes back in your query's language.
- **Put arXiv scope limits in the query text** — year, venue (NeurIPS/ICLR/CVPR), category (cs.CL), author, institution, minimum citations. They become retrieval filters.
- **If results miss, rephrase.** Raising `--effort` only adds reading rounds; it can't redirect the first-round recall.

### Flags

```bash
deepxiv ask "reward hacking in RLHF" --verbose          # tool calls + quota on stderr
deepxiv ask "state space models vs transformers" --json # one JSON object
deepxiv ask "MoE routing collapse" --no-stream          # wait for the full answer
deepxiv ask "diffusion samplers" --all-sources          # every retrieved source

deepxiv ask "NeurIPS 2025 best paper" --web --search-type news
deepxiv ask "retrieval evaluation methodology" --web --search-type scholar
```

`--top-k N` (1–30, arXiv only) sets first-round retrieval size. `--search-type` / `--gl` / `--hl` are web-only. `--max-answer-tokens N` (256–16384) caps answer length; `--language LANG` overrides the answer language.

### Three things to know about the results

> **Citations are real.** The service is instructed never to invent an arXiv ID or URL, and says "no relevant papers" rather than fabricating one. `[arXiv:2512.15176]` maps directly to `https://arxiv.org/abs/2512.15176`.

> **Sources are the retrieval set, not the citation list.** A 10-paper retrieval often supports a single citation. The CLI shows only cited sources by default; `--all-sources` shows the rest.

> **Web evidence has two strengths.** The service reads only *cached* page bodies and never fetches live, so an uncached page contributes just its search snippet. Chinese sites and news pages are cached less often. The CLI marks pages read in full (📄) versus snippet-only (🔗), and the answer flags snippet-only claims. Weigh them accordingly.

Also: when the answer hits `--max-answer-tokens`, the CLI warns and the API sets `answer_truncated`. Don't treat a truncated answer as complete.

---

## The rest of the toolkit

Everything below costs 1 general limit unit per call and works with any token, including the auto-registered one.

### Progressive reading: search → judge → read

Read papers in layers so an agent doesn't load 50k tokens to answer a question about the method section.

```bash
deepxiv search "agentic memory" --limit 5     # 1. find candidates
deepxiv paper 2409.05591 --brief              # 2. is it worth reading?
deepxiv paper 2409.05591 --head               # 3. structure & token distribution
deepxiv paper 2409.05591 --section Method     # 4. read only what matters
```

- `--brief` — title, TLDR, keywords, citations, GitHub URL
- `--head` — sections overview and token distribution
- `--section NAME` — one section (`Introduction`, `Method`, `Experiments`, …)
- `--preview` / `--raw` / *(no flag)* — ≈10k-char preview / full markdown / full paper

### Search

```bash
deepxiv search "transformer" --limit 10 --format json

# Filter by author, org, category (comma-separated)
deepxiv search "image generation" --authors "Shitao Xiao" --categories cs.CV --limit 5

# Filter by venue (repeatable; NeurIPS ↔ NIPS aliases match automatically)
deepxiv search "diffusion model" --venue NeurIPS --venue-year 2025 --limit 5

# Filter by date and citations (dates accept YYYY, YYYY-MM, YYYY-MM-DD)
deepxiv search "diffusion models" --date-from 2024-01 --min-citations 50

# Advanced date modes: exact / after / before / between
deepxiv search "image generation" \
  --date-search-type between --date-str 2025-06-01 --date-str 2025-07-01

# Pagination and opt-in fine reranking
deepxiv search "LLM alignment" --limit 10 --offset 10
deepxiv search "transformer model" --use-fine-rerank
```

`--authors` and `--orgs` are filters *and* ranking signals; `--categories` is a pure filter. Filters combine with `AND`, so stacking a narrow date window on a high citation floor can legitimately return 0 results — loosen one.

Returns `{status, total_count, result: [...]}`. Each result carries `arxiv_id`, `title`, `abstract`, `tldr`, `authors`, `categories`, `citation_count`, `date`, `github_url`, `score`, and `venue`/`venue_year` when known.

### Other sources

```bash
deepxiv trending --days 7 --limit 30       # hottest recent papers (social signals)
deepxiv paper 2409.05591 --popularity      # per-paper views, tweets, likes

deepxiv pmc PMC544940 --head               # PubMed Central

deepxiv search "protein design" --biorxiv --limit 5     # bioRxiv / medRxiv
deepxiv biorxiv 10.1101/2021.02.26.433129 --format text
deepxiv medrxiv 10.1101/2020.03.24.20042937 --section Methods
```

## Agent integration

### CLI skill

```bash
mkdir -p $CODEX_HOME/skills
ln -s "$(pwd)/skills/deepxiv-cli" $CODEX_HOME/skills/deepxiv-cli
```

For frameworks without native skill support, load [skills/deepxiv-cli/SKILL.md](skills/deepxiv-cli/SKILL.md) as operating instructions. Two worked workflows also ship as skills: [trending digest](skills/deepxiv-trending-digest/SKILL.md) and [baseline table](skills/deepxiv-baseline-table/SKILL.md).

### Built-in research agent

Runs the search → read → reason loop locally with your own LLM key — useful when you want to control the model or the loop. Install with `pip install "deepxiv-sdk[all]"`; works with any OpenAI-compatible API.

```bash
deepxiv agent config
deepxiv agent query "What are the latest papers about agent memory?" --verbose
```

### Rolling your own MCP server

deepxiv ships no MCP server — the CLI and `Reader` are the integration surface, and wrapping them takes about twenty lines. What's worth copying is not the plumbing but the guidance below: an agent given a bare `ask(query)` tool will use this API poorly.

```python
from mcp.server.mcpserver import MCPServer   # mcp>=2.0; it was FastMCP in 1.x
from deepxiv_sdk import Reader, agent_search_sources

mcp = MCPServer("deepxiv")
reader = Reader()

@mcp.tool()
def ask_arxiv(query: str, effort: str = "default") -> str:
    """Answer a research question, citing real arXiv IDs.

    Use for methods, numbers, and experimental results from papers. For current
    events, products, or anything non-academic, use ask_web.

    Be specific — "what compression ratio does KV cache eviction report on
    LongBench" works; "kv cache" does not. Ask for numbers explicitly ("what
    speedup", "which benchmark") to make it read paper bodies rather than
    abstracts. Put scope (year, venue, category, author) in the query text.
    Chinese works directly. If the answer misses, rephrase — raising effort adds
    reading rounds but cannot redirect first-round recall.

    effort: "default" (fastest), "high" (comparing papers), "xhigh" (surveys).
    """
    result = reader.agent_search(query, source="arxiv", effort=effort)
    answer = result["answer"]
    # `sources` is the retrieval set, a superset of what the answer cites.
    cited = [p for p in agent_search_sources(result) if p["arxiv_id"] in answer]
    lines = [answer]
    if cited:
        lines += ["\n---\nCited papers:"] + [
            f"- [{p['arxiv_id']}] {p['title']}" for p in cited
        ]
    if result["stats"]["answer_truncated"]:
        lines.append("\n⚠️ Truncated — do not treat as complete.")
    return "\n".join(lines)

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

Four things to put in your tool descriptions, or the agent will misuse the results:

1. **Citations are real** — the service never invents an ID, and says "no relevant papers" instead. Tell the agent to preserve them in what it reports back.
2. **`sources` is the retrieval set, not the citation list** — filter to IDs that appear in the answer, as above, or the agent will present unrelated papers as evidence.
3. **On the web backend, evidence has two strengths** — pages with `read: true` were read in full; the rest contributed only a search snippet. Surface that distinction so the agent can qualify weaker claims.
4. **`answer_truncated` means incomplete** — say so explicitly, otherwise the agent will summarise a cut-off answer as if it were whole.

For a `web` tool, swap `source="web"`, add `search_type` (`search` / `scholar` / `news` / `images`), and match on `page["url"] in answer` instead of `arxiv_id`.

---

## Tokens and limits

deepxiv resolves the token from `--token`, then `DEEPXIV_TOKEN`, then `~/.env`. On first use it auto-registers one.

| | Daily limit | Agentic calls | How to get |
|---|---|---|---|
| Auto-registered | 1,000 requests | ❌ not eligible | Automatic on first CLI use |
| Registered | 10,000 requests | ✅ 30/day | [data.rag.ac.cn/register](https://data.rag.ac.cn/register) |
| Custom | Contact us | Contact us | Email `tommy[at]chien.io` |

The two pools are independent: agentic calls don't consume your general limit, and vice versa. Lost your key? Recover it at [data.rag.ac.cn/token-lookup](https://data.rag.ac.cn/token-lookup).

Free test papers (no token) — arXiv: `2409.05591`, `2504.21776`; PMC: `PMC544940`.

## Python SDK

The CLI covers most workflows. For the Python API — agentic search (blocking and streaming), progressive reading, batching, and error handling — see **[USAGE.md](USAGE.md)**.

```python
from deepxiv_sdk import Reader

reader = Reader()
result = reader.agent_search("what speedup does DEER report on HumanEval")
print(result["answer"])
```

## Troubleshooting

- **`ask` returns 403?** You're on an auto-registered token. Agentic search needs a registered key — see above.
- **`ask` feels slow to start?** Only `--effort default` targets a sub-5s first token; `high`/`xhigh` deliberately gather more.
- **`ask` missed the point?** Rephrase more specifically rather than raising `--effort` — effort adds reading rounds but can't redirect first-round recall.
- **`ask` listed papers unrelated to the answer?** That's the retrieval set, not the citation list. `--all-sources` shows it in full.
- **A search returns 0 results?** Loosen filters — stacked date and citation constraints over-narrow quickly.
- **Timeouts?** `Reader` retries (max 3) with exponential backoff; customize with `Reader(timeout=120, max_retries=5)`. The `agent_search*` methods never auto-retry, by design.
- **Agent errors with `Reasoning content is only supported as the last assistant message`?** Reasoning models need thinking off for multi-round tool use: `deepxiv agent query "…" --disable-thinking`, or `Agent(..., enable_thinking=False)`.
- **`agent.add_paper()` on a brand-new paper?** Returns `False` when the paper isn't indexed yet — papers under 1–3 days old often aren't.

## Coverage

| Source | Status |
|---|---|
| arXiv | ✅ full text, T+1 sync |
| Web | ✅ Google + cached page bodies |
| PubMed Central | ✅ biomedical & life sciences |
| bioRxiv / medRxiv | ✅ biology & medicine preprints |

DeepXiv focuses on open-access literature so agents work on unrestricted data instead of hitting subscription walls.

## Examples

See [examples/](examples/): `example_ask.py`, `quickstart.py`, `example_reader.py`, `example_agent.py`, `example_advanced.py`, `example_error_handling.py`.

## License & support

MIT License — see [LICENSE](LICENSE).

- 🌐 **Live system**: [deepxiv.com](https://deepxiv.com)
- 🐛 **Issues**: [github.com/qhjqhj00/deepxiv_sdk/issues](https://github.com/qhjqhj00/deepxiv_sdk/issues)
- 📚 **API docs**: [data.rag.ac.cn/api/docs](https://data.rag.ac.cn/api/docs)
- 🚦 **Status**: [data.rag.ac.cn/status](https://data.rag.ac.cn/status)
- 📧 **Higher limits**: email `tommy[at]chien.io` with your use case
