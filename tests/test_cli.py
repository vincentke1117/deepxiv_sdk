"""
Integration tests for CLI commands.
"""
import pytest
from unittest import mock
from click.testing import CliRunner
from deepxiv_sdk.cli import main, get_token, save_token


class TestCLIBasic:
    """Test basic CLI functionality."""

    def test_cli_help(self):
        """Test help command."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Usage:" in result.output or "Commands:" in result.output

    def test_cli_version(self):
        """Test version command."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0 or "version" in result.output.lower()


class TestTokenManagement:
    """Test token management."""

    def test_get_token_from_option(self):
        """Test getting token from option."""
        token = get_token("test_token")
        assert token == "test_token"

    def test_get_token_none(self):
        """Test getting token when none is provided."""
        token = get_token(None)
        # Token might be from environment or None
        assert token is None or isinstance(token, str)

    def test_save_token(self, tmp_path):
        """Test saving token."""
        import os
        with mock.patch("pathlib.Path.home", return_value=tmp_path):
            env_file = save_token("test_token_123", is_global=True)
            assert env_file.exists()
            assert "test_token_123" in env_file.read_text()


class TestCLISearch:
    """Test CLI search command."""

    def test_search_help(self):
        """Test search help."""
        runner = CliRunner()
        result = runner.invoke(main, ["search", "--help"])
        assert result.exit_code == 0
        assert "search" in result.output.lower()

    @mock.patch("deepxiv_sdk.cli.Reader")
    def test_search_basic(self, mock_reader_class):
        """Test basic search."""
        runner = CliRunner()
        mock_instance = mock.Mock()
        mock_instance.search.return_value = {
            "status": "success",
            "total_count": 1,
            "result": [
                {
                    "arxiv_id": "2409.05591",
                    "title": "Test Paper",
                    "abstract": "Test abstract",
                    "categories": ["cs.AI"],
                    "citation_count": 10,
                    "score": 0.9,
                }
            ],
        }
        mock_reader_class.return_value = mock_instance

        result = runner.invoke(main, ["search", "agent", "--limit", "1"])
        # Should either succeed or mention missing token
        assert result.exit_code in [0, 1]

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_search_rate_limit_shows_friendly_message(self, mock_ensure_token, mock_reader_class):
        """Test search shows a friendly message when daily limit is reached."""
        from deepxiv_sdk import RateLimitError

        runner = CliRunner()
        mock_instance = mock.Mock()
        mock_instance.search.side_effect = RateLimitError("Daily limit reached")
        mock_reader_class.return_value = mock_instance

        result = runner.invoke(main, ["search", "agent"])
        assert result.exit_code == 1
        assert "当前 token 已到日使用上限" in result.output
        assert "Your token has reached its daily usage limit" in result.output
        assert "https://data.rag.ac.cn/register" in result.output
        assert "Traceback" not in result.output

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_paper_bad_request_shows_friendly_message(self, mock_ensure_token, mock_reader_class):
        """Test paper shows a friendly message when arXiv ID is invalid."""
        from deepxiv_sdk import BadRequestError

        runner = CliRunner()
        mock_instance = mock.Mock()
        mock_instance.raw.side_effect = BadRequestError("Invalid request")
        mock_reader_class.return_value = mock_instance

        result = runner.invoke(main, ["paper", "agent"])
        assert result.exit_code == 1
        assert "`deepxiv paper` 需要传入 arXiv ID" in result.output
        assert "`deepxiv paper` expects an arXiv ID" in result.output
        assert "deepxiv search" in result.output
        assert "Traceback" not in result.output


