"""
Command-line interface for deepxiv.
"""
import json
import os
import sys
import click
import requests
from pathlib import Path
from typing import Any
from uuid import uuid4
from .reader import (
    Reader,
    agent_search_sources,
    APIError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    # Load from home directory first (global config), then current directory (project config)
    # Later files override earlier ones
    env_paths = [
        Path.home() / ".env",  # Home directory (global)
        Path.cwd() / ".env",   # Current directory (project-specific, can override global)
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path, override=False)  # Don't override already set env vars
except ImportError:
    # python-dotenv not installed, skip loading .env file
    pass


DEFAULT_BASE_URL = "https://data.rag.ac.cn"
REGISTER_ENDPOINT = f"{DEFAULT_BASE_URL}/api/register"
SDK_REGISTER_ENDPOINT = f"{DEFAULT_BASE_URL}/api/register/sdk"
DEFAULT_DAILY_LIMIT = 10000
# Shared secret for SDK auto-registration (no SMS required).
# Must match SDK_REGISTRATION_SECRET on the server.
_SDK_SECRET = "UuZp0i83svQU7_naUEexczc-X3NWv7lvNkD8e3sPyng"


def get_token(token_option):
    """Get token from option or environment variable."""
    if token_option:
        return token_option
    return os.environ.get("DEEPXIV_TOKEN")


def _upsert_env_value(env_file: Path, key: str, value: str):
    """Insert or update a key=value pair in an env file."""
    env_line = f"{key}={value}\n"

    if env_file.exists():
        with open(env_file, "r") as f:
            lines = f.readlines()

        key_exists = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = env_line
                key_exists = True
                break

        if not key_exists:
            lines.append(env_line)

        with open(env_file, "w") as f:
            f.writelines(lines)
    else:
        with open(env_file, "w") as f:
            f.write(env_line)


def save_token(token: str, is_global: bool = True) -> Path:
    """Persist DEEPXIV_TOKEN to the selected env file."""
    env_file = Path.home() / ".env" if is_global else Path.cwd() / ".env"
    _upsert_env_value(env_file, "DEEPXIV_TOKEN", token)
    os.environ["DEEPXIV_TOKEN"] = token
    return env_file


def generate_registration_payload() -> dict:
    """Generate random registration data for automatic token provisioning."""
    suffix = uuid4().hex[:10]
    return {
        "sdk_secret": _SDK_SECRET,
        "name": f"deepxiv_{suffix}",
        "email": f"{suffix}@example.com",
    }


def auto_register_token() -> tuple[str | None, int | None]:
    """Automatically register for a token and persist it."""
    payload = generate_registration_payload()

    try:
        response = requests.post(SDK_REGISTER_ENDPOINT, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.RequestException as e:
        click.echo(f"\n❌ Failed to auto-register DEEPXIV token: {e}\n", err=True)
        return None, None
    except ValueError as e:
        click.echo(f"\n❌ Failed to parse registration response: {e}\n", err=True)
        return None, None

    if not result.get("success"):
        click.echo("\n❌ Failed to auto-register DEEPXIV token.\n", err=True)
        message = result.get("message", "Unknown error")
        click.echo(f"Server message: {message}\n", err=True)
        return None, None

    data = result.get("data", {})
    token = data.get("token")
    daily_limit = data.get("daily_limit", DEFAULT_DAILY_LIMIT)
    if not token:
        click.echo("\n❌ Registration succeeded but no token was returned.\n", err=True)
        return None, None

    env_file = save_token(token, is_global=True)
    click.echo(f"已自动申请 token，并已保存到 {env_file}")
    click.echo(f"当前 daily limit: {daily_limit}\n")
    return token, daily_limit


def ensure_token(token_option=None, auto_create: bool = True):
    """Get an existing token or auto-create one on first use."""
    token = get_token(token_option)
    if token:
        return token

    if not auto_create:
        return None

    token, _ = auto_register_token()
    return token


def check_token_and_warn(token):
    """Check if token is configured and warn if not."""
    if not token:
        click.echo("⚠️  Warning: DEEPXIV_TOKEN not configured.", err=True)
        click.echo("   Some features may not work without authentication.\n", err=True)
        click.echo("   Get your free token at: https://data.rag.ac.cn/register", err=True)
        click.echo("   Then configure it with: deepxiv config\n", err=True)
        return False
    return True


def handle_auth_error():
    """Handle authentication errors with helpful message."""
    click.echo("\n❌ 认证失败（401 Unauthorized） / Authentication failed (401 Unauthorized)\n", err=True)
    click.echo("当前 API token 缺失或无效。 / Your API token is missing or invalid.\n", err=True)
    click.echo("你可以重新运行任意 deepxiv 命令自动注册新 token。 / Try running any deepxiv command again to auto-register a new token.", err=True)
    click.echo("或手动设置：export DEEPXIV_TOKEN=your_token / Or set it directly: export DEEPXIV_TOKEN=your_token", err=True)
    click.echo("使用 `deepxiv token` 查看当前 token。 / Use `deepxiv token` to inspect the current token.\n", err=True)


def handle_rate_limit_error():
    """Handle daily limit errors with a friendly message."""
    click.echo("\n❌ 当前 token 已到日使用上限。 / Your token has reached its daily usage limit.\n", err=True)
    click.echo("请访问 https://data.rag.ac.cn/register 注册，以获得更高 limit。 / Visit https://data.rag.ac.cn/register to get a higher limit.\n", err=True)


def handle_bad_request_error(command_name="command"):
    """Handle invalid requests with command-specific hints."""
    click.echo("\n❌ 请求参数有误。 / Invalid request arguments.\n", err=True)

    if command_name == "paper":
        click.echo("`deepxiv paper` 需要传入 arXiv ID，例如 `2409.05591`。 / `deepxiv paper` expects an arXiv ID such as `2409.05591`.\n", err=True)
        click.echo("如果你输入的是关键词，请先使用 `deepxiv search \"keyword\"` 查到论文 ID 再读取。 / If you entered a keyword, use `deepxiv search \"keyword\"` first to find the paper ID.\n", err=True)
    elif command_name == "pmc":
        click.echo("`deepxiv pmc` 需要传入 PMC ID，例如 `PMC544940`。 / `deepxiv pmc` expects a PMC ID such as `PMC544940`.\n", err=True)
    elif command_name == "search":
        click.echo("请检查搜索关键词和筛选参数是否正确。 / Please check your search query and filters.\n", err=True)
    elif command_name == "ask":
        click.echo("`deepxiv ask` 的问题需在 1~2000 字符之间。 / `deepxiv ask` needs a query of 1~2000 characters.\n", err=True)
    elif command_name in ("biorxiv", "medrxiv"):
        click.echo(f"`deepxiv {command_name}` 需要传入 DOI，例如 `10.1101/2021.02.26.433129`。 / `deepxiv {command_name}` expects a DOI such as `10.1101/2021.02.26.433129`.\n", err=True)
    else:
        click.echo("请检查命令参数、论文 ID 或筛选条件是否正确。 / Please check your command arguments, paper ID, or filters.\n", err=True)


def exit_on_reader_error(error, command_name="command"):
    """Print a friendly message for an API exception, then exit non-zero."""
    if isinstance(error, BadRequestError):
        handle_bad_request_error(command_name)
    elif isinstance(error, AuthenticationError):
        handle_auth_error()
    elif isinstance(error, RateLimitError):
        handle_rate_limit_error()
    else:
        click.echo(f"\n❌ Error: {error}\n", err=True)
    sys.exit(1)


def run_reader_call(fn, command_name="command"):
    """Run a reader call and convert API exceptions into friendly CLI output."""
    try:
        return fn()
    except APIError as e:
        exit_on_reader_error(e, command_name)


def get_agent_config():
    """Get agent LLM configuration from environment or config file."""
    config = {}
    
    # Try environment variables first
    config["api_key"] = os.environ.get("DEEPXIV_AGENT_API_KEY")
    config["base_url"] = os.environ.get("DEEPXIV_AGENT_BASE_URL")
    config["model"] = os.environ.get("DEEPXIV_AGENT_MODEL")
    
    # If not in env, try to load from config file
    if not config["api_key"]:
        config_file = Path.home() / ".deepxiv_agent_config.json"
        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    file_config = json.load(f)
                    config["api_key"] = config["api_key"] or file_config.get("api_key")
                    config["base_url"] = config["base_url"] or file_config.get("base_url")
                    config["model"] = config["model"] or file_config.get("model", "gpt-4")
            except Exception:
                pass
    return config


def save_agent_config(api_key, base_url=None, model="gpt-4"):
    """Save agent LLM configuration to config file."""
    config_file = Path.home() / ".deepxiv_agent_config.json"
    config = {
        "api_key": api_key,
        "base_url": base_url,
        "model": model
    }
    
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)
    
    click.echo(f"✅ Agent configuration saved to {config_file}")
    click.echo("   This file stays on your local machine only.")


def check_agent_config():
    """Check if agent is configured and warn if not."""
    config = get_agent_config()
    if not config.get("api_key"):
        click.echo("⚠️  Warning: Agent LLM API not configured.", err=True)
        click.echo("   Please configure it with: deepxiv agent config\n", err=True)
        return False
    return True


@click.group()
@click.version_option()
def main():
    """deepxiv - Access arXiv papers from the command line.

    Set token via --token option or DEEPXIV_TOKEN environment variable.
    """
    pass


@main.command()
@click.argument("query")
@click.option("--token", "-t", default=None, envvar="DEEPXIV_TOKEN", help="API token (or set DEEPXIV_TOKEN env var)")
@click.option("--limit", "-l", default=10, help="Number of results (1~100, default: 10). Maps to upstream top_k.")
@click.option("--offset", default=0, type=int, help="Pagination offset (0~10000, default: 0)")
@click.option("--format", "-f", "output_format", default="text", type=click.Choice(["text", "json"]),
              help="Output format (default: text)")
@click.option("--categories", "-c", default=None, help="Filter by categories (comma-separated, e.g., cs.AI,cs.CL)")
@click.option("--authors", "authors_opt", default=None, help="Filter by authors (comma-separated)")
@click.option("--orgs", "orgs_opt", default=None, help="Filter by organizations (comma-separated)")
@click.option("--venue", "venue_opt", multiple=True,
              help="Filter by publication venue; repeatable (e.g. --venue NeurIPS --venue ICLR). "
                   "Aliases match automatically (NeurIPS ↔ NIPS).")
@click.option("--venue-year", default=None, type=int, help="Filter by conference/venue year (e.g. 2025)")
@click.option("--min-citations", default=None, type=int, help="Minimum citation count")
@click.option("--date-from", default=None, help="Publication date from (YYYY / YYYY-MM / YYYY-MM-DD)")
@click.option("--date-to", default=None, help="Publication date to (YYYY / YYYY-MM / YYYY-MM-DD)")
@click.option("--date-search-type", default=None, type=click.Choice(["between", "exact", "after", "before"]),
              help="Advanced date filter mode (overrides --date-from/--date-to mapping)")
@click.option("--date-str", "date_str_opt", default=None, multiple=True,
              help="Date string for --date-search-type. Use twice for 'between' (start, end).")
@click.option("--use-fine-rerank", is_flag=True, default=False,
              help="Enable upstream fine reranking (default: disabled)")
@click.option("--biorxiv", "source", flag_value="biorxiv", default=False, help="Search bioRxiv preprints")
@click.option("--medrxiv", "source", flag_value="medrxiv", default=False, help="Search medRxiv preprints")
def search(query, token, limit, offset, output_format, categories, authors_opt, orgs_opt,
           venue_opt, venue_year, min_citations, date_from, date_to, date_search_type,
           date_str_opt, use_fine_rerank, source):
    """Search papers across arXiv (default), bioRxiv, or medRxiv.

    The CLI uses the unified retrieve endpoint and routes all three sources
    through ``reader.search()``.

    Examples:
        deepxiv search "agent memory" --limit 5
        deepxiv search "transformer" --format json
        deepxiv search "diffusion model" --venue NeurIPS --venue-year 2025
        deepxiv search "language model" --venue NeurIPS --venue ICLR
        deepxiv search "protein design" --biorxiv --limit 5
        deepxiv search "Alzheimer" --medrxiv --date-from 2024-01
        deepxiv search "image generation" --date-search-type between \
            --date-str 2025-06-01 --date-str 2025-07-01
    """
    token = ensure_token(token)
    if not token:
        sys.exit(1)

    reader = Reader(token=token)

    cat_list = [c.strip() for c in categories.split(",")] if categories else None
    auth_list = [a.strip() for a in authors_opt.split(",")] if authors_opt else None
    orgs_list = [o.strip() for o in orgs_opt.split(",")] if orgs_opt else None
    venue_list = list(venue_opt) if venue_opt else None

    resolved_source = source if source in ("biorxiv", "medrxiv") else "arxiv"

    # Translate --date-str repeats: single string for non-between, list for between.
    date_str_value: Any = None
    if date_str_opt:
        date_str_list = list(date_str_opt)
        if date_search_type == "between":
            date_str_value = date_str_list
        else:
            date_str_value = date_str_list[0] if len(date_str_list) == 1 else date_str_list

    results = run_reader_call(
        lambda: reader.search(
            query=query,
            size=limit,
            offset=offset,
            source=resolved_source,
            categories=cat_list,
            authors=auth_list,
            orgs=orgs_list,
            venue=venue_list,
            venue_year=venue_year,
            min_citation=min_citations,
            date_search_type=date_search_type,
            date_str=date_str_value,
            date_from=date_from,
            date_to=date_to,
            use_fine_rerank=use_fine_rerank,
        ),
        command_name="search",
    )

    if not results:
        handle_auth_error()
        sys.exit(1)

    if output_format == "json":
        click.echo(json.dumps(results, indent=2, ensure_ascii=False))
        return

    result_list = results.get("result", [])
    total = results.get("total_count", len(result_list))
    label = {"arxiv": "arXiv", "biorxiv": "bioRxiv", "medrxiv": "medRxiv"}[resolved_source]
    id_field = f"{resolved_source}_id"

    click.echo(f"\nFound {total} {label} papers for '{query}' (showing {len(result_list)}):\n")

    for i, paper in enumerate(result_list, 1):
        paper_id = paper.get(id_field) or paper.get("arxiv_id") or paper.get("biorxiv_id") \
            or paper.get("medrxiv_id") or "Unknown"
        title = paper.get("title", "No title")
        abstract = (paper.get("abstract") or paper.get("tldr") or "")[:200]
        score = paper.get("score", 0) or 0
        citations = paper.get("citation_count", paper.get("citation", 0))
        date = paper.get("date") or paper.get("publish_at") or "N/A"

        click.echo(f"{i}. {title}")
        try:
            click.echo(
                f"   {label}: {paper_id} | Score: {score:.3f} | "
                f"Citations: {citations} | Date: {date}"
            )
        except (TypeError, ValueError):
            click.echo(
                f"   {label}: {paper_id} | Score: {score} | "
                f"Citations: {citations} | Date: {date}"
            )
        if paper.get("venue"):
            venue_line = f"   Venue: {paper.get('venue')}"
            if paper.get("venue_year"):
                venue_line += f" ({paper.get('venue_year')})"
            click.echo(venue_line)
        if abstract:
            click.echo(f"   {abstract}...")
        click.echo()


@main.command()
@click.argument("query")
@click.option("--token", "-t", default=None, envvar="DEEPXIV_TOKEN", help="API token (or set DEEPXIV_TOKEN env var)")
@click.option("--web", "-w", "use_web", is_flag=True,
              help="Search the web (Google + cached page bodies) instead of arXiv")
@click.option("--effort", "-e", default="default", type=click.Choice(["default", "high", "xhigh"]),
              help="Evidence-gathering depth. default: 1~2 rounds (~3~4s to first token on "
                   "arXiv, ~5~9s on web). high: 3 rounds. xhigh: 4~5 rounds. (default: default)")
@click.option("--verbose", "-v", is_flag=True, help="Show tool calls and progress on stderr while streaming")
@click.option("--json", "json_output", is_flag=True, help="Emit one JSON object instead of streaming text")
@click.option("--no-stream", is_flag=True, help="Wait for the full answer instead of streaming it")
@click.option("--top-k", default=None, type=click.IntRange(1, 30),
              help="arXiv only: first-round retrieval size (1~30, default: 10)")
@click.option("--search-type", default=None,
              type=click.Choice(["search", "scholar", "news", "images"]),
              help="--web only: Google vertical (default: search). Use news for "
                   "time-sensitive questions, scholar for non-arXiv academic sources.")
@click.option("--gl", default=None, help="--web only: Google country code (e.g. us, cn)")
@click.option("--hl", default=None, help="--web only: Google UI language (e.g. en, zh-cn)")
@click.option("--max-answer-tokens", default=4096, type=click.IntRange(256, 16384),
              help="Hard cap on answer length (256~16384, default: 4096)")
@click.option("--language", default=None, help="Answer language (default: follows the query's language)")
@click.option("--no-sources", is_flag=True, help="Skip the sources list")
@click.option("--all-sources", is_flag=True,
              help="List every retrieved source, not just the ones the answer cites")
def ask(query, token, use_web, effort, verbose, json_output, no_stream, top_k,
        search_type, gl, hl, max_answer_tokens, language, no_sources, all_sources):
    """Ask a question and get an answer with real citations.

    Searches arXiv by default; pass --web to search the web instead. The service
    picks its own tools, reads sources when it needs to, and cites what it used.

    Requires a registered account key (https://data.rag.ac.cn/register) — the
    token deepxiv auto-registers on first use is not eligible. Agentic calls draw
    on a separate daily quota (free 30 / lite 500 / premium 10000) and do not
    consume your general daily limit.

    Which one to use:

    \b
      arXiv (default)  methods, numbers, experimental results from papers
      --web            current events, products, companies, anything non-academic
      --web --search-type scholar   academic sources beyond arXiv

    Be specific — "what compression ratio does KV cache eviction report on
    LongBench" works far better than "kv cache". Chinese queries work directly.
    If results miss, rephrasing beats raising --effort.

    The answer goes to stdout and progress to stderr, so redirection stays clean:

        deepxiv ask "test-time compute scaling laws" > answer.md

    Examples:
        deepxiv ask "what speedup does speculative decoding report on HumanEval"
        deepxiv ask "对比 MoE 路由崩塌的几种缓解方法" --effort high
        deepxiv ask "latest Claude model pricing" --web
        deepxiv ask "who won the NeurIPS 2025 best paper" --web --search-type news
        deepxiv ask "state space models vs transformers" --json
    """
    source = "web" if use_web else "arxiv"

    # Reject cross-backend flags here: the service silently ignores them, which
    # would look like the flag worked.
    misplaced = []
    if use_web and top_k is not None:
        misplaced.append("--top-k is arXiv-only")
    if not use_web:
        for flag, value in (("--search-type", search_type), ("--gl", gl), ("--hl", hl)):
            if value is not None:
                misplaced.append(f"{flag} requires --web")
    if misplaced:
        for problem in misplaced:
            click.echo(f"❌ {problem}", err=True)
        sys.exit(2)

    token = ensure_token(token)
    if not token:
        sys.exit(1)

    reader = Reader(token=token)
    backend_kwargs = (
        {"search_type": search_type, "gl": gl, "hl": hl} if use_web
        else {"top_k": top_k}
    )

    # --json needs the whole payload anyway, so use the blocking endpoint.
    if json_output or no_stream:
        result = run_reader_call(
            lambda: reader.agent_search(
                query=query,
                source=source,
                effort=effort,
                max_answer_tokens=max_answer_tokens,
                language=language,
                **backend_kwargs,
            ),
            command_name="ask",
        )
        if json_output:
            click.echo(json.dumps(result, indent=2, ensure_ascii=False))
            return

        answer_text = result.get("answer", "")
        click.echo(answer_text)
        _print_ask_sources(
            agent_search_sources(result), no_sources, answer_text,
            all_sources, source,
        )
        _print_ask_quota(result.get("quota"), verbose)
        if (result.get("stats") or {}).get("answer_truncated"):
            click.echo(
                "\n⚠️  Answer was truncated — raise --max-answer-tokens or narrow the query.",
                err=True,
            )
        return

    sources = []
    answer_chunks = []
    quota = None
    truncated = False
    saw_answer = False
    try:
        for event in reader.agent_search_stream(
            query=query,
            source=source,
            effort=effort,
            verbose=verbose,
            max_answer_tokens=max_answer_tokens,
            language=language,
            **backend_kwargs,
        ):
            name = event.get("event")

            if name in ("answer_delta", "answer"):
                saw_answer = True
                text = event.get("text", "")
                answer_chunks.append(text)
                click.echo(text, nl=False)
            elif name == "sources":
                sources = agent_search_sources(event)
            elif name == "billing":
                quota = event
            elif name == "done":
                truncated = bool(event.get("answer_truncated"))
            elif name == "error":
                click.echo(
                    f"\n\n❌ Error during {event.get('stage', 'unknown')} stage: "
                    f"{event.get('message', 'unknown error')}\n",
                    err=True,
                )
                sys.exit(1)
            elif name == "warning" and verbose:
                click.echo(f"⚠️  [{event.get('stage', '?')}] {event.get('message', '')}", err=True)
            elif name == "tool_call" and verbose:
                args = event.get("arguments") or {}
                click.echo(f"🔧 round {event.get('round')} {event.get('name')}({json.dumps(args, ensure_ascii=False)[:120]})", err=True)
            elif name == "tool_result" and verbose:
                status = "ok" if event.get("ok") else "failed"
                click.echo(
                    f"   └─ {status} in {event.get('elapsed_ms')}ms: {event.get('summary', '')}",
                    err=True,
                )
            elif name == "start" and verbose:
                click.echo(
                    f"🔍 run {event.get('run_id')} | model {event.get('model')} "
                    f"| effort {event.get('effort')} | max {event.get('max_rounds')} rounds",
                    err=True,
                )
    except APIError as e:
        # Flush any partial answer before the error message goes to stderr.
        if saw_answer:
            click.echo()
        exit_on_reader_error(e, command_name="ask")

    click.echo()
    _print_ask_sources(
        sources, no_sources, "".join(answer_chunks), all_sources, source
    )
    _print_ask_quota(quota, verbose)
    if truncated:
        click.echo(
            "\n⚠️  Answer was truncated — raise --max-answer-tokens or narrow the query.",
            err=True,
        )


def _ask_source_is_cited(item, answer_text, source):
    """Was this source actually referenced in the answer?"""
    if source == "web":
        url = item.get("url")
        return bool(url) and url in answer_text
    arxiv_id = item.get("arxiv_id")
    return bool(arxiv_id) and arxiv_id in answer_text


def _print_ask_sources(sources, no_sources, answer_text="", show_all=False,
                       source="arxiv"):
    """Print the sources list to stderr so stdout stays answer-only.

    The service returns everything it retrieved, which is a superset of what the
    answer actually cites — a 10-source retrieval can end up supporting a single
    citation. Narrow to the ones referenced in the answer, unless the caller
    asked for the full retrieval set or nothing matched.
    """
    if no_sources or not sources:
        return

    cited = [s for s in sources if _ask_source_is_cited(s, answer_text, source)]
    if show_all or not cited:
        shown, label = sources, "retrieved"
    else:
        shown, label = cited, "cited"

    header = f"\n📚 Sources ({len(shown)} {label}"
    if label == "cited" and len(sources) > len(shown):
        header += f", {len(sources)} retrieved — use --all-sources for the rest"
    click.echo(header + "):", err=True)

    for i, item in enumerate(shown, 1):
        if source == "web":
            # `read` marks pages whose body the model actually read; the rest
            # only contributed a search snippet, which is weaker evidence.
            mark = "📄" if item.get("read") else "🔗"
            click.echo(f"  {i}. {mark} {item.get('title', '')}", err=True)
            click.echo(f"     {item.get('url', '')}", err=True)
        else:
            arxiv_id = item.get("arxiv_id", "?")
            click.echo(f"  {i}. [{arxiv_id}] {item.get('title', '')}", err=True)
            click.echo(
                f"     {item.get('url') or f'https://arxiv.org/abs/{arxiv_id}'}",
                err=True,
            )

    if source == "web" and any(not s.get("read") for s in shown):
        click.echo(
            "     🔗 = search snippet only (not read in full) — weaker evidence",
            err=True,
        )


def _print_ask_quota(quota, verbose=False):
    """Report remaining agentic quota; always warn when it is nearly gone."""
    if not quota:
        return
    remaining = quota.get("remaining")
    if remaining is None:
        return
    tier = quota.get("tier", "?")
    if remaining <= 5:
        click.echo(
            f"\n⚠️  {remaining} agentic call(s) left today on the '{tier}' tier. "
            "Upgrade at https://data.rag.ac.cn/register",
            err=True,
        )
    elif verbose:
        click.echo(
            f"\n💳 tier={tier} used={quota.get('used')} remaining={remaining}",
            err=True,
        )


@main.command()
@click.argument("arxiv_id")
@click.option("--token", "-t", default=None, envvar="DEEPXIV_TOKEN", help="API token (or set DEEPXIV_TOKEN env var)")
@click.option("--format", "-f", "output_format", default="markdown", type=click.Choice(["markdown", "json"]),
              help="Output format (default: markdown)")
@click.option("--section", "-s", default=None, help="Get a specific section by name")
@click.option("--preview", "-p", is_flag=True, help="Get only a preview (first ~10k chars)")
@click.option("--head", is_flag=True, help="Get paper metadata (returns JSON)")
@click.option("--brief", "-b", is_flag=True, help="Get brief info (title, TLDR, keywords, citations, GitHub URL)")
@click.option("--raw", is_flag=True, help="Get raw markdown content")
@click.option("--popularity", is_flag=True, help="Get social impact metrics (trending signal)")
@click.option("--biorxiv", "bio_source", flag_value="biorxiv", default=False, help="Treat ID as bioRxiv DOI")
@click.option("--medrxiv", "bio_source", flag_value="medrxiv", default=False, help="Treat ID as medRxiv DOI")
def paper(arxiv_id, token, output_format, section, preview, head, brief, raw, popularity, bio_source):
    """Get an arXiv paper by ID (or bioRxiv/medRxiv paper with --biorxiv/--medrxiv).

    Example:
        deepxiv paper 2409.05591
        deepxiv paper 2409.05591 --brief
        deepxiv paper 2409.05591 --section Introduction
        deepxiv paper 10.1101/2021.02.26.433129 --biorxiv
        deepxiv paper 10.1101/2021.02.26.433129 --biorxiv --section Introduction
        deepxiv paper 10.1101/2025.08.11.25333149 --medrxiv
    """
    # ── bioRxiv / medRxiv via --biorxiv / --medrxiv flag ─────────────────────
    if bio_source in ("biorxiv", "medrxiv"):
        token = ensure_token(token)
        if not token:
            sys.exit(1)
        reader = Reader(token=token)
        if section:
            data_type = "section"
            section_names = [s.strip() for s in section.split(",")]
        else:
            data_type = "metadata"
            section_names = None

        result = run_reader_call(
            lambda: reader.biomed_data(
                source_id=arxiv_id,
                source=bio_source,
                data_type=data_type,
                section_names=section_names,
            ),
            command_name=bio_source,
        )
        if not result:
            handle_auth_error()
            sys.exit(1)

        if output_format == "json" or data_type == "section":
            click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _print_biomed_metadata(result, "bioRxiv" if bio_source == "biorxiv" else "medRxiv")
        return
    
    # Handle --popularity flag (requires token)
    if popularity:
        token = get_token(token)
        if not token:
            check_token_and_warn(token)
            return

        reader = Reader(token=token)
        try:
            impact = run_reader_call(lambda: reader.social_impact(arxiv_id), command_name="paper")

            if output_format == "json":
                if impact:
                    click.echo(json.dumps(impact, indent=2))
                else:
                    click.echo(json.dumps({"arxiv_id": arxiv_id, "data": None}, indent=2))
            else:
                if impact:
                    click.echo(f"\n📱 Social Impact Metrics for arXiv:{arxiv_id}\n")
                    click.echo(f"  📊 Views:     {impact.get('total_views', 'N/A')}")
                    click.echo(f"  🐦 Tweets:    {impact.get('total_tweets', 'N/A')}")
                    click.echo(f"  👍 Likes:     {impact.get('total_likes', 'N/A')}")
                    click.echo(f"  💬 Replies:   {impact.get('total_replies', 'N/A')}")
                    click.echo(f"\n  📅 First seen: {impact.get('first_seen_date', 'N/A')}")
                    click.echo(f"  📅 Last seen:  {impact.get('last_seen_date', 'N/A')}\n")
                else:
                    click.echo(f"ℹ️  No social impact data found for arXiv:{arxiv_id}")
                    click.echo("   This paper may be too old or not mentioned on social media.\n")
        except Exception as e:
            click.echo(f"❌ Error: {e}", err=True)
            sys.exit(1)
        return

    token = ensure_token(token)
    if not token:
        sys.exit(1)

    reader = Reader(token=token)

    if head:
        # Get paper metadata
        result = run_reader_call(lambda: reader.head(arxiv_id), command_name="paper")
        if not result:
            handle_auth_error()
            sys.exit(1)
        click.echo(json.dumps(result, indent=2))

    elif brief:
        # Get brief information
        result = run_reader_call(lambda: reader.brief(arxiv_id), command_name="paper")
        if not result:
            handle_auth_error()
            sys.exit(1)
        
        if output_format == "json":
            click.echo(json.dumps(result, indent=2))
        else:
            # Pretty print brief info
            click.echo(f"\n📄 {result.get('title', 'No title')}\n")
            click.echo(f"🆔 arXiv: {result.get('arxiv_id', arxiv_id)}")
            click.echo(f"📅 Published: {result.get('publish_at', 'N/A')}")
            click.echo(f"📊 Citations: {result.get('citations', 0)}")
            click.echo(f"🔗 PDF: {result.get('src_url', 'N/A')}")
            if result.get("github_url"):
                click.echo(f"💻 GitHub: {result.get('github_url')}")
            
            if result.get('keywords'):
                keywords = result.get('keywords', [])
                if isinstance(keywords, list):
                    click.echo(f"\n🏷️  Keywords: {', '.join(keywords)}")
                else:
                    click.echo(f"\n🏷️  Keywords: {keywords}")
            
            if result.get('tldr'):
                click.echo(f"\n💡 TLDR:\n{result.get('tldr')}\n")

    elif raw:
        # Get raw markdown content
        content = run_reader_call(lambda: reader.raw(arxiv_id), command_name="paper")
        if not content:
            handle_auth_error()
            sys.exit(1)
        click.echo(content)

    elif section:
        # Get specific section
        content = run_reader_call(lambda: reader.section(arxiv_id, section), command_name="paper")
        if not content:
            handle_auth_error()
            sys.exit(1)

        if output_format == "json":
            click.echo(json.dumps({"arxiv_id": arxiv_id, "section": section, "content": content}, indent=2))
        else:
            click.echo(f"# {section}\n")
            click.echo(content)

    elif preview:
        # Get preview
        result = run_reader_call(lambda: reader.preview(arxiv_id), command_name="paper")
        if not result:
            handle_auth_error()
            sys.exit(1)

        if output_format == "json":
            click.echo(json.dumps(result, indent=2))
        else:
            click.echo(result.get("content", result.get("preview", "")))

    elif output_format == "json":
        # Get full JSON
        result = run_reader_call(lambda: reader.json(arxiv_id), command_name="paper")
        if not result:
            handle_auth_error()
            sys.exit(1)
        click.echo(json.dumps(result, indent=2))

    else:
        # Get full markdown
        content = run_reader_call(lambda: reader.raw(arxiv_id), command_name="paper")
        if not content:
            # Try head for metadata
            head = run_reader_call(lambda: reader.head(arxiv_id), command_name="paper")
            if head:
                click.echo(f"# {head.get('title', arxiv_id)}\n")
                click.echo(f"**Authors:** {', '.join([a.get('name', str(a)) if isinstance(a, dict) else str(a) for a in head.get('authors', [])])}\n")
                click.echo(f"**Categories:** {', '.join(head.get('categories', []))}\n")
                click.echo(f"\n## Abstract\n\n{head.get('abstract', 'No abstract')}\n")
                click.echo("\n## Sections\n")
                for name, info in head.get("sections", {}).items():
                    click.echo(f"- {name}: {info.get('tldr', 'No summary')[:100]}...")
            else:
                handle_auth_error()
                sys.exit(1)
        else:
            click.echo(content)


@main.command()
@click.option("--token", "-t", default=None, help="DEEPXIV_TOKEN to save (if not provided, will prompt)")
@click.option("--global", "-g", "is_global", is_flag=True, default=True, help="Save to home directory (default: True)")
def config(token, is_global):
    """Configure DEEPXIV_TOKEN in .env file.

    Get your free token at: https://data.rag.ac.cn/register

    Example:
        deepxiv config                    # Save to ~/.env (global)
        deepxiv config --token YOUR_TOKEN
        deepxiv config --no-global        # Save to current directory
    """
    # Get token from option or prompt
    if not token:
        click.echo("📝 Get your free token at: https://data.rag.ac.cn/register\n")
        token = click.prompt("Please enter your DEEPXIV_TOKEN", hide_input=True)
    
    if not token or not token.strip():
        click.echo("Error: Token cannot be empty", err=True)
        sys.exit(1)
    
    token = token.strip()
    
    # Determine .env file location
    if is_global:
        env_file = Path.home() / ".env"
    else:
        env_file = Path.cwd() / ".env"
    
    existed = env_file.exists() and f"DEEPXIV_TOKEN=" in env_file.read_text()
    _upsert_env_value(env_file, "DEEPXIV_TOKEN", token)
    os.environ["DEEPXIV_TOKEN"] = token
    action = "updated" if existed else "added"
    click.echo(f"✓ DEEPXIV_TOKEN {action} in {env_file}")
    
    click.echo(f"\n✅ Token saved successfully!")
    click.echo(f"   The deepxiv CLI will automatically load it from {env_file}")
    click.echo(f"\n💡 To use in other apps/shells:")
    click.echo(f"   - Run: source {env_file}")
    click.echo(f"   - Or add to ~/.bashrc: export DEEPXIV_TOKEN=your_token")


@main.command()
@click.argument("pmc_id")
@click.option("--token", "-t", default=None, envvar="DEEPXIV_TOKEN", help="API token (or set DEEPXIV_TOKEN env var)")
@click.option("--format", "-f", "output_format", default="json", type=click.Choice(["json"]),
              help="Output format (default: json)")
@click.option("--head", is_flag=True, help="Get PMC paper metadata (returns JSON)")
def pmc(pmc_id, token, output_format, head):
    """Get a PMC (PubMed Central) paper by ID.

    Example:
        deepxiv pmc PMC544940
        deepxiv pmc PMC544940 --head
        deepxiv pmc PMC514704 --token YOUR_TOKEN
    """
    token = ensure_token(token)
    if not token:
        sys.exit(1)

    reader = Reader(token=token)

    if head:
        # Get PMC paper metadata
        result = run_reader_call(lambda: reader.pmc_head(pmc_id), command_name="pmc")
        if not result:
            handle_auth_error()
            sys.exit(1)
        click.echo(json.dumps(result, indent=2))
    else:
        # Get full PMC JSON
        result = run_reader_call(lambda: reader.pmc_json(pmc_id), command_name="pmc")
        if not result:
            handle_auth_error()
            sys.exit(1)
        click.echo(json.dumps(result, indent=2))


def _print_biomed_metadata(result: dict, label: str):
    """Pretty-print bioRxiv / medRxiv metadata."""
    click.echo(f"\n📄 {result.get('title', 'No title')}\n")
    click.echo(f"🆔 DOI: {result.get('source_id', 'N/A')}")
    click.echo(f"📅 Date: {result.get('publication_date', result.get('date', 'N/A'))}")
    click.echo(f"🔗 URL: {result.get('url', 'N/A')}")
    authors = result.get("authors", [])
    if authors:
        names = ", ".join(
            a.get("name", str(a)) if isinstance(a, dict) else str(a)
            for a in authors[:5]
        )
        if len(authors) > 5:
            names += f" ... (+{len(authors) - 5} more)"
        click.echo(f"👤 Authors: {names}")
    categories = result.get("categories", [])
    if categories:
        click.echo(f"🏷️  Categories: {', '.join(categories)}")
    if result.get("tldr"):
        click.echo(f"\n💡 TLDR:\n{result['tldr']}\n")
    elif result.get("abstract"):
        click.echo(f"\n📝 Abstract:\n{result['abstract'][:500]}...\n")


@main.command()
@click.argument("source_id")
@click.option("--token", "-t", default=None, envvar="DEEPXIV_TOKEN", help="API token (or set DEEPXIV_TOKEN env var)")
@click.option("--format", "-f", "output_format", default="json", type=click.Choice(["json", "text"]),
              help="Output format (default: json)")
@click.option("--section", "-s", default=None, help="Get specific section(s) by name (comma-separated)")
@click.option("--roc", is_flag=True, help="Get cited-by-reason list")
@click.option("--roc-num", default=None, type=int, help="Limit number of cited-by-reason entries")
def biorxiv(source_id, token, output_format, section, roc, roc_num):
    """Get a bioRxiv paper by DOI.

    SOURCE_ID is the paper DOI, e.g. 10.1101/2021.02.26.433129

    Example:
        deepxiv biorxiv 10.1101/2021.02.26.433129
        deepxiv biorxiv 10.1101/2021.02.26.433129 --format text
        deepxiv biorxiv 10.1101/2021.02.26.433129 --section Introduction,Methods
        deepxiv biorxiv 10.1101/2021.02.26.433129 --roc --roc-num 5
    """
    token = ensure_token(token)
    if not token:
        sys.exit(1)

    reader = Reader(token=token)

    if roc:
        data_type = "roc"
        section_names = None
    elif section:
        data_type = "section"
        section_names = [s.strip() for s in section.split(",")]
    else:
        data_type = "metadata"
        section_names = None

    result = run_reader_call(
        lambda: reader.biomed_data(
            source_id=source_id,
            source="biorxiv",
            data_type=data_type,
            section_names=section_names,
            roc_num=roc_num,
        ),
        command_name="biorxiv",
    )

    if not result:
        handle_auth_error()
        sys.exit(1)

    if output_format == "text" and data_type == "metadata":
        _print_biomed_metadata(result, "bioRxiv")
    else:
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@main.command()
@click.argument("source_id")
@click.option("--token", "-t", default=None, envvar="DEEPXIV_TOKEN", help="API token (or set DEEPXIV_TOKEN env var)")
@click.option("--format", "-f", "output_format", default="json", type=click.Choice(["json", "text"]),
              help="Output format (default: json)")
@click.option("--section", "-s", default=None, help="Get specific section(s) by name (comma-separated)")
@click.option("--roc", is_flag=True, help="Get cited-by-reason list")
@click.option("--roc-num", default=None, type=int, help="Limit number of cited-by-reason entries")
def medrxiv(source_id, token, output_format, section, roc, roc_num):
    """Get a medRxiv paper by DOI.

    SOURCE_ID is the paper DOI, e.g. 10.1101/2025.08.11.25333149

    Example:
        deepxiv medrxiv 10.1101/2025.08.11.25333149
        deepxiv medrxiv 10.1101/2025.08.11.25333149 --format text
        deepxiv medrxiv 10.1101/2025.08.11.25333149 --section Introduction
        deepxiv medrxiv 10.1101/2025.08.11.25333149 --roc
    """
    token = ensure_token(token)
    if not token:
        sys.exit(1)

    reader = Reader(token=token)

    if roc:
        data_type = "roc"
        section_names = None
    elif section:
        data_type = "section"
        section_names = [s.strip() for s in section.split(",")]
    else:
        data_type = "metadata"
        section_names = None

    result = run_reader_call(
        lambda: reader.biomed_data(
            source_id=source_id,
            source="medrxiv",
            data_type=data_type,
            section_names=section_names,
            roc_num=roc_num,
        ),
        command_name="medrxiv",
    )

    if not result:
        handle_auth_error()
        sys.exit(1)

    if output_format == "text" and data_type == "metadata":
        _print_biomed_metadata(result, "medRxiv")
    else:
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))


