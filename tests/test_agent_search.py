"""
Unit tests for the agentic search endpoint (Reader.agent_search / _stream).
"""
import json
import pytest
from unittest import mock

from deepxiv_sdk import (
    Reader,
    APIError,
    BadRequestError,
    AuthenticationError,
    RateLimitError,
    ServerError,
)


def make_response(status_code=200, json_body=None, lines=None, text=""):
    """Build a mock requests.Response covering both call styles."""
    response = mock.Mock()
    response.status_code = status_code
    response.text = text
    response.content = b"x" if (json_body is not None or lines) else b""
    response.json.return_value = json_body if json_body is not None else {}
    response.iter_lines.return_value = [
        json.dumps(line).encode("utf-8") for line in (lines or [])
    ]
    # Support `with requests.post(...) as response:`
    response.__enter__ = mock.Mock(return_value=response)
    response.__exit__ = mock.Mock(return_value=False)
    return response


STREAM_EVENTS = [
    {"event": "billing", "limit_cost": 100, "token_source": "sdk", "daily_limit": 1000},
    {"event": "start", "run_id": "abc123", "model": "deepseek-v4-flash", "effort": "default"},
    {"event": "answer_start", "elapsed_ms": 3812},
    {"event": "answer_delta", "text": "DEER reports a 5.54x speedup "},
    {"event": "answer_delta", "text": "on HumanEval [arXiv:2512.15176]."},
    {"event": "sources", "papers": [
        {"arxiv_id": "2512.15176", "url": "https://arxiv.org/abs/2512.15176", "title": "DEER"},
        {"arxiv_id": "1204.1689", "url": "https://arxiv.org/abs/1204.1689", "title": "Lie groups"},
    ]},
    {"event": "done", "elapsed_ms": 6496, "ttfa_ms": 3812, "answer_truncated": False},
]


class TestAgentSearchValidation:
    """Arguments are validated client-side, before any limit is spent."""

    @pytest.mark.parametrize("kwargs", [
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 2001},
        {"query": "ok", "effort": "ultra"},
        {"query": "ok", "top_k": 0},
        {"query": "ok", "top_k": 31},
        {"query": "ok", "max_answer_tokens": 255},
        {"query": "ok", "max_answer_tokens": 16385},
        {"query": "ok", "source": "reddit"},
        {"query": "ok", "source": "web", "top_k": 10},
        {"query": "ok", "search_type": "news"},
        {"query": "ok", "gl": "us"},
        {"query": "ok", "hl": "en"},
        {"query": "ok", "source": "web", "search_type": "videos"},
    ])
    def test_invalid_arguments_raise_before_request(self, kwargs):
        reader = Reader(token="t")
        with mock.patch("deepxiv_sdk.reader.requests.post") as post:
            with pytest.raises(ValueError):
                reader.agent_search(**kwargs)
            post.assert_not_called()

    def test_invalid_arguments_raise_before_stream_request(self):
        reader = Reader(token="t")
        with mock.patch("deepxiv_sdk.reader.requests.post") as post:
            with pytest.raises(ValueError):
                list(reader.agent_search_stream(query=""))
            post.assert_not_called()

    def test_query_is_stripped(self):
        reader = Reader(token="t")
        payload = reader._build_agent_search_payload(
            "  padded  ", "arxiv", "default", False, False, 4096, None
        )
        assert payload["query"] == "padded"

    def test_language_omitted_when_none(self):
        reader = Reader(token="t")
        payload = reader._build_agent_search_payload(
            "q", "arxiv", "default", False, True, 4096, None
        )
        assert "language" not in payload

    def test_arxiv_payload_shape(self):
        reader = Reader(token="t")
        payload = reader._build_agent_search_payload(
            "q", "arxiv", "high", True, False, 512, "en", top_k=5
        )
        assert payload == {
            "query": "q", "effort": "high", "verbose": True,
            "stream_answer": False, "max_answer_tokens": 512,
            "language": "en", "top_k": 5,
        }

    def test_arxiv_top_k_defaults_to_10(self):
        reader = Reader(token="t")
        payload = reader._build_agent_search_payload(
            "q", "arxiv", "default", False, True, 4096, None
        )
        assert payload["top_k"] == 10

    def test_web_payload_shape(self):
        reader = Reader(token="t")
        payload = reader._build_agent_search_payload(
            "q", "web", "default", False, True, 4096, None,
            search_type="news", gl="cn", hl="zh-cn",
        )
        assert payload == {
            "query": "q", "effort": "default", "verbose": False,
            "stream_answer": True, "max_answer_tokens": 4096,
            "search_type": "news", "gl": "cn", "hl": "zh-cn",
        }

    def test_web_defaults_search_type_and_omits_locale(self):
        """Locale is left to the service, which auto-switches for Chinese."""
        reader = Reader(token="t")
        payload = reader._build_agent_search_payload(
            "q", "web", "default", False, True, 4096, None
        )
        assert payload["search_type"] == "search"
        assert "gl" not in payload and "hl" not in payload
        assert "top_k" not in payload

    def test_boundary_values_accepted(self):
        reader = Reader(token="t")
        for top_k in (1, 30):
            payload = reader._build_agent_search_payload(
                "q", "arxiv", "xhigh", False, True, 256, None, top_k=top_k
            )
            assert payload["top_k"] == top_k
        for tokens in (256, 16384):
            payload = reader._build_agent_search_payload(
                "q", "web", "default", False, True, tokens, None
            )
            assert payload["max_answer_tokens"] == tokens