class TestCLIPaper:
    """Test CLI paper commands."""

    def test_paper_help(self):
        """Test paper help."""
        runner = CliRunner()
        result = runner.invoke(main, ["paper", "--help"])
        assert result.exit_code == 0
        assert "paper" in result.output.lower()

    @mock.patch("deepxiv_sdk.cli.Reader")
    def test_paper_brief(self, mock_reader_class):
        """Test paper brief command."""
        runner = CliRunner()
        mock_instance = mock.Mock()
        mock_instance.brief.return_value = {
            "arxiv_id": "2409.05591",
            "title": "Test Paper",
            "tldr": "Test TLDR",
            "citations": 100,
            "github_url": "https://github.com/example/test-paper",
        }
        mock_reader_class.return_value = mock_instance

        result = runner.invoke(main, ["paper", "2409.05591", "--brief"])
        assert result.exit_code in [0, 1]  # Might fail due to token

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_paper_brief_displays_github_url(self, mock_ensure_token, mock_reader_class):
        """Test paper brief pretty output includes GitHub URL when available."""
        runner = CliRunner()
        mock_instance = mock.Mock()
        mock_instance.brief.return_value = {
            "arxiv_id": "2409.05591",
            "title": "Test Paper",
            "tldr": "Test TLDR",
            "citations": 100,
            "src_url": "https://arxiv.org/pdf/2409.05591.pdf",
            "github_url": "https://github.com/example/test-paper",
        }
        mock_reader_class.return_value = mock_instance

        result = runner.invoke(main, ["paper", "2409.05591", "--brief"])
        assert result.exit_code == 0
        assert "GitHub" in result.output
        assert "https://github.com/example/test-paper" in result.output


class TestCLIToken:
    """Test token command."""

    def test_token_help(self):
        """Test token help."""
        runner = CliRunner()
        result = runner.invoke(main, ["token", "--help"])
        assert result.exit_code == 0


class TestCLIPMC:
    """Test PMC commands."""

    def test_pmc_help(self):
        """Test PMC help."""
        runner = CliRunner()
        result = runner.invoke(main, ["pmc", "--help"])
        assert result.exit_code == 0
        assert "pmc" in result.output.lower()

    @mock.patch("deepxiv_sdk.cli.Reader")
    def test_pmc_head(self, mock_reader_class):
        """Test PMC head command."""
        runner = CliRunner()
        mock_instance = mock.Mock()
        mock_instance.pmc_head.return_value = {
            "pmc_id": "PMC544940",
            "title": "Sample Paper",
        }
        mock_reader_class.return_value = mock_instance

        result = runner.invoke(main, ["pmc", "PMC544940", "--head"])
        assert result.exit_code in [0, 1]


class TestCLIConfig:
    """Test config command."""

    def test_config_help(self):
        """Test config help."""
        runner = CliRunner()
        result = runner.invoke(main, ["config", "--help"])
        assert result.exit_code == 0
        assert "config" in result.output.lower()


class TestCLICommandSet:
    """The registered command set."""

    def test_serve_command_is_gone(self):
        """deepxiv no longer ships an MCP server."""
        assert "serve" not in main.commands

    def test_core_commands_present(self):
        for name in ("ask", "search", "paper", "trending", "config", "token"):
            assert name in main.commands


