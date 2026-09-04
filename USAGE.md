# Python SDK Guide

The complete Python API. For CLI usage see [README.md](README.md).

> **中文版**: [USAGE.zh.md](USAGE.zh.md)

## Install

```bash
pip install deepxiv-sdk              # Reader + CLI
pip install "deepxiv-sdk[all]"       # + built-in research agent (needs your own LLM key)
```

```python
from deepxiv_sdk import Reader

reader = Reader()  # token from DEEPXIV_TOKEN or ~/.env
reader = Reader(token="...", timeout=60, max_retries=3)  # or configure explicitly
```

## Agentic search

```python
from deepxiv_sdk import Reader

reader = Reader()  # token from --token, DEEPXIV_TOKEN, or ~/.env

# Blocking — simplest, waits 8~30s for the whole answer
result = reader.agent_search("what speedup does DEER report on HumanEval")
print(result["answer"])
print(result["quota"]["remaining"], "agentic calls left today")

# Web backend
result = reader.agent_search("Claude API pricing", source="web", search_type="news")
```

Streaming — first token in ≈3–4s on arXiv at `effort="default"`:

```python
from deepxiv_sdk import agent_search_sources

chunks, sources, truncated = [], [], False
for event in reader.agent_search_stream("test-time compute scaling laws"):
    name = event["event"]
    if name == "answer_delta":
        chunks.append(event["text"])
        print(event["text"], end="", flush=True)
    elif name == "sources":
        sources = agent_search_sources(event)   # normalises papers/pages
    elif name == "done":
        truncated = event["answer_truncated"]
    elif name == "error":
        raise RuntimeError(f"{event['stage']}: {event['message']}")
answer = "".join(chunks)
```

Events always sent: `billing` (carries `tier` / `used` / `remaining`), `start`, `answer_start`, `answer_delta` (or `answer` when `stream_answer=False`), `sources`, `done`. Pass `verbose=True` to also receive `tool_call`, `tool_result`, `thinking`, `warning`. `answer_delta` carries only the final answer — process narration goes to `thinking`/`tool_call` and never overlaps.

The `sources` event keys its payload by backend — `papers` for arXiv (`arxiv_id`/`title`/`url`), `pages` for web (`url`/`title`/`read`). `agent_search_sources()` normalises both, plus the blocking endpoint's `sources`.

Both methods take `source` (`"arxiv"` / `"web"`), `effort`, `max_answer_tokens`, `language`, `timeout` (default 180s), plus `top_k` (arXiv) or `search_type` / `gl` / `hl` (web). Arguments are validated client-side, so an invalid call fails for free instead of spending a quota unit on a 422. Passing a backend's flag to the other backend raises rather than being silently dropped.

> These two methods **do not auto-retry**, unlike the rest of `Reader` — each call spends a quota unit, and a retried stream would re-bill and restart the answer. Handle `RateLimitError` with your own backoff.
>
> An `error` event is **yielded, not raised**: a partial answer may already have streamed, so the caller decides what to keep.

---

## Reader methods

```python
reader.agent_search(query, source="arxiv"|"web")   # agentic search → cited answer
reader.agent_search_stream(query, ...)             # same, streaming NDJSON events
reader.search(query, size=10, source="arxiv")      # unified retrieve
reader.brief(arxiv_id)                             # title, TLDR, keywords, citations
reader.head(arxiv_id)                              # metadata + sections overview
reader.section(arxiv_id, name)                     # one section
reader.preview(arxiv_id)                           # ~10k-char preview
reader.raw(arxiv_id) / reader.json(arxiv_id)       # full markdown / structured JSON
reader.trending(days=7, limit=30)                  # trending papers (days 1~30)
reader.talent_search(query, semantic=True)         # scholar search (spends agent quota)
reader.talent_survey(person_id, refresh=False)     # full profile for one scholar
reader.social_impact(arxiv_id)                     # popularity metrics
reader.pmc_head(pmc_id) / reader.pmc_json(pmc_id)  # PubMed Central
reader.biomed_search(...) / reader.biomed_data(...) # bioRxiv / medRxiv
```

<details>
<summary><b><code>reader.search()</code> parameters</b></summary>

```python
reader.search(
    query,
    size=10,                  # → upstream top_k (1~100); top_k= also accepted
    offset=0,                 # 0~10000
    source="arxiv",           # "arxiv" | "biorxiv" | "medrxiv"
    categories=None,          # list[str], filter only
    authors=None,             # list[str], filters and influences ranking
    orgs=None,                # list[str], filters and influences ranking
    venue=None,               # str | list[str]; aliases match automatically
    venue_year=None,          # int
    min_citation=None,        # int
    date_search_type=None,    # "between" | "exact" | "after" | "before"
    date_str=None,            # str, or [start, end] for "between"
    date_from=None,           # convenience; auto-mapped to the pair above
    date_to=None,
    use_fine_rerank=False,    # SDK defaults off (cheaper); True for better ordering
)
```

