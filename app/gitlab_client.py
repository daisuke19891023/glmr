"""Async GitLab API client with retry and pagination helpers."""

import asyncio
import logging
from types import TracebackType
from typing import Any, Self, TYPE_CHECKING, cast
from collections.abc import AsyncIterator, Mapping

import httpx
from tenacity import AsyncRetrying, RetryError, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

if TYPE_CHECKING:
    from app.config import AppSettings

LOGGER = logging.getLogger(__name__)

_RETRY_FAILURE_MESSAGE = "GitLab API request failed after retries"
_RATE_LIMIT_STATUS = 429
_SERVER_ERROR_LOWER = 500
_SERVER_ERROR_UPPER = 600
_UNEXPECTED_PAYLOAD_MESSAGE = "Unexpected response payload type"


class RateLimitError(RuntimeError):
    """Raised when the GitLab API responds with a rate limit status."""

    def __init__(self, retry_after: float | None = None) -> None:
        """Store the retry delay suggested by the server."""
        super().__init__("GitLab API rate limit encountered")
        self.retry_after = retry_after or 1.0


class GitLabAPIError(RuntimeError):
    """Raised when the GitLab API returns a non-retryable error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        """Attach HTTP status metadata to the exception instance."""
        super().__init__(message)
        self.status_code = status_code


class GitLabClient:
    """High-level asynchronous client for interacting with the GitLab REST API."""

    def __init__(
        self,
        settings: "AppSettings",
        *,
        timeout: float = 60.0,
        max_attempts: int = 5,
    ) -> None:
        """Configure the HTTP client with authentication headers and retry policy."""
        self._settings = settings
        headers = {
            "User-Agent": "glmr-collector/0.1",
            "Accept": "application/json",
        }
        token = settings.gitlab_token.get_secret_value()
        if token:
            headers["PRIVATE-TOKEN"] = token
        self._client = httpx.AsyncClient(
            base_url=str(settings.gitlab_api_base),
            headers=headers,
            timeout=httpx.Timeout(timeout),
        )
        self._max_attempts = max_attempts

    async def __aenter__(self) -> Self:
        """Enter the async context manager and return the client."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Ensure the underlying HTTP client is closed when exiting the context."""
        del exc_type, exc, tb
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Perform an HTTP request with retry and rate limit handling."""
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self._max_attempts),
            retry=retry_if_exception_type((RateLimitError, httpx.HTTPStatusError, httpx.TransportError)),
            wait=wait_exponential_jitter(initial=1, max=10),
            reraise=True,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    response = await self._client.request(method, path, params=params, headers=headers)
                    if response.status_code == _RATE_LIMIT_STATUS:
                        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                        LOGGER.warning("Rate limit hit, retrying in %ss", retry_after)
                        await asyncio.sleep(retry_after)
                        raise RateLimitError(retry_after)
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        status_code = exc.response.status_code
                        if _SERVER_ERROR_LOWER <= status_code < _SERVER_ERROR_UPPER:
                            raise
                        error_message = (
                            f"GitLab API returned {status_code}: {exc.response.text}"
                        )
                        raise GitLabAPIError(
                            error_message,
                            status_code=status_code,
                        ) from exc
                    return response
        except RetryError as exc:  # pragma: no cover - defensive
            raise GitLabAPIError(_RETRY_FAILURE_MESSAGE) from exc
        raise GitLabAPIError(_RETRY_FAILURE_MESSAGE)

    async def paginate(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Iterate over paginated GitLab API responses."""
        current_params: dict[str, Any] = {"per_page": self._settings.per_page}
        if params:
            current_params.update(params)

        while True:
            response = await self.request(method, path, params=current_params, headers=headers)
            payload = self.parse_json(response)
            if isinstance(payload, list):
                data_iter = cast("list[dict[str, Any]]", payload)
            elif isinstance(payload, dict):
                payload_dict: dict[str, Any] = cast("dict[str, Any]", payload)
                raw_value: object = payload_dict.get("data", [])
                if not isinstance(raw_value, list):
                    raise GitLabAPIError(_UNEXPECTED_PAYLOAD_MESSAGE)
                data_iter = cast("list[dict[str, Any]]", raw_value)
            else:
                raise GitLabAPIError(_UNEXPECTED_PAYLOAD_MESSAGE)
            for item in data_iter:
                yield item
            next_page = response.headers.get("X-Next-Page")
            if not next_page:
                break
            current_params["page"] = next_page


    def parse_json(self, response: httpx.Response) -> Any:
        """Decode a JSON response or raise a GitLabAPIError on failure."""
        try:
            return response.json()
        except ValueError as exc:
            content_type = response.headers.get("Content-Type", "unknown")
            message = (
                "GitLab API returned an invalid JSON payload "
                f"(status {response.status_code}, content-type {content_type})"
            )
            raise GitLabAPIError(message, status_code=response.status_code) from exc


def _parse_retry_after(value: str | None) -> float:
    if not value:
        return 1.0
    try:
        return float(value)
    except ValueError:  # pragma: no cover - defensive against non-numeric headers
        return 1.0