@main.command()
def help():
    """Show detailed help and usage examples.

    Example:
        deepxiv help
    """
    help_text = """
deepxiv - Access arXiv papers from the command line

CONFIGURATION:
  deepxiv config                    Configure your DEEPXIV_TOKEN manually
  deepxiv token                     Show the current token and support contact

ASK (agentic search → cited answer; needs a REGISTERED key, separate quota):
  deepxiv ask "question"            Search arXiv and answer, citing real IDs
  deepxiv ask "question" --web      Search the web instead, citing page links
    --effort, -e LEVEL              default / high / xhigh (deeper = slower)
    --verbose, -v                   Show tool calls, quota, progress on stderr
    --json                          Emit one JSON object instead of streaming
    --no-stream                     Wait for the full answer
    --max-answer-tokens N           Answer length cap (256~16384, default: 4096)
    --language LANG                 Answer language (default: query's language)
    --no-sources                    Skip the sources list
    --all-sources                   List every retrieved source, not just cited
    --top-k N                       arXiv only: retrieval size (1~30, default: 10)
    --search-type TYPE              --web only: search / scholar / news / images
    --gl CC / --hl LANG             --web only: Google country / UI language

  Agentic calls need a key from https://data.rag.ac.cn/register — the
  auto-registered SDK token returns 403. Quota is separate from the general
  daily limit: free 30/day, lite 500, premium 10000. Each call costs 1.

SEARCH:
  deepxiv search "query"            Search for papers (arXiv by default)
    --limit, -l N                   Number of results (1~100, default: 10)
    --offset N                      Pagination offset (0~10000, default: 0)
    --format, -f FORMAT             Output format: text, json (default: text)
    --categories, -c CATS           Filter by categories (e.g., cs.AI,cs.CL)
    --authors A1,A2                 Filter by authors (also influences ranking)
    --orgs O1,O2                    Filter by organizations (also influences ranking)
    --venue NAME                    Filter by venue; repeatable (e.g. NeurIPS, ICLR)
    --venue-year YEAR               Filter by conference/venue year (e.g. 2025)
    --min-citations N               Minimum citation count
    --date-from YYYY[-MM[-DD]]      Convenience: publication date from
    --date-to YYYY[-MM[-DD]]        Convenience: publication date to
    --date-search-type MODE         Advanced: between / exact / after / before
    --date-str S                    Advanced: date string (use twice for between)
    --use-fine-rerank               Enable upstream fine reranking (off by default)
    --biorxiv / --medrxiv           Switch to bioRxiv / medRxiv source

GET PAPER:
  deepxiv paper ARXIV_ID            Get paper by arXiv ID
    --head                          Get paper metadata (JSON)
    --brief, -b                     Get brief info (title, TLDR, keywords, citations, GitHub URL)
    --raw                           Get raw markdown content
    --preview, -p                   Get preview (~10k chars)
    --section, -s NAME              Get specific section
    --format, -f FORMAT             Output format: markdown, json (default: markdown)

GET PMC PAPER:
  deepxiv pmc PMC_ID                Get PMC paper by ID
    --head                          Get PMC paper metadata (JSON)
    --format, -f FORMAT             Output format: json (default: json)

GET bioRxiv PAPER:
  deepxiv biorxiv DOI               Get bioRxiv paper by DOI
    --section, -s NAMES             Get specific section(s), comma-separated
    --roc                           Get cited-by-reason list
    --roc-num N                     Limit cited-by-reason entries
    --format, -f FORMAT             Output format: json, text (default: json)

GET medRxiv PAPER:
  deepxiv medrxiv DOI               Get medRxiv paper by DOI
    --section, -s NAMES             Get specific section(s), comma-separated
    --roc                           Get cited-by-reason list
    --roc-num N                     Limit cited-by-reason entries
    --format, -f FORMAT             Output format: json, text (default: json)

EXAMPLES:
  # Configure token
  deepxiv config

  # Ask examples (be specific; rephrasing beats raising --effort)
  deepxiv ask "what speedup does speculative decoding report on HumanEval"
  deepxiv ask "对比 MoE 路由崩塌的几种缓解方法" --effort high
  deepxiv ask "state space models vs transformers" --json
  deepxiv ask "test-time compute scaling laws" > answer.md
  deepxiv ask "Anthropic Claude API pricing tiers" --web
  deepxiv ask "NeurIPS 2025 best paper winner" --web --search-type news

  # Search examples
  deepxiv search "transformer architecture" --limit 5
  deepxiv search "diffusion model" --venue NeurIPS --venue-year 2025
  deepxiv search "protein design" --biorxiv --limit 5
  deepxiv search "Alzheimer" --medrxiv --date-from 2024-01
  deepxiv search "machine learning" --categories cs.AI,cs.LG --min-citations 100

  # Get paper examples
  deepxiv paper 2409.05591
  deepxiv paper 2409.05591 --head
  deepxiv paper 2409.05591 --brief
  deepxiv paper 2409.05591 --raw
  deepxiv paper 2409.05591 --preview
  deepxiv paper 2409.05591 --section Introduction

  # Get PMC paper examples
  deepxiv pmc PMC544940
  deepxiv pmc PMC544940 --head
  deepxiv pmc PMC514704

  # Get bioRxiv / medRxiv paper examples
  deepxiv biorxiv 10.1101/2021.02.26.433129
  deepxiv biorxiv 10.1101/2021.02.26.433129 --format text
  deepxiv biorxiv 10.1101/2021.02.26.433129 --section Introduction,Methods
  deepxiv biorxiv 10.1101/2021.02.26.433129 --roc --roc-num 5
  deepxiv medrxiv 10.1101/2025.08.11.25333149
  deepxiv medrxiv 10.1101/2025.08.11.25333149 --format text

ENVIRONMENT:
  If DEEPXIV_TOKEN is missing, deepxiv will auto-register one on first use.
  
  Set DEEPXIV_TOKEN via:
    - Config command: deepxiv config (recommended)
    - Inspect current token: deepxiv token
    - Environment variable: export DEEPXIV_TOKEN=your_token
    - Command option: --token YOUR_TOKEN

For more information, visit: https://data.rag.ac.cn
"""
    click.echo(help_text)


