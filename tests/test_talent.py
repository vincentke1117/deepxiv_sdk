"""
Tests for the talent (scholar profile) endpoints and CLI commands.
"""
import json
import pytest
from unittest import mock
from click.testing import CliRunner

from deepxiv_sdk import Reader
from deepxiv_sdk.cli import main
from deepxiv_sdk.reader import NotFoundError


SEARCH_RESPONSE = {
    "persons": [
        {
            "id": 257,
            "name_zh": None,
            "name_en": "Zhicheng Dou",
            "primary_affiliation": "Renmin University of China",
            "location": "北京",
            "h_index": 55,
            "total_citations": 13168,
            "tags": ["信息检索", "检索增强生成"],
        }
    ],
    "total": 1,
    "limit": 10,
    "offset": 0,
    "semantic": True,
    "quota": {"tier": "free", "cost": 1, "daily_limit": 30, "used": 3, "remaining": 27},
    "cached": False,
}

SURVEY_RESPONSE = {
    "person": {
        "id": 257,
        "name_en": "Zhicheng Dou",
        "primary_affiliation": "Renmin University of China",
        "h_index": 55,
        "total_citations": 13168,
        "tags": ["信息检索"],
        "report_md": "# 窦志成\n\nreport body",
        "profile": {
            "status": "长聘教授",
            "bio_md": "bio body",
            "links": {"email": "dou@ruc.edu.cn", "homepage": "https://dou.playbigdata.com/"},
            "education": [{"start": "2003", "end": "2008", "school": "南开大学", "degree": "工学博士"}],
            "work": [{"start": "2018.08", "end": "今", "org": "中国人民大学", "title": "长聘教授"}],
            "open_source": [{"url": "https://github.com/RUC-NLPIR/FlashRAG", "stars": 3501}],
        },
    },
    "papers": [],
    "scholar": {"age_days": 0.73, "refreshed": False, "refresh_skipped": "skipped by request"},
    "quota": {"tier": "free", "remaining": 26, "used": 4},
}


class TestTalentReader:
    """Reader-level talent methods."""

    def test_search_builds_params(self):
        reader = Reader(token="t")
        with mock.patch.object(reader, "_make_request", return_value=SEARCH_RESPONSE) as req:
            result = reader.talent_search(
                query="RAG people", semantic=True, tags=["LLM", "Agent"],
                career_stage="student", sort="total_citations", limit=5,
            )
        url, kwargs = req.call_args[0][0], req.call_args[1]
        params = kwargs["params"]
        assert url.endswith("/talent/search")
        assert params["q"] == "RAG people"
        assert params["semantic"] == "true"
        assert params["tags"] == "LLM,Agent"
        assert params["career_stage"] == "student"
        assert params["sort"] == "total_citations"
        assert params["limit"] == 5
        assert result["total"] == 1

    def test_search_omits_unset_filters(self):
        reader = Reader(token="t")
        with mock.patch.object(reader, "_make_request", return_value=SEARCH_RESPONSE) as req:
            reader.talent_search(query="窦志成")
        params = req.call_args[1]["params"]
        assert "semantic" not in params
        assert "tags" not in params
        assert "career_stage" not in params

    @pytest.mark.parametrize("kwargs", [
        {"career_stage": "professor"},
        {"investigated": "shallow"},
        {"sort": "h-index"},
        {"order": "sideways"},
    ])
    def test_search_rejects_bad_enums(self, kwargs):
        reader = Reader(token="t")
        with pytest.raises(ValueError):
            reader.talent_search(query="x", **kwargs)

    @pytest.mark.parametrize("refresh,expected", [
        (None, {}),
        (True, {"refresh": "true"}),
        (False, {"refresh": "false"}),
    ])
    def test_survey_refresh_flag(self, refresh, expected):
        reader = Reader(token="t")
        with mock.patch.object(reader, "_make_request", return_value=SURVEY_RESPONSE) as req:
            reader.talent_survey(257, refresh=refresh)
        assert req.call_args[0][0].endswith("/talent/survey/257")
        assert req.call_args[1]["params"] == expected


class TestTalentCLI:
    """CLI-level talent commands."""

    def test_search_text_output(self):
        runner = CliRunner()
        with mock.patch("deepxiv_sdk.cli.Reader") as R:
            R.return_value.talent_search.return_value = SEARCH_RESPONSE
            result = runner.invoke(main, ["talent", "search", "RAG", "-s", "-t", "tok"])
        assert result.exit_code == 0
        assert "[257] Zhicheng Dou" in result.output
        assert "Renmin University of China" in result.output
        assert "semantic search" in result.output

    def test_search_json_output(self):
        runner = CliRunner()
        with mock.patch("deepxiv_sdk.cli.Reader") as R:
            R.return_value.talent_search.return_value = SEARCH_RESPONSE
            result = runner.invoke(main, ["talent", "search", "RAG", "--json", "-t", "tok"])
        assert result.exit_code == 0
        assert json.loads(result.output)["total"] == 1

    def test_search_requires_query_or_tags(self):
        runner = CliRunner()
        result = runner.invoke(main, ["talent", "search", "-t", "tok"])
        assert result.exit_code == 1
        assert "Provide a QUERY or --tags" in result.output

    def test_search_accepts_tags_only(self):
        runner = CliRunner()
        with mock.patch("deepxiv_sdk.cli.Reader") as R:
            R.return_value.talent_search.return_value = SEARCH_RESPONSE
            result = runner.invoke(main, ["talent", "search", "--tags", "LLM", "-t", "tok"])
        assert result.exit_code == 0

    def test_survey_text_output(self):
        runner = CliRunner()
        with mock.patch("deepxiv_sdk.cli.Reader") as R:
            R.return_value.talent_survey.return_value = SURVEY_RESPONSE
            result = runner.invoke(main, ["talent", "survey", "257", "--no-refresh", "-t", "tok"])
        assert result.exit_code == 0
        assert "bio body" in result.output
        assert "南开大学" in result.output
        assert "FlashRAG" in result.output
        R.return_value.talent_survey.assert_called_once_with(257, refresh=False)

    def test_survey_markdown_output(self):
        runner = CliRunner()
        with mock.patch("deepxiv_sdk.cli.Reader") as R:
            R.return_value.talent_survey.return_value = SURVEY_RESPONSE
            result = runner.invoke(main, ["talent", "survey", "257", "-f", "markdown", "-t", "tok"])
        assert result.exit_code == 0
        assert result.output.strip().startswith("# 窦志成")

    def test_survey_default_refresh_is_unset(self):
        runner = CliRunner()
        with mock.patch("deepxiv_sdk.cli.Reader") as R:
            R.return_value.talent_survey.return_value = SURVEY_RESPONSE
            runner.invoke(main, ["talent", "survey", "257", "-t", "tok"])
        R.return_value.talent_survey.assert_called_once_with(257, refresh=None)

    def test_survey_not_found(self):
        runner = CliRunner()
        with mock.patch("deepxiv_sdk.cli.Reader") as R:
            R.return_value.talent_survey.side_effect = NotFoundError("nope")
            result = runner.invoke(main, ["talent", "survey", "999999", "-t", "tok"])
        assert result.exit_code == 1
        assert "No scholar with ID 999999" in result.output
