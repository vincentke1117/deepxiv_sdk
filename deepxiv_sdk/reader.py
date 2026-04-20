"""
Reader class for accessing the arXiv data service API.
Provides typed interface with robust error handling and logging.
"""
import logging
import requests
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

# Configure logger
logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base exception for API errors."""
    pass


class AuthenticationError(APIError):
    """Raised when authentication fails (401, invalid token)."""
    pass


class BadRequestError(APIError):
    """Raised when the request is invalid (400)."""
    pass


class RateLimitError(APIError):
    """Raised when rate limit is exceeded (429)."""
    pass


class NotFoundError(APIError):
    """Raised when requested resource is not found (404)."""
    pass


class ServerError(APIError):
    """Raised when server returns 5xx error."""
    pass


class Reader:
    """Reader for accessing arXiv papers via the data service API.

    Provides comprehensive paper search, metadata retrieval, and content access
    with support for hybrid search (BM25 + Vector) and PMC biomedical literature.

    Attributes:
        token: API token for authentication (optional for free papers)
        base_url: Base URL of the data service
        timeout: Request timeout in seconds (default: 60)
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay: Initial retry delay in seconds (default: 1)
    """

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: str = "https://data.rag.ac.cn",
        timeout: int = 60,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """
        Initialize the Reader.

        Args:
            token: API token for authentication (optional for free papers)
            base_url: Base URL of the data service (default: https://data.rag.ac.cn)
            timeout: Request timeout in seconds (default: 60)
            max_retries: Maximum number of retry attempts (default: 3)
            retry_delay: Initial retry delay in seconds (default: 1.0)
        """
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.arxiv_endpoint = f"{self.base_url}/arxiv/"
        self.pmc_endpoint = f"{self.base_url}/pmc/"
        self.websearch_endpoint = f"{self.base_url}/websearch"
        self.semantic_scholar_endpoint = f"{self.base_url}/semantic_scholar"
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        logger.debug(
            f"Reader initialized with base_url={self.base_url}, "
            f"token={'***' if token else 'None'}"
        )

    def _make_request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """
        Make a request to the API with retry logic and comprehensive error handling.

        Args:
            url: URL to request
            params: Query parameters
            retry_count: Current retry attempt number (internal use)

        Returns:
            Response JSON or None if max retries exceeded

        Raises:
            BadRequestError: Invalid request parameters or malformed IDs (400)
            AuthenticationError: Invalid or expired token (401)
            RateLimitError: Daily limit reached (429)
            NotFoundError: Resource not found (404)
            ServerError: Server error (5xx)
            APIError: Other API errors
        """
        headers: Dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            logger.debug(f"Making request to {url} with params {params}")
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )

            # Handle HTTP errors with appropriate exceptions
            if response.status_code == 400:
                logger.warning(f"Bad request to {url}: {response.text}")
                raise BadRequestError(
                    "Invalid request. Please check your arXiv/PMC ID or command arguments."
                )
            elif response.status_code == 401:
                logger.error("Authentication failed: Invalid or expired token")
                raise AuthenticationError(
                    "Invalid or expired token. Run 'deepxiv config' to set a valid token."
                )
            elif response.status_code == 404:
                logger.warning(f"Resource not found: {url}")
                raise NotFoundError(f"Paper not found. Check your arXiv/PMC ID.")
            elif response.status_code == 429:
                logger.warning("Rate limit exceeded")
                raise RateLimitError(
                    "Daily limit reached. Email tommy@chien.io for higher limits."
                )
            elif response.status_code >= 500:
                logger.error(f"Server error {response.status_code}: {response.text}")
                raise ServerError(f"Server error {response.status_code}")

            response.raise_for_status()
            if not response.content:
                logger.debug(f"Empty response body from {url}")
                return {}
            result = response.json()
            logger.debug(f"Successfully received response from {url}")
            return result

        except APIError:
            raise

        except requests.exceptions.Timeout as e:
            if retry_count < self.max_retries:
                wait_time = self.retry_delay * (2 ** retry_count)
                logger.warning(
                    f"Request timeout (attempt {retry_count + 1}/{self.max_retries}), "
                    f"retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
                return self._make_request(url, params, retry_count + 1)
            else:
                logger.error(f"Request timeout after {self.max_retries} retries")
                raise APIError(
                    f"Request timed out after {self.max_retries} retries. "
                    "Check your internet connection or try again later."
                )

        except requests.exceptions.ConnectionError as e:
            if retry_count < self.max_retries:
                wait_time = self.retry_delay * (2 ** retry_count)
                logger.warning(
                    f"Connection error (attempt {retry_count + 1}/{self.max_retries}), "
                    f"retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
                return self._make_request(url, params, retry_count + 1)
            else:
                logger.error(f"Connection error after {self.max_retries} retries")
                raise APIError(
                    f"Failed to connect to {url}. "
                    "Check your internet connection or try again later."
                )

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e}")
            raise APIError(f"HTTP error {e.response.status_code}: {str(e)}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise APIError(f"Request failed: {str(e)}")

        except ValueError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            raise APIError(f"Invalid response format: {str(e)}")

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise APIError(f"Unexpected error: {str(e)}")

    def _make_post_request(
        self,
        url: str,
        json_data: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """
        Make a POST request to the API with retry logic and comprehensive error handling.

        Args:
            url: URL to request
            json_data: JSON request body
            retry_count: Current retry attempt number (internal use)

        Returns:
            Response JSON or None if max retries exceeded

        Raises:
            BadRequestError: Invalid request parameters or malformed IDs (400)
            AuthenticationError: Invalid or expired token (401)
            RateLimitError: Daily limit reached (429)
            ServerError: Server error (5xx)
            APIError: Other API errors
        """
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            logger.debug(f"Making POST request to {url} with json {json_data}")
            response = requests.post(
                url,
                json=json_data,
                headers=headers,
                timeout=self.timeout,
            )

            if response.status_code == 400:
                logger.warning(f"Bad request to {url}: {response.text}")
                raise BadRequestError(
                    "Invalid request. Please check your query or command arguments."
                )
            elif response.status_code == 401:
                logger.error("Authentication failed: Invalid or expired token")
                raise AuthenticationError(
                    "Invalid or expired token. Run 'deepxiv config' to set a valid token."
                )
            elif response.status_code == 429:
                logger.warning("Rate limit exceeded")
                raise RateLimitError(
                    "Daily limit reached. Visit https://data.rag.ac.cn/register for a higher limit."
                )
            elif response.status_code >= 500:
                logger.error(f"Server error {response.status_code}: {response.text}")
                raise ServerError(f"Server error {response.status_code}")

            response.raise_for_status()
            if not response.content:
                logger.debug(f"Empty response body from {url}")
                return {}
            result = response.json()
            logger.debug(f"Successfully received POST response from {url}")
            return result

        except APIError:
            raise

        except requests.exceptions.Timeout:
            if retry_count < self.max_retries:
                wait_time = self.retry_delay * (2 ** retry_count)
                logger.warning(
                    f"POST request timeout (attempt {retry_count + 1}/{self.max_retries}), "
                    f"retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
                return self._make_post_request(url, json_data, retry_count + 1)
            raise APIError(
                f"Request timed out after {self.max_retries} retries. "
                "Check your internet connection or try again later."
            )

        except requests.exceptions.ConnectionError:
            if retry_count < self.max_retries:
                wait_time = self.retry_delay * (2 ** retry_count)
                logger.warning(
                    f"POST connection error (attempt {retry_count + 1}/{self.max_retries}), "
                    f"retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
                return self._make_post_request(url, json_data, retry_count + 1)
            raise APIError(
                f"Failed to connect to {url}. "
                "Check your internet connection or try again later."
            )

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e}")
            raise APIError(f"HTTP error {e.response.status_code}: {str(e)}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            raise APIError(f"Request failed: {str(e)}")

        except ValueError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            raise APIError(f"Invalid response format: {str(e)}")

        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise APIError(f"Unexpected error: {str(e)}")

    # Sources supported by the unified retrieve endpoint.
    _RETRIEVE_SOURCES = ("arxiv", "biorxiv", "medrxiv")
    # Date filter modes accepted by the upstream service.
    _DATE_SEARCH_TYPES = ("between", "exact", "after", "before")

    def search(
        self,
        query: str,
        size: int = 10,
        offset: int = 0,
        source: str = "arxiv",
        categories: Optional[List[str]] = None,
        authors: Optional[List[str]] = None,
        orgs: Optional[List[str]] = None,
        min_citation: Optional[int] = None,
        date_search_type: Optional[str] = None,
        date_str: Optional[Any] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        use_fine_rerank: bool = False,
        # Deprecated: kept for backward compatibility, no longer sent upstream.
        search_mode: Optional[str] = None,
        bm25_weight: Optional[float] = None,
        vector_weight: Optional[float] = None,
        top_k: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Semantic search across arXiv / bioRxiv / medRxiv.

        Calls the unified retrieve endpoint
        ``GET https://data.rag.ac.cn/arxiv/?type=retrieve``.

        Args:
            query: Search query string (max 500 characters).
            size: Number of results to return (default: 10, range 1~100).
                Mapped to the upstream ``top_k`` parameter.
            offset: Pagination offset (default: 0, range 0~10000).
            source: Paper source: ``"arxiv"`` (default), ``"biorxiv"``, or
                ``"medrxiv"``.
            categories: Filter by categories (e.g., ``["cs.CV", "cs.CL"]``).
                Filter only, does not affect ranking.
            authors: Author name filter; also influences ranking.
            orgs: Organization name filter; also influences ranking.
            min_citation: Minimum citation count filter.
            date_search_type: One of ``"between"``, ``"exact"``, ``"after"``,
                ``"before"``. Must be paired with ``date_str``.
            date_str: Date string in ``YYYY`` / ``YYYY-MM`` / ``YYYY-MM-DD``.
                When ``date_search_type="between"``, must be a two-element
                ``[start, end]`` list.
            date_from: Convenience legacy param. When provided without
                ``date_search_type``, it is mapped automatically:
                ``date_from`` + ``date_to`` → ``between``;
                only ``date_from`` → ``after``;
                only ``date_to`` → ``before``.
            date_to: See ``date_from``.
            use_fine_rerank: Whether to enable upstream fine reranking.
                Default: ``False`` (the SDK opts out by default; the upstream
                default is ``True``).
            search_mode / bm25_weight / vector_weight: Deprecated. The unified
                retrieve endpoint no longer supports them; values are ignored.
            top_k: Optional explicit ``top_k`` override. If provided, takes
                precedence over ``size``.

        Returns:
            Dictionary with the upstream response shape::

                {
                    "status": "success",
                    "total_count": <int>,
                    "result": [ { "arxiv_id" | "biorxiv_id" | "medrxiv_id": ..., ... }, ... ]
                }

            The ID field on each item depends on ``source``.

        Raises:
            ValueError: On invalid arguments.
            APIError: If the upstream request fails.
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if source not in self._RETRIEVE_SOURCES:
            raise ValueError(
                f"source must be one of {list(self._RETRIEVE_SOURCES)}"
            )
        effective_top_k = top_k if top_k is not None else size
        if effective_top_k < 1 or effective_top_k > 100:
            raise ValueError("size/top_k must be between 1 and 100")
        if offset < 0 or offset > 10000:
            raise ValueError("offset must be between 0 and 10000")

        if search_mode is not None or bm25_weight is not None or vector_weight is not None:
            logger.warning(
                "search_mode / bm25_weight / vector_weight are deprecated and "
                "ignored by the unified retrieve endpoint."
            )

        # Resolve date filter: prefer explicit date_search_type/date_str.
        resolved_date_type = date_search_type
        resolved_date_str: Any = date_str
        if resolved_date_type is None and (date_from or date_to):
            if date_from and date_to:
                resolved_date_type = "between"
                resolved_date_str = [date_from, date_to]
            elif date_from:
                resolved_date_type = "after"
                resolved_date_str = date_from
            else:
                resolved_date_type = "before"
                resolved_date_str = date_to

        if resolved_date_type is not None:
            if resolved_date_type not in self._DATE_SEARCH_TYPES:
                raise ValueError(
                    f"date_search_type must be one of {list(self._DATE_SEARCH_TYPES)}"
                )
            if resolved_date_str is None:
                raise ValueError(
                    "date_str is required when date_search_type is provided"
                )
            if resolved_date_type == "between":
                if not (
                    isinstance(resolved_date_str, (list, tuple))
                    and len(resolved_date_str) == 2
                ):
                    raise ValueError(
                        "date_str must be [start, end] when date_search_type='between'"
                    )
        elif resolved_date_str is not None:
            raise ValueError(
                "date_search_type is required when date_str is provided"
            )

        # Build params; lists are passed as repeated keys by `requests`.
        params: Dict[str, Any] = {
            "type": "retrieve",
            "query": query,
            "source": source,
            "top_k": effective_top_k,
            "offset": offset,
            # The SDK opts out of fine rerank by default.
            "use_fine_rerank": "true" if use_fine_rerank else "false",
        }
        if self.token:
            params["token"] = self.token

        if categories:
            params["categories"] = list(categories)
        if authors:
            params["authors"] = list(authors)
        if orgs:
            params["orgs"] = list(orgs)
        if min_citation is not None:
            params["min_citation"] = min_citation
        if resolved_date_type is not None:
            params["date_search_type"] = resolved_date_type
            params["date_str"] = (
                list(resolved_date_str)
                if isinstance(resolved_date_str, (list, tuple))
                else resolved_date_str
            )

        result = self._make_request(self.arxiv_endpoint, params=params)
        result = result or {"status": "success", "total_count": 0, "result": []}
        logger.info(
            f"Search for '{query}' (source={source}) "
            f"returned {result.get('total_count', 0)} results"
        )
        return result

    def websearch(self, query: str) -> Dict[str, Any]:
        """
        Search the web with the DeepXiv websearch endpoint.

        Args:
            query: Search query string

        Returns:
            Dictionary response from the websearch endpoint

        Raises:
            APIError: If the request fails
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        result = self._make_post_request(
            self.websearch_endpoint,
            json_data={"query": query},
        )
        logger.info(f"Websearch for '{query}' completed")
        return result or {}

    def semantic_scholar(self, semantic_scholar_id: str) -> Dict[str, Any]:
        """
        Get paper information by Semantic Scholar ID.

        Args:
            semantic_scholar_id: Semantic Scholar paper ID (e.g., "258001")

        Returns:
            Dictionary response from the semantic scholar endpoint

        Raises:
            APIError: If the request fails
        """
        if not semantic_scholar_id or not str(semantic_scholar_id).strip():
            raise ValueError("semantic_scholar_id cannot be empty")

        params: Dict[str, Any] = {
            "id": str(semantic_scholar_id).strip(),
            "token": self.token or "",
        }
        result = self._make_request(self.semantic_scholar_endpoint, params=params)
        logger.info(f"Semantic Scholar lookup for '{semantic_scholar_id}' completed")
        return result or {}

    def head(self, arxiv_id: str) -> Dict[str, Any]:
        """
        Get paper metadata and structure (head information).

        Args:
            arxiv_id: arXiv ID (e.g., "2409.05591", "2504.21776")

        Returns:
            Dictionary with paper head information including:
            - title: Paper title
            - abstract: Paper abstract
            - authors: List of authors
            - sections: List of section information
            - token_count: Total tokens in the paper
            - categories: arXiv categories
            - publish_at: Publication date

        Raises:
            APIError: If the request fails
        """
        if not arxiv_id or not arxiv_id.strip():
            raise ValueError("arxiv_id cannot be empty")

        params: Dict[str, Any] = {"arxiv_id": arxiv_id, "type": "head"}
        result = self._make_request(self.arxiv_endpoint, params=params)
        return result or {}

    def brief(self, arxiv_id: str) -> Dict[str, Any]:
        """
        Get brief paper information (concise summary for quick overview).

        Args:
            arxiv_id: arXiv ID (e.g., "2409.05591", "2504.21776")

        Returns:
            Dictionary with brief paper information including:
            - arxiv_id: arXiv paper ID
            - title: Paper title
            - tldr: AI-generated summary (if available)
            - keywords: List of keywords (if available)
            - publish_at: Publication date
            - citations: Citation count
            - src_url: Direct link to PDF
            - github_url: Associated GitHub repository URL (if available)

        Raises:
            APIError: If the request fails
        """
        if not arxiv_id or not arxiv_id.strip():
            raise ValueError("arxiv_id cannot be empty")

        params: Dict[str, Any] = {"arxiv_id": arxiv_id, "type": "brief"}
        result = self._make_request(self.arxiv_endpoint, params=params)
        return result or {}

    def _match_section_name(self, arxiv_id: str, section_name: str) -> Optional[str]:
        """
        Match user input to actual section name (case-insensitive, partial match).

        Args:
            arxiv_id: arXiv ID
            section_name: User-provided section name (e.g., "Introduction", "introduction")

        Returns:
            Matched section name or None if not found
        """
        head = self.head(arxiv_id)
        if not head or "sections" not in head:
            return None

        sections: List[Dict[str, Any]] = head.get("sections", [])
        section_lower = section_name.lower()

        # Extract section names
        section_names = [
            section["name"] if isinstance(section, dict) else str(section)
            for section in sections
        ]

        # Try exact match first (case-insensitive)
        for name in section_names:
            if name.lower() == section_lower:
                return name

        # Try partial match (section name contains the query)
        for name in section_names:
            # Remove leading numbers like "1. " or "2. "
            clean_name = name.lower()
            if clean_name.startswith(tuple(f"{i}. " for i in range(10))):
                clean_name = clean_name[3:]

            if clean_name == section_lower or section_lower in clean_name:
                return name

        logger.warning(
            f"Section '{section_name}' not found in paper {arxiv_id}. "
            f"Available sections: {', '.join(section_names)}"
        )
        return None

    def section(self, arxiv_id: str, section_name: str) -> str:
        """
        Get a specific section content from a paper.

        Args:
            arxiv_id: arXiv ID (e.g., "2409.05591")
            section_name: Name of the section (e.g., "Introduction", "introduction", "Method")
                         Case-insensitive, partial match supported.

        Returns:
            Section content as string

        Raises:
            APIError: If the request fails
            ValueError: If section is not found
        """
        if not arxiv_id or not arxiv_id.strip():
            raise ValueError("arxiv_id cannot be empty")
        if not section_name or not section_name.strip():
            raise ValueError("section_name cannot be empty")

        # Match section name (case-insensitive)
        matched_name = self._match_section_name(arxiv_id, section_name)
        if not matched_name:
            raise ValueError(
                f"Section '{section_name}' not found in paper {arxiv_id}"
            )

        params: Dict[str, Any] = {
            "arxiv_id": arxiv_id,
            "type": "section",
            "section": matched_name,
        }
        result = self._make_request(self.arxiv_endpoint, params=params)

        return result.get("content", "") if result else ""

    def raw(self, arxiv_id: str) -> str:
        """
        Get the full paper content in markdown format.

        Args:
            arxiv_id: arXiv ID (e.g., "2409.05591")

        Returns:
            Full paper content as markdown string

        Raises:
            APIError: If the request fails
        """
        if not arxiv_id or not arxiv_id.strip():
            raise ValueError("arxiv_id cannot be empty")

        params: Dict[str, Any] = {"arxiv_id": arxiv_id, "type": "raw"}
        result = self._make_request(self.arxiv_endpoint, params=params)

        return result.get("raw", "") if result else ""

    def preview(self, arxiv_id: str) -> Dict[str, Any]:
        """
        Get a preview of the paper (first 10,000 characters).
        Useful for mobile devices or when you want to quickly scan the introduction.

        Args:
            arxiv_id: arXiv ID (e.g., "2409.05591")

        Returns:
            Dictionary with preview information including:
            - content: First 10,000 characters
            - is_truncated: Whether content was truncated
            - total_characters: Total characters in full document

        Raises:
            APIError: If the request fails
        """
        if not arxiv_id or not arxiv_id.strip():
            raise ValueError("arxiv_id cannot be empty")

        params: Dict[str, Any] = {"arxiv_id": arxiv_id, "type": "preview"}
        result = self._make_request(self.arxiv_endpoint, params=params)

        return result or {"content": "", "is_truncated": False}

    def json(self, arxiv_id: str) -> Dict[str, Any]:
        """
        Get the complete structured JSON file with all sections and metadata.

        Args:
            arxiv_id: arXiv ID (e.g., "2409.05591")

        Returns:
            Complete structured JSON with all paper data

        Raises:
            APIError: If the request fails
        """
        if not arxiv_id or not arxiv_id.strip():
            raise ValueError("arxiv_id cannot be empty")

        params: Dict[str, Any] = {"arxiv_id": arxiv_id, "type": "json"}
        result = self._make_request(self.arxiv_endpoint, params=params)

        return result or {}

    def markdown(self, arxiv_id: str) -> str:
        """
        Get the HTML view URL for the paper.

        Args:
            arxiv_id: arXiv ID (e.g., "2409.05591")

        Returns:
            URL to the HTML view of the paper
        """
        if not arxiv_id or not arxiv_id.strip():
            raise ValueError("arxiv_id cannot be empty")

        return f"https://arxiv.org/html/{arxiv_id}"

    # ========== PMC (PubMed Central) Methods ==========

    def pmc_head(self, pmc_id: str) -> Dict[str, Any]:
        """
        Get PMC paper metadata (title, abstract, authors, categories, publication date).

        Args:
            pmc_id: PMC ID (e.g., "PMC544940", "PMC514704")

        Returns:
            Dictionary with PMC paper metadata including:
            - pmc_id: PMC paper ID
            - title: Paper title
            - doi: Digital Object Identifier
            - abstract: Paper abstract
            - authors: List of authors
            - categories: Medical subject categories
            - publish_at: Publication date

        Raises:
            APIError: If the request fails
        """
        if not pmc_id or not pmc_id.strip():
            raise ValueError("pmc_id cannot be empty")

        params: Dict[str, Any] = {"pmc_id": pmc_id, "type": "head"}
        result = self._make_request(self.pmc_endpoint, params=params)

        return result or {}

    def pmc_full(self, pmc_id: str) -> Dict[str, Any]:
        """
        Get the complete PMC paper in structured JSON format with full content and metadata.

        Args:
            pmc_id: PMC ID (e.g., "PMC544940", "PMC514704")

        Returns:
            Complete structured JSON with all PMC paper data

        Raises:
            APIError: If the request fails
        """
        if not pmc_id or not pmc_id.strip():
            raise ValueError("pmc_id cannot be empty")

        params: Dict[str, Any] = {"pmc_id": pmc_id, "type": "json"}
        result = self._make_request(self.pmc_endpoint, params=params)

        return result or {}

    # Alias for backwards compatibility
    def pmc_json(self, pmc_id: str) -> Dict[str, Any]:
        """Alias for pmc_full(). Get the complete PMC paper in JSON format."""
        return self.pmc_full(pmc_id)

    # ========== Trending Methods ==========

    def trending(
        self,
        days: int = 7,
        limit: int = 30,
    ) -> Dict[str, Any]:
        """
        Get trending arXiv papers.

        Args:
            days: Number of days to look back (7, 14, or 30). Default: 7
            limit: Maximum number of papers to return. Default: 30

        Returns:
            Dictionary with trending papers including:
            - papers: List of trending paper objects with metadata
            - total: Total number of trending papers available
            - days: The days parameter used
            - generated_at: Timestamp when the trending list was generated

        Raises:
            ValueError: If days or limit are invalid
            APIError: If the request fails
        """
        if days not in [7, 14, 30]:
            raise ValueError("days must be 7, 14, or 30")
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")

        # Use the trending API endpoint (no token required)
        trending_url = "https://api.rag.ac.cn/trending_arxiv_papers/api/trending"
        params: Dict[str, Any] = {
            "days": days,
            "limit": limit,
        }

        result = self._make_request(trending_url, params=params)

        # Extract data from nested response structure
        if result and "data" in result:
            data = result["data"]
            logger.info(f"Retrieved {len(data.get('papers', []))} trending papers for last {days} days")
            return data

        logger.info(f"No trending data available for {days} days")
        return {"papers": [], "total": 0}

    # ========== Social Impact Methods ==========

    def social_impact(self, arxiv_id: str) -> Optional[Dict[str, Any]]:
        """
        Get social media impact metrics for an arXiv paper (trending signal).

        Args:
            arxiv_id: arXiv ID (e.g., "2409.05592", "2506.00002")

        Returns:
            Dictionary with social impact metrics including:
            - total_tweets: Number of tweets mentioning the paper
            - total_likes: Total likes across social media
            - total_views: Number of views
            - total_replies: Number of replies/comments
            - first_seen_date: When the paper first appeared in trending (ISO format)
            - last_seen_date: Most recent trending activity (ISO format)
            - arxiv_id: The paper ID

            Returns None if no data is found for the paper.

        Raises:
            ValueError: If arxiv_id is invalid
            AuthenticationError: If token is missing or invalid (required for this endpoint)
            APIError: If the request fails
        """
        if not arxiv_id or not arxiv_id.strip():
            raise ValueError("arxiv_id cannot be empty")

        if not self.token:
            raise AuthenticationError(
                "Token is required for social impact queries. "
                "Provide a token when initializing Reader: Reader(token='your_token')"
            )

        params: Dict[str, Any] = {
            "arxiv_id": arxiv_id,
            "token": self.token,
        }
        try:
            # Social impact data is served from the data.rag.ac.cn domain and
            # expects the token in query params for compatibility.
            signal_url = f"{self.base_url}/arxiv/trending_signal"
            result = self._make_request(signal_url, params=params)
            logger.info(f"Retrieved social impact metrics for {arxiv_id}")
            return result or None
        except NotFoundError:
            logger.warning(f"No social impact data found for {arxiv_id}")
            return None

    # ========== bioRxiv / medRxiv Methods ==========

    def biomed_search(
        self,
        query: str,
        source: str = "biorxiv",
        top_k: int = 10,
        authors: Optional[List[str]] = None,
        orgs: Optional[List[str]] = None,
        date_search_type: Optional[str] = None,
        date_str: Optional[Any] = None,
        use_fine_rerank: bool = False,
        **_legacy_kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Search bioRxiv / medRxiv preprints.

        Thin wrapper around :meth:`search` for backward compatibility. The
        unified ``/arxiv/?type=retrieve`` endpoint now serves all sources.

        Args:
            query: Search query string.
            source: ``"biorxiv"`` or ``"medrxiv"`` (default: ``"biorxiv"``).
            top_k: Number of results to return (default: 10).
            authors: Author name filter.
            orgs: Organization name filter.
            date_search_type: ``"between"`` / ``"exact"`` / ``"after"`` /
                ``"before"``.
            date_str: See :meth:`search`.
            use_fine_rerank: Whether to enable upstream fine reranking
                (default: ``False``).

        Returns:
            ``{"status": ..., "total_count": ..., "result": [...]}``

        Note:
            Legacy keyword arguments such as ``return_contents`` are silently
            ignored to preserve backwards compatibility with older callers.
        """
        if source not in ("biorxiv", "medrxiv"):
            raise ValueError('source must be "biorxiv" or "medrxiv"')
        if _legacy_kwargs:
            logger.debug(
                "biomed_search: ignoring legacy kwargs %s", list(_legacy_kwargs)
            )

        return self.search(
            query=query,
            size=top_k,
            source=source,
            authors=authors,
            orgs=orgs,
            date_search_type=date_search_type,
            date_str=date_str,
            use_fine_rerank=use_fine_rerank,
        )

    def biomed_data(
        self,
        source_id: str,
        source: str = "biorxiv",
        data_type: str = "metadata",
        section_names: Optional[List[str]] = None,
        roc_num: Optional[int] = None,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve a single bioRxiv / medRxiv paper's data.

        Args:
            source_id: Paper DOI, e.g. "10.1101/2021.02.26.433129"
            source: "biorxiv" or "medrxiv" (default: "biorxiv")
            data_type: "metadata" | "section" | "roc" (default: "metadata")
            section_names: List of section names to retrieve (used when data_type="section")
            roc_num: Number of cited-by-reason entries (used when data_type="roc")
            fields: Comma-separated field filter

        Returns:
            Dictionary with paper data

        Raises:
            ValueError: If source or data_type is invalid
            APIError: If the request fails
        """
        if source not in ("biorxiv", "medrxiv"):
            raise ValueError('source must be "biorxiv" or "medrxiv"')
        if data_type not in ("metadata", "section", "roc"):
            raise ValueError('data_type must be "metadata", "section", or "roc"')
        if not source_id or not source_id.strip():
            raise ValueError("source_id cannot be empty")

        url = f"{self.base_url}/{source}/data"
        params: Dict[str, Any] = {
            "source_id": source_id.strip(),
            "type": data_type,
        }
        if section_names:
            params["section_names"] = (
                ",".join(section_names)
                if isinstance(section_names, list)
                else section_names
            )
        if roc_num is not None:
            params["roc_num"] = roc_num
        if fields:
            params["fields"] = fields

        result = self._make_request(url, params=params)
        logger.info(f"biomed_data (source={source}, type={data_type}) for '{source_id}' completed")
        return result or {}