@main.group()
def agent():
    """Intelligent agent for paper research.
    
    Use the agent to ask questions about papers, search and analyze research.
    
    Example:
        deepxiv agent query "What are the latest papers about agent memory?"
        deepxiv agent config  # Configure LLM API locally first
    """
    pass


@agent.command(name="query")
@click.argument("query")
@click.option("--token", "-t", default=None, envvar="DEEPXIV_TOKEN", help="DeepXiv API token")
@click.option("--max-turn", default=20, type=int, help="Maximum number of reasoning turns (default: 20)")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed reasoning process")
@click.option("--api-key", default=None, envvar="DEEPXIV_AGENT_API_KEY", help="LLM API key (overrides config)")
@click.option("--base-url", default=None, envvar="DEEPXIV_AGENT_BASE_URL", help="LLM API base URL (overrides config)")
@click.option("--model", default=None, envvar="DEEPXIV_AGENT_MODEL", help="Model name (overrides config)")
@click.option("--disable-thinking", is_flag=True, default=False,
              help="Send enable_thinking=False (required by some reasoning models, e.g. MiMo / DeepSeek-R1)")
def agent_query(query, token, max_turn, verbose, api_key, base_url, model, disable_thinking):
    """Ask the agent a question about papers.
    
    The agent can search papers, read content, and provide intelligent answers.
    
    Example:
        deepxiv agent query "What are the latest papers about agent memory?"
        deepxiv agent query "Compare transformer variants" --max-turn 10 --verbose
    """
    
    # Run the query logic (same as agent_query)
    # Check DeepXiv token
    token = ensure_token(token)
    if not token:
        sys.exit(1)
    
    # Get LLM config from options or saved config
    llm_config = get_agent_config()
    # Override with command-line options if provided
    if api_key:
        llm_config["api_key"] = api_key
    if base_url:
        llm_config["base_url"] = base_url
    if model:
        llm_config["model"] = model
    
    # Check if LLM is configured
    if not llm_config.get("api_key"):
        click.echo("\n❌ Agent LLM API not configured.\n", err=True)
        click.echo("Please configure it first:", err=True)
        click.echo("   deepxiv agent config\n", err=True)
        click.echo("Or set environment variables:", err=True)
        click.echo("   export DEEPXIV_AGENT_API_KEY=your_key", err=True)
        sys.exit(1)
    
    # Initialize reader
    reader = Reader(token=token)
    
    # Initialize agent
    try:
        from .agent import Agent
    except ImportError as e:
        click.echo("\n❌ Agent dependencies are not installed.\n", err=True)
        click.echo("The `deepxiv agent` command requires optional agent packages.", err=True)
        click.echo("Missing dependency details:", err=True)
        click.echo(f"   {e}", err=True)
        click.echo("\nInstall the missing packages and try again.", err=True)
        click.echo("If `langgraph` is missing, for example:", err=True)
        click.echo("   pip install langgraph langchain-core", err=True)
        sys.exit(1)

    try:
        agent_instance = Agent(
            api_key=llm_config["api_key"],
            reader=reader,
            model=llm_config.get("model", "gpt-4"),
            base_url=llm_config.get("base_url"),
            max_llm_calls=max_turn,
            print_process=verbose,
            stream=verbose,
            enable_thinking=False if disable_thinking else None,
        )
        
        # Run query
        click.echo(f"\n🤖 Agent is thinking...\n")
        answer = agent_instance.query(query)
        
        # Print answer
        click.echo("\n" + "="*80)
        click.echo("📝 Answer:")
        click.echo("="*80)
        click.echo(answer)
        click.echo("="*80 + "\n")
        
    except Exception as e:
        click.echo(f"\n❌ Error: {e}", err=True)
        sys.exit(1)


