"""
Unit tests for the Reader class.
"""
import pytest
from unittest import mock
from deepxiv_sdk import (
    Reader,
    APIError,
    BadRequestError,
    AuthenticationError,
    RateLimitError,
    NotFoundError,
    ServerError,
)


class TestReaderInitialization:
    """Test Reader initialization."""

    def test_reader_init_with_token(self):
        """Test Reader initialization with token."""
        reader = Reader(token="test_token")
        assert reader.token == "test_token"
        assert reader.base_url == "https://data.rag.ac.cn"

    def test_reader_init_without_token(self):
        """Test Reader initialization without token."""
        reader = Reader()
        assert reader.token is None

    def test_reader_init_custom_base_url(self):
        """Test Reader initialization with custom base URL."""
        reader = Reader(base_url="https://custom.url/")
        assert reader.base_url == "https://custom.url"

    def test_reader_init_custom_timeout(self):
        """Test Reader initialization with custom timeout."""
        reader = Reader(timeout=120)
        assert reader.timeout == 120

    def test_reader_init_custom_retry_params(self):
        """Test Reader initialization with custom retry parameters."""
        reader = Reader(max_retries=5, retry_delay=2.0)
        assert reader.max_retries == 5
        assert reader.retry_delay == 2.0


class TestSearch:
    """Test search functionality."""

    def test_search_basic(self, mock_reader, sample_search_results):
        """Test basic search."""
        results = mock_reader.search("agent memory")
        assert results["total_count"] == 2
        assert len(results["result"]) == 2
        assert results["result"][0]["arxiv_id"] == "2409.05591"

    def test_search_with_size_limit(self, mock_reader):
        """Test search with size limit."""
        results = mock_reader.search("agent", size=5)
        assert isinstance(results, dict)
        assert "result" in results

    def test_search_with_invalid_size(self, mock_reader):
        """Test search with invalid size."""
        with pytest.raises(ValueError):
            mock_reader.search("query", size=101)

        with pytest.raises(ValueError):
            mock_reader.search("query", size=0)

    def test_search_with_empty_query(self, mock_reader):
        """Test search with empty query."""
        with pytest.raises(ValueError):
            mock_reader.search("")

    def test_search_with_categories(self, mock_reader):
        """Test search with category filters."""
        results = mock_reader.search(
            "transformer", categories=["cs.AI", "cs.CL"]
        )
        assert isinstance(results, dict)

    def test_search_with_date_range(self, mock_reader):
        """Test search with date range."""
        results = mock_reader.search(
            "llm", date_from="2024-01-01", date_to="2024-12-31"
        )
        assert isinstance(results, dict)

    def test_search_with_citation_filter(self, mock_reader):
        """Test search with minimum citation filter."""
        results = mock_reader.search("attention", min_citation=100)
        assert isinstance(results, dict)

    def test_websearch_basic(self, mock_reader):
        """Test websearch."""
        results = mock_reader.websearch("karpathy")
        assert isinstance(results, dict)
        assert results["query"] == "karpathy"
        assert len(results["results"]) == 1

    def test_semantic_scholar_basic(self, mock_reader):
        """Test semantic scholar lookup."""
        results = mock_reader.semantic_scholar("258001")
        assert isinstance(results, dict)
        assert results["id"] == "258001"
        assert results["title"] == "Semantic Scholar Test Paper"


class TestPaperAccess:
    """Test paper access methods."""

    def test_head(self, mock_reader, sample_paper_head):
        """Test getting paper head."""
        head = mock_reader.head("2409.05591")
        assert head["title"] == sample_paper_head["title"]
        assert head["arxiv_id"] == "2409.05591"
        assert len(head["authors"]) == 2

    def test_head_with_invalid_id(self, mock_reader):
        """Test head with invalid ID."""
        with pytest.raises(ValueError):
            mock_reader.head("")

    def test_brief(self, mock_reader, sample_paper_brief):
        """Test getting paper brief."""
        brief = mock_reader.brief("2409.05591")
        assert brief["title"] == sample_paper_brief["title"]
        assert brief["tldr"] is not None

    def test_brief_with_invalid_id(self, mock_reader):
        """Test brief with invalid ID."""
        with pytest.raises(ValueError):
            mock_reader.brief("   ")

    def test_raw(self, mock_reader):
        """Test getting raw paper content."""
        content = mock_reader.raw("2409.05591")
        assert isinstance(content, str)
        assert "Full Paper Content" in content or len(content) > 0

    def test_preview(self, mock_reader):
        """Test getting paper preview."""
        preview = mock_reader.preview("2409.05591")
        assert isinstance(preview, dict)
        assert "content" in preview
        assert preview["is_truncated"] is True

    def test_json(self, mock_reader):
        """Test getting paper as JSON."""
        json_data = mock_reader.json("2409.05591")
        assert isinstance(json_data, dict)

    def test_markdown(self, mock_reader):
        """Test getting paper markdown URL."""
        url = mock_reader.markdown("2409.05591")
        assert "2409.05591" in url
        assert url.startswith("https://arxiv.org/html/")