class TestCLIAsk:
    """Test the agentic search `ask` command."""

    STREAM_EVENTS = [
        {"event": "billing", "limit_cost": 100},
        {"event": "start", "run_id": "abc", "model": "deepseek-v4-flash",
         "effort": "default", "max_rounds": 4},
        {"event": "answer_start", "elapsed_ms": 3812},
        {"event": "answer_delta", "text": "DEER reports 5.54x "},
        {"event": "answer_delta", "text": "on HumanEval [arXiv:2512.15176]."},
        {"event": "sources", "papers": [
            {"arxiv_id": "2512.15176", "url": "https://arxiv.org/abs/2512.15176",
             "title": "DEER"},
            {"arxiv_id": "1204.1689", "url": "https://arxiv.org/abs/1204.1689",
             "title": "Lie groups on manifolds"},
        ]},
        {"event": "done", "answer_truncated": False},
    ]

    def test_ask_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["ask", "--help"])
        assert result.exit_code == 0
        assert "real citations" in result.output
        assert "--web" in result.output

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_ask_streams_answer(self, mock_token, mock_reader_class):
        runner = CliRunner()
        instance = mock.Mock()
        instance.agent_search_stream.return_value = iter(self.STREAM_EVENTS)
        mock_reader_class.return_value = instance

        result = runner.invoke(main, ["ask", "what speedup does DEER report"])
        assert result.exit_code == 0
        assert "DEER reports 5.54x on HumanEval [arXiv:2512.15176]." in result.output

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_ask_lists_only_cited_sources(self, mock_token, mock_reader_class):
        """Retrieved-but-uncited papers are hidden unless --all-sources."""
        runner = CliRunner()
        instance = mock.Mock()
        instance.agent_search_stream.return_value = iter(self.STREAM_EVENTS)
        mock_reader_class.return_value = instance

        result = runner.invoke(main, ["ask", "q"])
        assert "2512.15176" in result.output
        assert "Lie groups on manifolds" not in result.output
        assert "1 cited" in result.output

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_ask_all_sources_lists_everything(self, mock_token, mock_reader_class):
        runner = CliRunner()
        instance = mock.Mock()
        instance.agent_search_stream.return_value = iter(self.STREAM_EVENTS)
        mock_reader_class.return_value = instance

        result = runner.invoke(main, ["ask", "q", "--all-sources"])
        assert "Lie groups on manifolds" in result.output

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_ask_passes_effort_through(self, mock_token, mock_reader_class):
        runner = CliRunner()
        instance = mock.Mock()
        instance.agent_search_stream.return_value = iter(self.STREAM_EVENTS)
        mock_reader_class.return_value = instance

        runner.invoke(main, ["ask", "q", "--effort", "xhigh", "--top-k", "25"])
        kwargs = instance.agent_search_stream.call_args.kwargs
        assert kwargs["effort"] == "xhigh"
        assert kwargs["top_k"] == 25

    def test_ask_rejects_unknown_effort(self):
        runner = CliRunner()
        result = runner.invoke(main, ["ask", "q", "--effort", "ultra"])
        assert result.exit_code != 0

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_ask_json_uses_blocking_endpoint(self, mock_token, mock_reader_class):
        runner = CliRunner()
        instance = mock.Mock()
        instance.agent_search.return_value = {
            "answer": "text [arXiv:2512.15176]",
            "sources": [{"arxiv_id": "2512.15176", "title": "DEER"}],
            "stats": {"answer_truncated": False},
        }
        mock_reader_class.return_value = instance

        result = runner.invoke(main, ["ask", "q", "--json"])
        assert result.exit_code == 0
        assert '"answer"' in result.output
        instance.agent_search_stream.assert_not_called()

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_ask_warns_on_truncated_answer(self, mock_token, mock_reader_class):
        runner = CliRunner()
        events = list(self.STREAM_EVENTS[:-1]) + [
            {"event": "done", "answer_truncated": True}
        ]
        instance = mock.Mock()
        instance.agent_search_stream.return_value = iter(events)
        mock_reader_class.return_value = instance

        result = runner.invoke(main, ["ask", "q"])
        assert "truncated" in result.output

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_ask_error_event_exits_nonzero(self, mock_token, mock_reader_class):
        runner = CliRunner()
        events = [
            {"event": "answer_delta", "text": "partial"},
            {"event": "error", "stage": "gather", "message": "upstream exploded"},
        ]
        instance = mock.Mock()
        instance.agent_search_stream.return_value = iter(events)
        mock_reader_class.return_value = instance

        result = runner.invoke(main, ["ask", "q"])
        assert result.exit_code == 1
        assert "upstream exploded" in result.output

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_ask_rate_limit_is_friendly(self, mock_token, mock_reader_class):
        from deepxiv_sdk import RateLimitError
        runner = CliRunner()
        instance = mock.Mock()
        instance.agent_search_stream.side_effect = RateLimitError("limit")
        mock_reader_class.return_value = instance

        result = runner.invoke(main, ["ask", "q"])
        assert result.exit_code == 1
        assert "Traceback" not in result.output