class TestAgentSearchStream:
    """Streaming yields raw NDJSON events."""

    def test_yields_all_events_in_order(self):
        reader = Reader(token="t")
        with mock.patch("deepxiv_sdk.reader.requests.post",
                        return_value=make_response(lines=STREAM_EVENTS)):
            events = list(reader.agent_search_stream("test query"))
        assert [e["event"] for e in events] == [e["event"] for e in STREAM_EVENTS]

    def test_answer_deltas_reassemble(self):
        reader = Reader(token="t")
        with mock.patch("deepxiv_sdk.reader.requests.post",
                        return_value=make_response(lines=STREAM_EVENTS)):
            text = "".join(
                e["text"] for e in reader.agent_search_stream("q")
                if e["event"] == "answer_delta"
            )
        assert text == "DEER reports a 5.54x speedup on HumanEval [arXiv:2512.15176]."

    def test_sends_bearer_token_and_payload(self):
        reader = Reader(token="secret")
        with mock.patch("deepxiv_sdk.reader.requests.post",
                        return_value=make_response(lines=STREAM_EVENTS)) as post:
            list(reader.agent_search_stream("q", effort="high", verbose=True))
        kwargs = post.call_args.kwargs
        assert kwargs["headers"]["Authorization"] == "Bearer secret"
        assert kwargs["stream"] is True
        assert kwargs["json"]["effort"] == "high"
        assert kwargs["json"]["verbose"] is True
        assert post.call_args.args[0].endswith("/arxiv/agent/search/stream")

    def test_blank_and_malformed_lines_are_skipped(self):
        reader = Reader(token="t")
        response = make_response()
        response.iter_lines.return_value = [
            b"", b"   ", b"not json at all",
            json.dumps({"event": "done", "answer_truncated": False}).encode(),
        ]
        with mock.patch("deepxiv_sdk.reader.requests.post", return_value=response):
            events = list(reader.agent_search_stream("q"))
        assert [e["event"] for e in events] == ["done"]

    def test_error_event_is_yielded_not_raised(self):
        """A partial answer may already be out; the caller decides what to keep."""
        reader = Reader(token="t")
        lines = [
            {"event": "answer_delta", "text": "partial"},
            {"event": "error", "stage": "gather", "message": "upstream exploded"},
        ]
        with mock.patch("deepxiv_sdk.reader.requests.post",
                        return_value=make_response(lines=lines)):
            events = list(reader.agent_search_stream("q"))
        assert events[-1]["event"] == "error"
        assert events[-1]["stage"] == "gather"

    def test_does_not_retry_on_timeout(self):
        """Each call costs limit units, so a timed-out stream must not re-bill."""
        import requests as _requests
        reader = Reader(token="t", max_retries=3)
        with mock.patch("deepxiv_sdk.reader.requests.post",
                        side_effect=_requests.exceptions.Timeout()) as post:
            with pytest.raises(APIError, match="timed out"):
                list(reader.agent_search_stream("q"))
        assert post.call_count == 1