class TestSectionAccess:
    """Test section access methods."""

    def test_section_basic(self, mock_reader):
        """Test getting a section."""
        section = mock_reader.section("2409.05591", "Introduction")
        assert isinstance(section, str)
        assert len(section) > 0

    def test_section_case_insensitive(self, mock_reader):
        """Test section matching is case-insensitive."""
        section = mock_reader.section("2409.05591", "introduction")
        assert isinstance(section, str)

    def test_section_not_found(self, mock_reader):
        """Test section not found error."""
        with pytest.raises(ValueError, match="not found"):
            mock_reader.section("2409.05591", "NonexistentSection")

    def test_section_invalid_arxiv_id(self, mock_reader):
        """Test section with invalid paper ID."""
        with pytest.raises(ValueError):
            mock_reader.section("", "Introduction")

    def test_section_empty_name(self, mock_reader):
        """Test section with empty section name."""
        with pytest.raises(ValueError):
            mock_reader.section("2409.05591", "")


class TestPMCAccess:
    """Test PMC (PubMed Central) access methods."""

    def test_pmc_head(self, mock_reader, sample_pmc_head):
        """Test getting PMC paper head."""
        with mock.patch.object(
            mock_reader, "_make_request", return_value=sample_pmc_head
        ):
            head = mock_reader.pmc_head("PMC544940")
            assert head["pmc_id"] == "PMC544940" or head.get("title") is not None

    def test_pmc_head_invalid_id(self, mock_reader):
        """Test pmc_head with invalid ID."""
        with pytest.raises(ValueError):
            mock_reader.pmc_head("")

    def test_pmc_full(self, mock_reader):
        """Test getting full PMC paper."""
        with mock.patch.object(
            mock_reader, "_make_request", return_value={"content": "PMC data"}
        ):
            result = mock_reader.pmc_full("PMC544940")
            assert isinstance(result, dict)

    def test_pmc_json_alias(self, mock_reader):
        """Test that pmc_json is an alias for pmc_full."""
        with mock.patch.object(
            mock_reader, "_make_request", return_value={"content": "PMC data"}
        ):
            result1 = mock_reader.pmc_full("PMC544940")
            result2 = mock_reader.pmc_json("PMC544940")
            assert result1 == result2


class TestErrorHandling:
    """Test error handling."""

    def test_authentication_error_on_invalid_token(self, mock_reader_with_errors):
        """Test AuthenticationError on invalid token."""
        with pytest.raises(AuthenticationError):
            mock_reader_with_errors.search("test")

    def test_rate_limit_error(self, mock_reader_with_errors):
        """Test RateLimitError."""
        with pytest.raises(RateLimitError):
            mock_reader_with_errors.search("rate_limit")

    def test_api_error_message_is_helpful(self):
        """Test that API error messages are helpful."""
        try:
            raise AuthenticationError("Invalid token")
        except AuthenticationError as e:
            assert "token" in str(e).lower()

    def test_make_request_preserves_authentication_error(self):
        """Test that AuthenticationError is not wrapped as a generic APIError."""
        reader = Reader(token="bad_token")

        response = mock.Mock()
        response.status_code = 401
        response.text = '{"detail":"invalid token"}'

        with mock.patch("requests.get", return_value=response):
            with pytest.raises(AuthenticationError, match="Invalid or expired token"):
                reader._make_request("https://example.com/protected")

    def test_make_request_preserves_bad_request_error(self):
        """Test that 400 responses are surfaced as BadRequestError."""
        reader = Reader(token="test_token")

        response = mock.Mock()
        response.status_code = 400
        response.text = '{"detail":"bad request"}'

        with mock.patch("requests.get", return_value=response):
            with pytest.raises(BadRequestError, match="Invalid request"):
                reader._make_request("https://example.com/bad")

    def test_make_request_allows_empty_success_response(self):
        """Test that 200 responses with empty bodies are treated as empty payloads."""
        reader = Reader(token="test_token")

        response = mock.Mock()
        response.status_code = 200
        response.content = b""
        response.raise_for_status.return_value = None

        with mock.patch("requests.get", return_value=response):
            assert reader._make_request("https://example.com/empty") == {}


class TestInputValidation:
    """Test input validation."""

    def test_search_validates_size(self, mock_reader):
        """Test search size validation."""
        with pytest.raises(ValueError):
            mock_reader.search("query", size=0)

        with pytest.raises(ValueError):
            mock_reader.search("query", size=101)

    def test_search_validates_offset(self, mock_reader):
        """Test search offset validation."""
        with pytest.raises(ValueError):
            mock_reader.search("query", offset=-1)

    def test_empty_string_validation(self, mock_reader):
        """Test empty string validation."""
        with pytest.raises(ValueError):
            mock_reader.search("")

        with pytest.raises(ValueError):
            mock_reader.head("")

        with pytest.raises(ValueError):
            mock_reader.brief("")

        with pytest.raises(ValueError):
            mock_reader.section("2409.05591", "")


class TestSocialImpactEndpoint:
    """Test social impact endpoint behavior."""

    def test_social_impact_uses_data_domain_with_token_param(self):
        """Test that social impact requests use the data domain and token query param."""
        reader = Reader(token="test_token")

        with mock.patch.object(reader, "_make_request", return_value={}) as mocked_request:
            reader.social_impact("2603.26221")

        mocked_request.assert_called_once_with(
            "https://data.rag.ac.cn/arxiv/trending_signal",
            params={"arxiv_id": "2603.26221", "token": "test_token"},
        )

    def test_social_impact_returns_none_for_empty_response(self):
        """Test that empty successful social impact responses become None."""
        reader = Reader(token="test_token")

        with mock.patch.object(reader, "_make_request", return_value={}):
            assert reader.social_impact("2603.26221") is None