@agent.command(name="config")
@click.option("--api-key", default=None, help="LLM API key")
@click.option("--base-url", default=None, help="LLM API base URL (for OpenAI-compatible APIs)")
@click.option("--model", default=None, help="Model name (default: gpt-4)")
def agent_config(api_key, base_url, model):
    """Configure LLM API for the agent.
    
    Example:
        deepxiv agent config                                    # Interactive local configuration
        deepxiv agent config --api-key YOUR_KEY                 # OpenAI
        deepxiv agent config --api-key KEY --base-url https://api.deepseek.com --model deepseek-chat
    """
    # Get inputs interactively if not provided
    if not api_key:
        click.echo("🤖 Configure LLM API for deepxiv agent\n")
        click.echo("This configuration is stored locally on this machine only.\n")
        api_key = click.prompt("Please enter your LLM API key", hide_input=True)
    
    if not api_key or not api_key.strip():
        click.echo("Error: API key cannot be empty", err=True)
        sys.exit(1)
    
    api_key = api_key.strip()
    
    # Optional: ask for base_url if not provided
    if base_url is None:
        click.echo("\nAPI Base URL (leave empty for OpenAI)")
        click.echo("Examples: https://api.deepseek.com, https://api.openai.com/v1")
        base_url_input = click.prompt("Base URL", default="", show_default=False)
        base_url = base_url_input.strip() if base_url_input.strip() else None
    
    # Optional: ask for model if not provided
    if model is None:
        click.echo("\nModel name (e.g., gpt-4, deepseek-chat, gpt-4-turbo)")
        model = click.prompt("Model", default="gpt-4")
    
    # Save configuration
    save_agent_config(api_key, base_url, model)
    
    click.echo("\n✅ Configuration saved!")
    click.echo(f"   Model: {model}")
    if base_url:
        click.echo(f"   Base URL: {base_url}")
    click.echo("   Stored locally only in ~/.deepxiv_agent_config.json")
    click.echo("\n💡 You can now use: deepxiv agent \"your question\"")


