import asyncio

from backend.app.providers.content_extraction import (
    FirecrawlContentExtractionProvider,
    HttpContentExtractionProvider,
    JinaReaderContentExtractionProvider,
)


class _FakeResponse:
    def __init__(self, text: str, content_type: str = "text/html; charset=utf-8", status_code: int = 200, url: str = "https://example.com/page") -> None:
        self.text = text
        self.status_code = status_code
        self.url = url
        self.headers = {"content-type": content_type}

    def raise_for_status(self) -> None:
        return None


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, headers: dict[str, str] | None = None):
        return self.response

    async def post(self, url: str, json: dict | None = None, headers: dict[str, str] | None = None):
        return self.response


def test_http_content_extraction_provider_extracts_html(monkeypatch) -> None:
    class _ClientFactory:
        def __call__(self, *args, **kwargs):
            return _FakeClient(
                _FakeResponse(
                    "<html><head><title>Official Market Report</title></head><body><h1>Market</h1><p>Official data release.</p></body></html>"
                )
            )

    monkeypatch.setattr("backend.app.providers.content_extraction.httpx.AsyncClient", _ClientFactory())

    provider = HttpContentExtractionProvider()
    page = asyncio.run(provider.extract_url("https://example.com/page"))

    assert page.title == "Official Market Report"
    assert "Official data release." in page.raw_text
    assert page.domain == "example.com"


def test_firecrawl_content_extraction_provider_extracts_markdown(monkeypatch) -> None:
    class _ClientFactory:
        def __call__(self, *args, **kwargs):
            return _FakeClient(
                _FakeResponse(
                    text='{"data":{"markdown":"# Official Report\\n\\nGovernment release.","metadata":{"title":"Official Report","sourceURL":"https://data.gov.cn/report","publishedTime":"2026-01-01"}}}',
                    content_type="application/json",
                    url="https://api.firecrawl.dev/v1/scrape",
                )
            )

    def _json(self):
        import json
        return json.loads(self.text)

    monkeypatch.setattr(_FakeResponse, "json", _json, raising=False)
    monkeypatch.setattr("backend.app.providers.content_extraction.httpx.AsyncClient", _ClientFactory())

    provider = FirecrawlContentExtractionProvider(api_key="test-key")
    page = asyncio.run(provider.extract_url("https://data.gov.cn/report"))

    assert page.title == "Official Report"
    assert "Government release." in page.raw_text
    assert page.domain == "data.gov.cn"
    assert page.extraction_provider == "firecrawl"


def test_jina_reader_content_extraction_provider_reads_markdown(monkeypatch) -> None:
    class _ClientFactory:
        def __call__(self, *args, **kwargs):
            return _FakeClient(
                _FakeResponse(
                    "# Reader Title\n\nNormalized page content from reader.",
                    content_type="text/markdown",
                    url="https://r.jina.ai/http://example.com/page",
                )
            )

    monkeypatch.setattr("backend.app.providers.content_extraction.httpx.AsyncClient", _ClientFactory())

    provider = JinaReaderContentExtractionProvider()
    page = asyncio.run(provider.extract_url("https://example.com/page"))

    assert page.title == "Reader Title"
    assert "Normalized page content from reader." in page.raw_text
    assert page.extraction_provider == "jina_reader"