class TestAgentSearchBlocking:
    """The non-streaming variant returns the whole payload."""

    def test_returns_payload(self):
        body = {
            "status": "success",
            "query": "q",
            "answer": "An answer [arXiv:2512.15176].",
            "sources": [{"arxiv_id": "2512.15176", "title": "DEER"}],
            "stats": {"answer_truncated": False},
            "limit_cost": 100,
        }
        reader = Reader(token="t")
        with mock.patch("deepxiv_sdk.reader.requests.post",
                        return_value=make_response(json_body=body)) as post:
            result = reader.agent_search("q")
        assert result["answer"] == "An answer [arXiv:2512.15176]."
        assert result["sources"][0]["arxiv_id"] == "2512.15176"
        assert post.call_args.args[0].endswith("/arxiv/agent/search")
        assert not post.call_args.args[0].endswith("/stream")

    def test_forces_non_streaming_payload_flags(self):
        reader = Reader(token="t")
        with mock.patch("deepxiv_sdk.reader.requests.post",
                        return_value=make_response(json_body={})) as post:
            reader.agent_search("q")
        assert post.call_args.kwargs["json"]["stream_answer"] is False
        assert post.call_args.kwargs["json"]["verbose"] is False

    def test_does_not_retry_on_timeout(self):
        import requests as _requests
        reader = Reader(token="t", max_retries=3)
        with mock.patch("deepxiv_sdk.reader.requests.post",
                        side_effect=_requests.exceptions.Timeout()) as post:
            with pytest.raises(APIError, match="timed out"):
                reader.agent_search("q")
        assert post.call_count == 1


class TestAgentSearchErrorMapping:
    """HTTP status codes map onto the SDK exception hierarchy."""

    @pytest.mark.parametrize("status,exc", [
        (401, AuthenticationError),
        (403, AuthenticationError),
        (422, BadRequestError),
        (400, BadRequestError),
        (429, RateLimitError),
        (500, ServerError),
        (503, ServerError),
    ])
    def test_status_maps_to_exception(self, status, exc):
        reader = Reader(token="t")
        response = make_response(status_code=status, json_body={"detail": "nope"})
        with mock.patch("deepxiv_sdk.reader.requests.post", return_value=response):
            with pytest.raises(exc):
                reader.agent_search("q")
            with pytest.raises(exc):
                list(reader.agent_search_stream("q"))

    def test_validation_detail_is_surfaced(self):
        reader = Reader(token="t")
        body = {"detail": [
            {"type": "less_than_equal", "loc": ["body", "top_k"],
             "msg": "Input should be less than or equal to 30"},
        ]}
        response = make_response(status_code=422, json_body=body)
        with mock.patch("deepxiv_sdk.reader.requests.post", return_value=response):
            with pytest.raises(BadRequestError, match="top_k"):
                reader.agent_search("q")

    def test_rate_limit_message_flags_separate_pool(self):
        reader = Reader(token="t")
        response = make_response(status_code=429, json_body={"detail": "free tier"})
        with mock.patch("deepxiv_sdk.reader.requests.post", return_value=response):
            with pytest.raises(RateLimitError, match="separate"):
                reader.agent_search("q")

    def test_403_tells_user_to_register(self):
        """A working SDK token still lacks agentic access — say what to do."""
        reader = Reader(token="sdk-token")
        response = make_response(status_code=403, json_body={
            "detail": "Agentic search requires a registered account key."})
        with mock.patch("deepxiv_sdk.reader.requests.post", return_value=response):
            with pytest.raises(AuthenticationError, match="register"):
                reader.agent_search("q")
            with pytest.raises(AuthenticationError, match="register"):
                list(reader.agent_search_stream("q"))

    def test_non_json_error_body_does_not_crash(self):
        reader = Reader(token="t")
        response = make_response(status_code=500, text="<html>gateway</html>")
        response.json.side_effect = ValueError("no json")
        with mock.patch("deepxiv_sdk.reader.requests.post", return_value=response):
            with pytest.raises(ServerError):
                reader.agent_search("q")