@main.command(name="token")
@click.option("--token", "-t", default=None, envvar="DEEPXIV_TOKEN", help="API token (or set DEEPXIV_TOKEN env var)")
def show_token(token):
    """Show the current DEEPXIV token and support contact."""
    token = ensure_token(token)
    if not token:
        sys.exit(1)

    click.echo(f"Current DEEPXIV_TOKEN: {token}\n")
    click.echo("If you need a higher daily limit, email your name, email, and telephone to tommy@chien.io.")


@main.command()
@click.option("--token", "-t", default=None, envvar="DEEPXIV_TOKEN", help="API token")
def health(token):
    """Check API health and token validity.

    This command verifies:
    - API server connectivity
    - Token validity (if provided)
    - Free test papers availability
    """
    click.echo("🏥 Checking deepxiv API health...\n")

    # Check API connectivity
    click.echo("1️⃣  Checking API connectivity...")
    try:
        response = requests.get(f"{DEFAULT_BASE_URL}/api/docs", timeout=10)
        if response.status_code == 200:
            click.echo("   ✅ API server is reachable\n")
        else:
            click.echo(f"   ⚠️  API returned status {response.status_code}\n")
    except requests.exceptions.Timeout:
        click.echo("   ❌ API server is unreachable (timeout)\n")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        click.echo("   ❌ Cannot connect to API (connection error)\n")
        sys.exit(1)
    except Exception as e:
        click.echo(f"   ❌ Error: {e}\n")
        sys.exit(1)

    # Check token validity
    if token:
        click.echo("2️⃣  Checking token validity...")
        reader = Reader(token=token)
        try:
            # Try to access a free test paper
            result = reader.brief("2409.05591")
            if result:
                click.echo("   ✅ Token is valid\n")
            else:
                click.echo("   ⚠️  Token check inconclusive\n")
        except Exception as e:
            click.echo(f"   ❌ Token is invalid: {str(e)[:60]}\n")
            sys.exit(1)
    else:
        click.echo("2️⃣  Token not provided (skipped)\n")

    # Check free papers
    click.echo("3️⃣  Checking free test papers...")
    reader = Reader(token=token)
    test_papers = {
        "arxiv": "2409.05591",
        "pmc": "PMC544940"
    }

    try:
        brief = reader.brief(test_papers["arxiv"])
        if brief:
            click.echo(f"   ✅ arXiv test paper available: {test_papers['arxiv']}\n")
        else:
            click.echo(f"   ⚠️  Cannot access arXiv test paper\n")
    except Exception as e:
        click.echo(f"   ⚠️  arXiv test paper error: {str(e)[:40]}\n")

    click.echo("=" * 60)
    click.echo("✅ Health check completed!")
    click.echo("=" * 60)


