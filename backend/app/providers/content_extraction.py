"""Content extraction providers."""

from __future__ import annotations

import re
from collections.abc import Callable
from html import unescape
from urllib.parse import urljoin, urlparse

import httpx

from backend.app.providers.interfaces import ExtractedPage
from backend.app.providers.url_safety import validate_public_http_url

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


class HttpContentExtractionProvider:
    def __init__(
        self,
        timeout: float = 20.0,
        *,
        url_validator: Callable[[str], None] = validate_public_http_url,
        max_redirects: int = 5,
    ) -> None:
        self.timeout = timeout
        self.url_validator = url_validator
        self.max_redirects = max_redirects

    async def extract_url(self, url: str) -> ExtractedPage:
        current_url = url
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            for redirect_index in range(self.max_redirects + 1):
                self.url_validator(current_url)
                response = await client.get(
                    current_url,
                    headers={
                        "User-Agent": "SectorBreaker/0.1 (+local research workbench)",
                        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
                    },
                )
                location = response.headers.get("location")
                if response.status_code in {301, 302, 303, 307, 308} and location:
                    if redirect_index >= self.max_redirects:
                        raise ValueError("too many redirects while extracting URL")
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                break
            else:  # pragma: no cover - defensive; loop exits through break/raise
                raise ValueError("too many redirects while extracting URL")
            content_type = (response.headers.get("content-type") or "").lower()
            text = response.text

        if "html" in content_type or "<html" in text.lower():
            title = _extract_title(text)
            cleaned = _html_to_text(text)
            markdown = cleaned
        else:
            title = None
            cleaned = text.strip()
            markdown = cleaned

        parsed = urlparse(str(response.url))
        return ExtractedPage(
            url=url,
            canonical_url=str(response.url),
            title=title,
            raw_text=cleaned,
            markdown=markdown,
            domain=parsed.netloc or None,
            extraction_provider="http_content",
            extraction_metadata={"content_type": content_type, "status_code": response.status_code},
        )


class FirecrawlContentExtractionProvider:
    def __init__(
        self,
        api_key: str,
        endpoint: str = "https://api.firecrawl.dev/v1/scrape",
        timeout: float = 30.0,
        *,
        url_validator: Callable[[str], None] = validate_public_http_url,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout = timeout
        self.url_validator = url_validator

    async def extract_url(self, url: str) -> ExtractedPage:
        self.url_validator(url)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.endpoint,
                json={
                    "url": url,
                    "formats": ["markdown", "html"],
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json().get("data", {})

        markdown = (data.get("markdown") or "").strip()
        html = data.get("html") or ""
        raw_text = markdown or _html_to_text(html)
        metadata = data.get("metadata") or {}
        canonical_url = metadata.get("sourceURL") or metadata.get("url") or url
        domain = urlparse(canonical_url).netloc or None

        return ExtractedPage(
            url=url,
            canonical_url=canonical_url,
            title=metadata.get("title"),
            raw_text=raw_text,
            markdown=markdown or None,
            published_date=metadata.get("publishedTime"),
            author=metadata.get("author"),
            domain=domain,
            extraction_provider="firecrawl",
            extraction_metadata=metadata,
        )


class JinaReaderContentExtractionProvider:
    def __init__(
        self,
        endpoint_prefix: str = "https://r.jina.ai/http://",
        timeout: float = 30.0,
        *,
        url_validator: Callable[[str], None] = validate_public_http_url,
    ) -> None:
        self.endpoint_prefix = endpoint_prefix
        self.timeout = timeout
        self.url_validator = url_validator

    async def extract_url(self, url: str) -> ExtractedPage:
        self.url_validator(url)
        normalized = url.removeprefix("https://").removeprefix("http://")
        reader_url = f"{self.endpoint_prefix}{normalized}"
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(reader_url)
            response.raise_for_status()
            text = response.text.strip()

        domain = urlparse(url).netloc or None
        title = text.splitlines()[0].strip("# ").strip() if text else None
        return ExtractedPage(
            url=url,
            canonical_url=url,
            title=title or None,
            raw_text=text,
            markdown=text or None,
            domain=domain,
            extraction_provider="jina_reader",
            extraction_metadata={"reader_url": reader_url, "status_code": response.status_code},
        )


def _extract_title(html: str) -> str | None:
    match = _TITLE_RE.search(html)
    if not match:
        return None
    return _WHITESPACE_RE.sub(" ", unescape(match.group(1))).strip() or None


def _html_to_text(html: str) -> str:
    without_scripts = _SCRIPT_STYLE_RE.sub(" ", html)
    without_tags = _TAG_RE.sub(" ", without_scripts)
    normalized = _WHITESPACE_RE.sub(" ", unescape(without_tags)).strip()
    return normalized