Venue alias matching is rule-based and best-effort, so it isn't always exact.

</details>

---

## Advanced Search

### Semantic Search

The retrieve endpoint is built on qdrant vector search — there is no search-mode
or weight tuning to do:

```python
from deepxiv_sdk import Reader

reader = Reader()

results = reader.search("agent memory", size=20)
```

The one ranking knob is `use_fine_rerank`. The SDK leaves it off (cheaper); turn
it on when ordering quality matters more than latency:

```python
results = reader.search("llm agents", size=20, use_fine_rerank=True)
```

> The old `search_mode` / `bm25_weight` / `vector_weight` parameters were
> removed in 0.4.0. They had been accepted-and-ignored since the 0.3.0 backend
> migration; passing them now raises `TypeError`.

### Advanced Filtering

```python
# Filter by categories (CS categories)
results = reader.search(
    "reinforcement learning",
    categories=["cs.AI", "cs.LG"],
    min_citation=50  # At least 50 citations
)

# Filter by date range
results = reader.search(
    "transformer",
    date_from="2024-01-01",
    date_to="2024-12-31"
)

# Filter by authors
results = reader.search(
    "attention mechanism",
    authors=["Ashish Vaswani", "Ilya Sutskever"]
)
```

## Efficient Content Loading

### Strategy 1: Quick Preview

For quick browsing, use `brief()` to get key information:

```python
brief = reader.brief("2409.05591")
print(f"Title: {brief['title']}")
print(f"TLDR: {brief.get('tldr')}")
print(f"Keywords: {brief.get('keywords')}")
print(f"Citations: {brief.get('citations')}")
print(f"GitHub: {brief.get('github_url')}")
```

**Token cost**: Very low (≈500 tokens)

### Strategy 2: Progressive Loading

Get metadata and section summaries, then load progressively:

```python
# 1. Get structure
head = reader.head("2409.05591")
print("Available sections:")
for section, info in head['sections'].items():
    print(f"  {section}: {info['token_count']} tokens - {info['tldr']}")

# 2. Load only relevant sections
intro = reader.section("2409.05591", "Introduction")
methods = reader.section("2409.05591", "Methods")
```

**Token cost**: Controlled (load only what you need)

### Strategy 3: Preview

Quickly scan paper beginning:

```python
preview = reader.preview("2409.05591")
print(preview['content'][:1000])
if preview['is_truncated']:
    print(f"... (total: {preview['total_characters']} chars)")
```

**Token cost**: Low (≈2k tokens)

### Strategy 4: Full Content

Load complete paper only when needed:

```python
full = reader.raw("2409.05591")
print(f"Full paper: {len(full)} chars, ~{len(full) // 4} tokens")
```

**Token cost**: High (10k-50k+ tokens)

## Error Handling and Retry

### Catch Specific Errors

```python
from deepxiv_sdk import (
    Reader,
    AuthenticationError,
    RateLimitError,
    NotFoundError,
    APIError
)

reader = Reader(token="your_token")

try:
    paper = reader.head("2409.05591")
except AuthenticationError:
    print("❌ Token invalid. Run 'deepxiv config' to update")
except RateLimitError:
    print("⚠️  Daily limit reached. Try again tomorrow")
except NotFoundError:
    print("❌ Paper not found. Check arXiv ID")
except APIError as e:
    print(f"❌ API error: {e}")
```

For `agent_search` / `agent_search_stream`, two of these carry a different
meaning:

```python
try:
    result = reader.agent_search("...", source="web")
except AuthenticationError:
    # 401 (invalid token) OR 403 — a valid SDK token without agentic access.
    # Agentic search needs a registered key; see README.
    ...
except RateLimitError:
    # The agentic quota is exhausted. It is a separate pool from the general
    # daily limit, so other Reader calls still work. These two methods never
    # auto-retry, so back off yourself.
    ...
```

### Custom Retry Configuration

```python
reader = Reader(
    token="your_token",
    timeout=120,      # Increase timeout
    max_retries=5,    # Up to 5 retries
    retry_delay=1.0   # Initial retry delay (seconds)
)
```

Reader automatically uses exponential backoff:
- Attempt 1 retry: 1 second
- Attempt 2 retry: 2 seconds
- Attempt 3 retry: 4 seconds
- ...

## Batch Processing

### Process Multiple Papers

```python
arxiv_ids = ["2409.05591", "2504.21776", "2503.04975"]

papers = {}
for arxiv_id in arxiv_ids:
    try:
        papers[arxiv_id] = reader.brief(arxiv_id)
    except Exception as e:
        print(f"Failed to fetch {arxiv_id}: {e}")

# Process fetched papers
for arxiv_id, paper in papers.items():
    print(f"{paper['title']} ({paper['citations']} citations)")
```

### Search Pagination

```python
# Get first 500 results
all_results = []
for offset in range(0, 500, 100):
    results = reader.search(
        "agent memory",
        size=100,
        offset=offset
    )
    all_results.extend(results['results'])

print(f"Total papers fetched: {len(all_results)}")
```