@main.command()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def debug(verbose):
    """Print debug information and environment settings.

    Useful for troubleshooting configuration issues.
    """
    import logging

    click.echo("🐛 Debug Information\n")

    # Python and package info
    click.echo("System Information:")
    click.echo(f"  Python Version: {sys.version}")
    click.echo(f"  Platform: {sys.platform}\n")

    # deepxiv version
    from . import __version__
    click.echo(f"deepxiv-sdk Version: {__version__}\n")

    # Dependencies
    click.echo("Installed Features:")
    try:
        import langgraph
        click.echo("  ✅ Agent support (langgraph installed)")
    except ImportError:
        click.echo("  ❌ Agent support (install with: pip install deepxiv-sdk[agent])")

    try:
        import dotenv
        click.echo("  ✅ .env file support (python-dotenv installed)")
    except ImportError:
        click.echo("  ⚠️  .env file support (optional, install with: pip install python-dotenv)")

    click.echo()

    # Environment variables
    click.echo("Environment Variables:")
    deepxiv_token = os.environ.get("DEEPXIV_TOKEN")
    if deepxiv_token:
        click.echo(f"  ✅ DEEPXIV_TOKEN is set")
    else:
        click.echo(f"  ⚠️  DEEPXIV_TOKEN is not set (will auto-register on first use)")

    if os.environ.get("DEEPXIV_AGENT_API_KEY"):
        click.echo(f"  ✅ DEEPXIV_AGENT_API_KEY is set")
    else:
        click.echo(f"  ⚠️  DEEPXIV_AGENT_API_KEY is not set (required for agent)")

    click.echo()

    # Configuration files
    click.echo("Configuration Files:")
    home_env = Path.home() / ".env"
    if home_env.exists():
        click.echo(f"  ✅ ~/.env exists")
        if verbose:
            # Show non-secret values
            with open(home_env) as f:
                for line in f:
                    if "=" in line:
                        key, _ = line.split("=", 1)
                        if key.strip() and not any(secret in key for secret in ["TOKEN", "KEY", "SECRET"]):
                            click.echo(f"     {key.strip()}: (hidden)")
    else:
        click.echo(f"  ⚠️  ~/.env does not exist (tokens will be saved here on first use)")

    agent_config = Path.home() / ".deepxiv_agent_config.json"
    if agent_config.exists():
        click.echo(f"  ✅ Agent config exists at ~/.deepxiv_agent_config.json")
    else:
        click.echo(f"  ⚠️  Agent config does not exist (run 'deepxiv agent config' to create)")

    click.echo()

    # Enable logging if verbose
    if verbose:
        click.echo("Enabling verbose logging...\n")
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger("deepxiv_sdk")
        logger.setLevel(logging.DEBUG)

        # Test API connectivity with logging
        click.echo("Making test API request with debug logging...\n")
        reader = Reader(token=deepxiv_token)
        try:
            result = reader.brief("2409.05591")
            click.echo("\n✅ Test request successful")
        except Exception as e:
            click.echo(f"\n❌ Test request failed: {e}")