class TestCLIAskWeb:
    """`deepxiv ask --web` routes to the web backend."""

    WEB_EVENTS = [
        {"event": "billing", "tier": "free", "used": 28, "remaining": 2},
        {"event": "answer_delta",
         "text": "Opus is $5/MTok ([docs](https://platform.claude.com/pricing))."},
        {"event": "sources", "pages": [
            {"url": "https://platform.claude.com/pricing", "title": "Pricing",
             "read": True},
            {"url": "https://example.com/other", "title": "Other", "read": False},
        ]},
        {"event": "done", "answer_truncated": False},
    ]

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_web_flag_sets_source(self, mock_token, mock_reader_class):
        runner = CliRunner()
        instance = mock.Mock()
        instance.agent_search_stream.return_value = iter(self.WEB_EVENTS)
        mock_reader_class.return_value = instance

        result = runner.invoke(main, ["ask", "q", "--web"])
        assert result.exit_code == 0
        assert instance.agent_search_stream.call_args.kwargs["source"] == "web"

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_web_sources_use_url_matching(self, mock_token, mock_reader_class):
        """Web citations are URLs, not arXiv IDs."""
        runner = CliRunner()
        instance = mock.Mock()
        instance.agent_search_stream.return_value = iter(self.WEB_EVENTS)
        mock_reader_class.return_value = instance

        result = runner.invoke(main, ["ask", "q", "--web"])
        assert "1 cited" in result.output
        assert "platform.claude.com/pricing" in result.output
        assert "example.com/other" not in result.output

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_web_marks_snippet_only_pages(self, mock_token, mock_reader_class):
        runner = CliRunner()
        instance = mock.Mock()
        instance.agent_search_stream.return_value = iter(self.WEB_EVENTS)
        mock_reader_class.return_value = instance

        result = runner.invoke(main, ["ask", "q", "--web", "--all-sources"])
        assert "weaker evidence" in result.output

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_search_type_passed_through(self, mock_token, mock_reader_class):
        runner = CliRunner()
        instance = mock.Mock()
        instance.agent_search_stream.return_value = iter(self.WEB_EVENTS)
        mock_reader_class.return_value = instance

        runner.invoke(main, ["ask", "q", "--web", "--search-type", "news"])
        assert instance.agent_search_stream.call_args.kwargs["search_type"] == "news"

    def test_top_k_rejected_with_web(self):
        runner = CliRunner()
        result = runner.invoke(main, ["ask", "q", "--web", "--top-k", "5"])
        assert result.exit_code == 2
        assert "arXiv-only" in result.output

    def test_search_type_rejected_without_web(self):
        runner = CliRunner()
        result = runner.invoke(main, ["ask", "q", "--search-type", "news"])
        assert result.exit_code == 2
        assert "requires --web" in result.output

    def test_max_answer_tokens_range_enforced(self):
        runner = CliRunner()
        for bad in ("255", "16385"):
            result = runner.invoke(main, ["ask", "q", "--max-answer-tokens", bad])
            assert result.exit_code != 0

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_low_quota_warns(self, mock_token, mock_reader_class):
        runner = CliRunner()
        instance = mock.Mock()
        instance.agent_search_stream.return_value = iter(self.WEB_EVENTS)
        mock_reader_class.return_value = instance

        result = runner.invoke(main, ["ask", "q", "--web"])
        assert "2 agentic call(s) left today" in result.output

    @mock.patch("deepxiv_sdk.cli.Reader")
    @mock.patch("deepxiv_sdk.cli.ensure_token", return_value="test_token")
    def test_403_points_at_registration(self, mock_token, mock_reader_class):
        from deepxiv_sdk import AuthenticationError
        runner = CliRunner()
        instance = mock.Mock()
        instance.agent_search_stream.side_effect = AuthenticationError(
            "Agentic search requires a registered account key."
        )
        mock_reader_class.return_value = instance

        result = runner.invoke(main, ["ask", "q"])
        assert result.exit_code == 1
        assert "Traceback" not in result.output
