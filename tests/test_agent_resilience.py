"""
Tests for the ReAct agent:
- tool-failure circuit breaker (issue #11 Problem 1)
- extra_body / enable_thinking passthrough (issue #11 Problem 2)
- graceful handling of missing / unindexed papers (issue #12)

These require the optional agent dependencies (langgraph); the whole module is
skipped if they are not installed.
"""
from types import SimpleNamespace

import pytest

pytest.importorskip("langgraph")

from deepxiv_sdk import ServerError, NotFoundError, BadRequestError
from deepxiv_sdk.agent.tools import ToolExecutor, is_service_failure
from deepxiv_sdk.agent.graph import (
    call_llm,
    tool_call_node,
    check_limits_node,
    create_react_graph,
    create_initial_state,
)
from deepxiv_sdk.agent.agent import Agent


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
def _tool_call_response():
    """A response that asks to call search_papers."""
    tc = SimpleNamespace(
        id="call_1",
        type="function",
        function=SimpleNamespace(name="search_papers", arguments='{"query": "agent memory"}'),
    )
    msg = SimpleNamespace(content="", tool_calls=[tc], reasoning_content=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _answer_response(text):
    msg = SimpleNamespace(content=text, tool_calls=None, reasoning_content=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _FakeClient:
    """Records every create() call. Returns a tool call when tools are offered,
    otherwise a final answer (the forced-answer path uses tools=None)."""

    def __init__(self, answer="<answer>The paper service is temporarily unavailable.</answer>"):
        self.calls = []
        self._answer = answer
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                if kwargs.get("tools"):
                    return _tool_call_response()
                return _answer_response(outer._answer)

        self.chat = SimpleNamespace(completions=_Completions())


class _FailingReader:
    """Reader stub whose search always 503s, like the backend in issue #11."""

    def search(self, **kwargs):
        raise ServerError("Server error 503")


class _OkReader:
    def search(self, **kwargs):
        return {"status": "success", "total_count": 0, "result": []}


class _DummyReader:
    pass


class _NotFoundReader:
    """head() 404s, like an unindexed paper in issue #12."""

    def head(self, arxiv_id):
        raise NotFoundError("Paper not found. Check your arXiv/PMC ID.")


class _BadRequestReader:
    def head(self, arxiv_id):
        raise BadRequestError("invalid arxiv id")


class _ServerErrorReader:
    def head(self, arxiv_id):
        raise ServerError("Server error 503")


class _HeadOkReader:
    def head(self, arxiv_id):
        return {
            "title": "A Paper",
            "abstract": "abstract",
            "authors": [],
            "sections": {},
            "token_count": 1,
            "categories": [],
            "publish_at": "2026-05-22",
        }


def _config(client, **overrides):
    cfg = {
        "client": client,
        "model_name": "test-model",
        "max_tokens": 256,
        "temperature": 0.0,
        "max_llm_calls": 20,
        "max_time_seconds": 600,
        "max_consecutive_failures": 2,
        "print_process": False,
        "stream": False,
        "extra_body": None,
        "tool_executor": ToolExecutor(_FailingReader()),
    }
    cfg.update(overrides)
    return {"configurable": cfg, "recursion_limit": 100}


# --------------------------------------------------------------------------- #
# is_service_failure classifier
# --------------------------------------------------------------------------- #
class TestServiceFailureClassifier:
    def test_service_errors_are_failures(self):
        assert is_service_failure(
            "Error executing search_papers: the paper data service returned an error (503)."
        )
        assert is_service_failure("Error: Failed to search for papers with query 'x'.")
        assert is_service_failure("Error: Failed to fetch section 'Intro' from paper 123.")
        assert is_service_failure("Error: Failed to load paper 2409.05591.")

    def test_recoverable_errors_are_not_failures(self):
        # The model fumbling an argument must NOT count toward the breaker.
        assert not is_service_failure(
            "Error: Section 'Foo' not found in paper 123. Available sections: Intro, Method"
        )
        assert not is_service_failure(
            "Error: Paper 123 is not loaded. Please use load_paper first."
        )
        assert not is_service_failure("=== Search Results for 'x' (arXiv) ===")
        assert not is_service_failure("")


# --------------------------------------------------------------------------- #
# Problem 2: extra_body passthrough
# --------------------------------------------------------------------------- #
class TestExtraBodyPassthrough:
    def test_extra_body_forwarded_to_create(self):
        client = _FakeClient()
        call_llm(
            messages=[{"role": "user", "content": "hi"}],
            client=client,
            model_name="m",
            tools=None,
            extra_body={"enable_thinking": False},
        )
        assert client.calls[0]["extra_body"] == {"enable_thinking": False}

    def test_no_extra_body_key_when_unset(self):
        client = _FakeClient()
        call_llm(
            messages=[{"role": "user", "content": "hi"}],
            client=client,
            model_name="m",
            tools=None,
        )
        assert "extra_body" not in client.calls[0]

    def test_agent_enable_thinking_builds_extra_body(self):
        a = Agent(api_key="x", reader=_DummyReader(), enable_thinking=False)
        assert a.extra_body == {"enable_thinking": False}
        assert a.max_consecutive_failures == 3

    def test_agent_extra_body_merges_enable_thinking(self):
        a = Agent(
            api_key="x",
            reader=_DummyReader(),
            extra_body={"foo": 1},
            enable_thinking=True,
        )
        assert a.extra_body == {"foo": 1, "enable_thinking": True}

    def test_agent_default_extra_body_empty(self):
        a = Agent(api_key="x", reader=_DummyReader())
        assert a.extra_body == {}


# --------------------------------------------------------------------------- #
# Problem 1: circuit breaker
# --------------------------------------------------------------------------- #
class TestToolFailureCounter:
    def _assistant_with_tool_call(self):
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "1", "type": "function",
                 "function": {"name": "search_papers", "arguments": "{}"}}
            ],
        }

    def test_failure_increments_counter(self):
        state = create_initial_state()
        state["messages"] = [self._assistant_with_tool_call()]
        state["status"] = ["tool_call"]
        out = tool_call_node(state, _config(_FakeClient()))
        assert out["consecutive_failures"] == 1

    def test_failure_accumulates(self):
        state = create_initial_state()
        state["messages"] = [self._assistant_with_tool_call()]
        state["status"] = ["tool_call"]
        state["consecutive_failures"] = 2
        out = tool_call_node(state, _config(_FakeClient()))
        assert out["consecutive_failures"] == 3

    def test_success_resets_counter(self):
        state = create_initial_state()
        state["messages"] = [self._assistant_with_tool_call()]
        state["status"] = ["tool_call"]
        state["consecutive_failures"] = 5
        cfg = _config(_FakeClient(), tool_executor=ToolExecutor(_OkReader()))
        out = tool_call_node(state, cfg)
        assert out["consecutive_failures"] == 0


