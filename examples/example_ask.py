"""
Agentic search examples: one question in, a cited answer out.

The service picks its own tools and reads sources when it needs to — arXiv paper
sections on the arXiv backend, cached page bodies on the web backend. No LLM key
needed; inference runs server-side.

Requires a REGISTERED key from https://data.rag.ac.cn/register — the token the
SDK auto-registers on first use returns 403. Each account gets 30 agentic calls
per day free, from a pool separate from the general daily limit. This file makes
five calls in total.

Run:
    python examples/example_ask.py
"""
from deepxiv_sdk import (
    Reader,
    agent_search_sources,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)


def blocking_example(reader):
    """Simplest form: wait for the whole answer (8~28s)."""
    print("=" * 70)
    print("1. Blocking")
    print("=" * 70)

    result = reader.agent_search(
        "what speedup does speculative decoding report on HumanEval"
    )

    print(result["answer"])

    # `sources` is the retrieval set — a superset of what the answer cites.
    sources = agent_search_sources(result)
    print(f"\nRetrieved {len(sources)} papers. Cited:")
    for paper in sources:
        if paper["arxiv_id"] in result["answer"]:
            print(f"  [{paper['arxiv_id']}] {paper['title']}")

    print(f"\nQuota: {result['quota']['remaining']} calls left "
          f"on the '{result['quota']['tier']}' tier")

    if result["stats"]["answer_truncated"]:
        print("\n⚠️  Truncated — raise max_answer_tokens or narrow the query.")


def streaming_example(reader):
    """First token lands in ~3~4s at effort='default'."""
    print("\n" + "=" * 70)
    print("2. Streaming")
    print("=" * 70)

    chunks, sources, truncated = [], [], False

    for event in reader.agent_search_stream(
        "what compression ratio does KV cache eviction report on LongBench"
    ):
        name = event["event"]
        if name == "answer_delta":
            chunks.append(event["text"])
            print(event["text"], end="", flush=True)
        elif name == "sources":
            sources = agent_search_sources(event)
        elif name == "done":
            truncated = event["answer_truncated"]
            print(f"\n\n[first token at {event['ttfa_ms']}ms, "
                  f"total {event['elapsed_ms']}ms]")
        elif name == "error":
            # Yielded, not raised — a partial answer may already be printed.
            print(f"\n❌ {event['stage']}: {event['message']}")
            return

    answer = "".join(chunks)
    cited = [p for p in sources if p["arxiv_id"] in answer]
    print(f"Cited {len(cited)} of {len(sources)} retrieved papers.")
    if truncated:
        print("⚠️  Truncated — raise max_answer_tokens or narrow the query.")


def verbose_example(reader):
    """verbose=True exposes the tool calls the service makes along the way."""
    print("\n" + "=" * 70)
    print("3. Verbose — watching it work")
    print("=" * 70)

    for event in reader.agent_search_stream(
        "对比几种缓解 MoE 路由崩塌的方法",  # Chinese works directly
        effort="high",
        verbose=True,
    ):
        name = event["event"]
        if name == "tool_call":
            print(f"🔧 round {event['round']}: {event['name']}({event['arguments']})")
        elif name == "tool_result":
            print(f"   └─ {event['summary']} ({event['elapsed_ms']}ms)")
        elif name == "warning":
            print(f"⚠️  [{event['stage']}] {event['message']}")
        elif name == "answer_delta":
            print(event["text"], end="", flush=True)
    print()


def web_example(reader):
    """The web backend: same protocol, different sources — and weaker evidence.

    The service reads only *cached* page bodies and never fetches live, so an
    uncached page contributes just its search snippet. `read` tells them apart.
    """
    print("\n" + "=" * 70)
    print("4. Web backend")
    print("=" * 70)

    result = reader.agent_search(
        "what are the pricing tiers for the Anthropic Claude API",
        source="web",
    )
    print(result["answer"][:600], "...\n")

    for page in agent_search_sources(result):
        if page["url"] in result["answer"]:
            strength = "read in full" if page.get("read") else "snippet only"
            print(f"  [{strength}] {page['title']}\n    {page['url']}")


def error_handling_example(reader):
    """Arguments are validated locally, so bad calls cost nothing."""
    print("\n" + "=" * 70)
    print("5. Error handling")
    print("=" * 70)

    # Caught client-side — no request, no quota spent.
    for bad in [{"query": ""},
                {"query": "ok", "effort": "ultra"},
                {"query": "ok", "top_k": 99},
                {"query": "ok", "max_answer_tokens": 100},
                # Backend-specific flags are rejected, not silently dropped:
                {"query": "ok", "source": "web", "top_k": 10},
                {"query": "ok", "search_type": "news"}]:
        try:
            reader.agent_search(**bad)
        except ValueError as e:
            print(f"  rejected locally: {e}")

    # These do reach the server.
    try:
        reader.agent_search("a genuinely obscure question about nothing")
    except AuthenticationError as e:
        # 403 lands here too: a valid SDK token without agentic access.
        print(f"  auth: {e}")
    except RateLimitError:
        # Never auto-retried — each call spends a quota unit, so backoff is yours.
        print("  agentic quota exhausted — retry tomorrow")
    except BadRequestError as e:
        print(f"  server rejected the request: {e}")


if __name__ == "__main__":
    reader = Reader()  # token auto-loaded from ~/.env

    blocking_example(reader)
    streaming_example(reader)
    verbose_example(reader)
    web_example(reader)
    error_handling_example(reader)