WEB_STREAM_EVENTS = [
    {"event": "billing", "tier": "free", "used": 28, "remaining": 2, "cost": 1},
    {"event": "start", "run_id": "web1", "effort": "default"},
    {"event": "answer_delta", "text": "Opus costs $5/MTok "},
    {"event": "answer_delta", "text": "([docs](https://platform.claude.com/pricing))."},
    {"event": "sources", "pages": [
        {"url": "https://platform.claude.com/pricing", "title": "Pricing", "read": True},
        {"url": "https://example.com/unrelated", "title": "Unrelated", "read": False},
    ]},
    {"event": "done", "answer_truncated": False},
]


class TestAgentSearchWebBackend:
    """The web backend is the same protocol against a different endpoint."""

    def test_stream_hits_web_endpoint(self):
        reader = Reader(token="t")
        with mock.patch("deepxiv_sdk.reader.requests.post",
                        return_value=make_response(lines=WEB_STREAM_EVENTS)) as post:
            list(reader.agent_search_stream("q", source="web"))
        assert post.call_args.args[0].endswith("/web/agent/search/stream")

    def test_blocking_hits_web_endpoint(self):
        reader = Reader(token="t")
        with mock.patch("deepxiv_sdk.reader.requests.post",
                        return_value=make_response(json_body={"answer": "x"})) as post:
            reader.agent_search("q", source="web")
        url = post.call_args.args[0]
        assert url.endswith("/web/agent/search") and not url.endswith("/stream")

    def test_search_type_is_sent(self):
        reader = Reader(token="t")
        with mock.patch("deepxiv_sdk.reader.requests.post",
                        return_value=make_response(lines=WEB_STREAM_EVENTS)) as post:
            list(reader.agent_search_stream("q", source="web", search_type="news"))
        assert post.call_args.kwargs["json"]["search_type"] == "news"

    def test_arxiv_remains_the_default_source(self):
        reader = Reader(token="t")
        with mock.patch("deepxiv_sdk.reader.requests.post",
                        return_value=make_response(lines=STREAM_EVENTS)) as post:
            list(reader.agent_search_stream("q"))
        assert "/arxiv/agent/search" in post.call_args.args[0]


class TestAgentSearchSourcesHelper:
    """agent_search_sources() normalises papers / pages / sources."""

    def test_normalises_each_key(self):
        from deepxiv_sdk import agent_search_sources
        assert agent_search_sources({"papers": [{"a": 1}]}) == [{"a": 1}]
        assert agent_search_sources({"pages": [{"b": 2}]}) == [{"b": 2}]
        assert agent_search_sources({"sources": [{"c": 3}]}) == [{"c": 3}]

    def test_empty_when_absent(self):
        from deepxiv_sdk import agent_search_sources
        assert agent_search_sources({"event": "done"}) == []

    def test_preserves_empty_list(self):
        from deepxiv_sdk import agent_search_sources
        assert agent_search_sources({"papers": []}) == []