class TestCircuitBreakerNode:
    def _state_after_failures(self, failures, round_=3):
        state = create_initial_state()
        state["round"] = round_
        state["consecutive_failures"] = failures
        state["messages"] = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "",
             "tool_calls": [{"id": "1", "type": "function",
                             "function": {"name": "search_papers", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "1",
             "content": "Error executing search_papers: the paper data service returned an error (503)."},
        ]
        return state

    def test_breaker_trips_and_forces_answer(self):
        client = _FakeClient()
        state = self._state_after_failures(failures=2)
        out = check_limits_node(state, _config(client, max_consecutive_failures=2))

        assert out["status"][-1] == "answer"
        assert "unavailable" in out["prediction"].lower()
        # The forced-answer call must NOT offer tools (else it could loop again).
        assert "tools" not in client.calls[-1]

    def test_breaker_does_not_trip_below_threshold(self):
        client = _FakeClient()
        state = self._state_after_failures(failures=1)
        out = check_limits_node(state, _config(client, max_consecutive_failures=2))
        # No forced answer: node returns only status, makes no LLM call.
        assert "prediction" not in out
        assert client.calls == []

    def test_breaker_disabled_when_zero(self):
        client = _FakeClient()
        state = self._state_after_failures(failures=9)
        out = check_limits_node(state, _config(client, max_consecutive_failures=0))
        assert "prediction" not in out
        assert client.calls == []


class TestEndToEndCircuitBreaker:
    def test_graph_stops_looping_on_repeated_search_failures(self):
        """Before the fix the LLM re-invoked search_papers until max_llm_calls
        (20). The breaker must terminate far sooner with an answer."""
        client = _FakeClient()
        graph = create_react_graph()

        state = create_initial_state()
        state["question"] = "What is the latest on agent memory?"
        state["num_llm_calls_available"] = 20

        final = graph.invoke(state, _config(client, max_consecutive_failures=2))

        # Broke early instead of looping to the 20-call ceiling.
        assert final["round"] <= 5
        assert "unavailable" in final["prediction"].lower()
        # Sanity: it really did keep hitting the failing tool before breaking.
        assert any(c.get("tools") for c in client.calls)
        # And the final call was a tools-less forced answer.
        assert "tools" not in client.calls[-1]


# --------------------------------------------------------------------------- #
# Issue #12: missing / unindexed papers
# --------------------------------------------------------------------------- #
class TestAddPaperMissing:
    def test_returns_false_on_not_found(self):
        agent = Agent(api_key="x", reader=_NotFoundReader())
        assert agent.add_paper("2605.12345") is False
        assert agent.persistent_papers == {}

    def test_returns_false_on_bad_request(self):
        agent = Agent(api_key="x", reader=_BadRequestReader())
        assert agent.add_paper("not-an-id") is False

    def test_propagates_genuine_errors(self):
        # A 5xx is not "paper unavailable" — the caller should still see it.
        agent = Agent(api_key="x", reader=_ServerErrorReader())
        with pytest.raises(ServerError):
            agent.add_paper("2409.05591")

    def test_returns_true_on_success(self):
        agent = Agent(api_key="x", reader=_HeadOkReader())
        assert agent.add_paper("2409.05591") is True
        assert "2409.05591" in agent.persistent_papers


class TestToolNotFoundIsRecoverable:
    """A 404 inside a tool must read as recoverable and NOT trip the breaker."""

    def test_load_paper_not_found(self):
        executor = ToolExecutor(_NotFoundReader())
        msg = executor.execute_tool_call(
            "load_paper", {"arxiv_id": "2605.12345"}, create_initial_state()
        )
        assert "could not find" in msg
        assert not is_service_failure(msg)

    def test_load_paper_bad_request(self):
        executor = ToolExecutor(_BadRequestReader())
        msg = executor.execute_tool_call(
            "load_paper", {"arxiv_id": "bad-id"}, create_initial_state()
        )
        assert "invalid arguments" in msg
        assert not is_service_failure(msg)

    def test_search_server_error_still_trips_breaker(self):
        # Contrast: a real 5xx is still classified as a service failure.
        executor = ToolExecutor(_FailingReader())
        msg = executor.execute_tool_call(
            "search_papers", {"query": "x"}, create_initial_state()
        )
        assert is_service_failure(msg)


def test_exceptions_module_path_matches_root():
    """The path used in issue #12's workaround now exists and is canonical."""
    from deepxiv_sdk.exceptions import NotFoundError as NF_mod
    from deepxiv_sdk import NotFoundError as NF_root

    assert NF_mod is NF_root