## Agent for Complex Analysis

### Basic Query

```python
from deepxiv_sdk import Agent

agent = Agent(
    api_key="your_openai_key",
    model="gpt-4"
)

answer = agent.query("What are key innovations in recent transformer papers?")
print(answer)
```

### Multi-Turn Conversation

```python
# First query
answer1 = agent.query("Summarize the MemGPT paper")
print(answer1)

# Follow-up uses previously loaded papers
answer2 = agent.query("Compare MemGPT with other long-context approaches")
print(answer2)

# Check loaded papers
loaded = agent.get_loaded_papers()
print(f"Papers loaded: {list(loaded.keys())}")

# Reset for new conversation
agent.reset_papers()
```

### Manual Paper Loading

```python
# Preload specific papers
agent.add_paper("2409.05591")
agent.add_paper("2504.21776")

# Then query
answer = agent.query("Compare these two papers")
```

### Use Different LLMs

```python
# DeepSeek
agent = Agent(
    api_key="your_deepseek_key",
    base_url="https://api.deepseek.com/v1",
    model="deepseek-chat"
)

# OpenRouter
agent = Agent(
    api_key="your_openrouter_key",
    base_url="https://openrouter.ai/api/v1",
    model="openai/gpt-4"
)

# Local Ollama
agent = Agent(
    api_key="ollama",  # dummy key
    base_url="http://localhost:11434/v1",
    model="llama2"
)
```

## Best Practices

### 1. Use Appropriate Loading Strategy

```python
# ❌ Bad: Always load full papers
for arxiv_id in search_results:
    content = reader.raw(arxiv_id)  # Wastes tokens!

# ✅ Good: Progressive loading
for arxiv_id in search_results:
    brief = reader.brief(arxiv_id)  # Quick filter
    if is_relevant(brief):
        content = reader.raw(arxiv_id)  # Load only relevant ones
```

### 2. Cache Results

```python
import json
from pathlib import Path

cache_file = Path("paper_cache.json")
cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}

def get_paper_cached(arxiv_id):
    if arxiv_id in cache:
        return cache[arxiv_id]

    paper = reader.head(arxiv_id)
    cache[arxiv_id] = paper
    cache_file.write_text(json.dumps(cache))
    return paper
```

### 3. Handle Large Search Results

```python
# Stream process results instead of loading all at once
def search_and_process(query, callback):
    offset = 0
    while True:
        results = reader.search(query, size=100, offset=offset)
        if not results['results']:
            break

        for paper in results['results']:
            callback(paper)  # Process each paper

        offset += 100

search_and_process("reinforcement learning", process_paper_func)
```

### 4. Enable Logging

```python
import logging

# Enable deepxiv logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('deepxiv_sdk')
logger.setLevel(logging.DEBUG)

# Now you'll see deepxiv debug info
reader = Reader()
results = reader.search("agent")  # Outputs logs
```

## Troubleshooting

### Issue: Token Expired

**Symptom**: `AuthenticationError: Invalid or expired token`

**Solution**:
```bash
deepxiv config --token YOUR_NEW_TOKEN
```

### Issue: Rate Limit

**Symptom**: `RateLimitError: Daily limit reached`

**Solution**:
- Wait until tomorrow (daily reset)
- Or contact tommy@chien.io for higher limit

### Issue: Network Timeout

**Symptom**: `APIError: Request timed out after 3 retries`

**Solution**:
```python
# Increase timeout and retry count
reader = Reader(timeout=180, max_retries=5)
```

### Issue: Paper Not Found

**Symptom**: `NotFoundError: Paper not found`

**Solution**:
- Check arXiv ID format (should be like `2409.05591`)
- Verify paper exists at https://arxiv.org

### Issue: Empty Search Results

**Symptom**: `No papers found matching 'query'`

**Solution**:
- Try different keywords
- Remove restrictive filters
- Check category codes are correct

## Environment Variables

Control deepxiv behavior with environment variables:

```bash
# API Token
export DEEPXIV_TOKEN="your_token"

# LLM API keys (for agent)
export DEEPXIV_AGENT_API_KEY="your_api_key"
export DEEPXIV_AGENT_BASE_URL="https://api.example.com"
export DEEPXIV_AGENT_MODEL="gpt-4"

# Enable debug logging
export DEEPXIV_DEBUG=1
```

## Performance Optimization

### Skip Fine Reranking

```python
# Default: fine reranking off — fastest and cheapest
results = reader.search("agents")

# Better ordering, extra upstream latency
results = reader.search("agents", use_fine_rerank=True)
```

### Limit Search Scope

```python
# Faster search
results = reader.search(
    "transformers",
    size=10,                           # Only top 10
    categories=["cs.CL", "cs.AI"],     # Limit categories
    date_from="2024-01-01"             # Recent papers only
)
```

---

Have questions or suggestions? [Open an issue on GitHub](https://github.com/qhjqhj00/deepxiv_sdk/issues)