@main.command()
@click.option("--days", type=click.IntRange(1, 30), default=7,
              help="Time range in days (1~30, default: 7)")
@click.option("--limit", type=int, default=30,
              help="Maximum number of papers to return (default: 30, max: 100)")
@click.option("--output", "-o", "output_format", type=click.Choice(["text", "json"]),
              default="text", help="Output format (default: text)")
@click.option("--json", "json_output", is_flag=True, help="Shorthand for --output json")
def trending(days, limit, output_format, json_output):
    """Get trending arXiv papers.

    Shows the hottest papers from the last 1~30 days based on
    social media mentions, views, and engagement.

    Examples:
        deepxiv trending                    # Last 7 days, 30 papers
        deepxiv trending --days 1           # Just today
        deepxiv trending --days 30          # Last 30 days
        deepxiv trending --limit 5          # Top 5 papers
        deepxiv trending --json             # JSON output
        deepxiv trending --days 14 --limit 10 --json
    """
    # If --json flag is used, override output_format
    if json_output:
        output_format = "json"

    reader = Reader()

    try:
        result = reader.trending(days=int(days), limit=min(limit, 100))

        if output_format == "json":
            click.echo(json.dumps(result, indent=2))
        else:
            # Text output
            papers = result.get("papers", [])

            if not papers:
                click.echo("ℹ️  No trending papers found for this period.")
                return

            click.echo(f"\n📊 Trending Papers (Last {days} Days)\n")
            click.echo(f"Generated: {result.get('generated_at', 'N/A')}")
            click.echo(f"Total trending papers available: {result.get('total', 0)}\n")
            click.echo("-" * 100)

            for paper in papers[:min(limit, 100)]:
                arxiv_id = paper.get("arxiv_id", "N/A")
                rank = paper.get("rank", "?")
                stats = paper.get("stats", {})
                views = stats.get("total_views", "0")
                likes = stats.get("total_likes", "0")
                mentions = stats.get("total_mentions", 0)

                click.echo(f"\n#{rank}: arXiv:{arxiv_id}")
                click.echo(f"  📈 Views: {views:>10} | 👍 Likes: {likes:>8} | 💬 Mentions: {mentions}")

                mentioned_by = paper.get("mentioned_by", [])
                if mentioned_by:
                    top_mention = mentioned_by[0]
                    click.echo(f"  👤 Mentioned by: {top_mention.get('name')} (@{top_mention.get('username')})")
                    click.echo(f"     Followers: {top_mention.get('followers', 'N/A'):,}")

            click.echo("\n" + "-" * 100 + "\n")

    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
