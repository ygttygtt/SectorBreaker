"""Generate minimal .env snippets for real search-provider onboarding."""

from __future__ import annotations

import os
from pathlib import Path
import sys


SEARCH_PROVIDER_SNIPPETS = {
    "tavily": [
        "SEARCH_PROVIDER_MODE=tavily",
        "TAVILY_API_KEY=YOUR_TAVILY_API_KEY",
        "TAVILY_ENDPOINT=https://api.tavily.com/search",
    ],
    "serper": [
        "SEARCH_PROVIDER_MODE=serper",
        "SERPER_API_KEY=YOUR_SERPER_API_KEY",
        "SERPER_ENDPOINT=https://google.serper.dev/search",
    ],
    "brave": [
        "SEARCH_PROVIDER_MODE=brave",
        "BRAVE_API_KEY=YOUR_BRAVE_API_KEY",
        "BRAVE_ENDPOINT=https://api.search.brave.com/res/v1/web/search",
    ],
    "exa": [
        "SEARCH_PROVIDER_MODE=exa",
        "EXA_API_KEY=YOUR_EXA_API_KEY",
        "EXA_ENDPOINT=https://api.exa.ai/search",
    ],
    "firecrawl": [
        "SEARCH_PROVIDER_MODE=firecrawl",
        "FIRECRAWL_API_KEY=YOUR_FIRECRAWL_API_KEY",
        "FIRECRAWL_SEARCH_ENDPOINT=https://api.firecrawl.dev/v2/search",
    ],
}

EXTRACTION_PROVIDER_SNIPPETS = {
    "http": [
        "CONTENT_EXTRACTION_PROVIDER=http",
    ],
    "firecrawl": [
        "CONTENT_EXTRACTION_PROVIDER=firecrawl",
        "FIRECRAWL_API_KEY=YOUR_FIRECRAWL_API_KEY",
        "FIRECRAWL_ENDPOINT=https://api.firecrawl.dev/v1/scrape",
    ],
    "jina": [
        "CONTENT_EXTRACTION_PROVIDER=jina",
        "JINA_READER_ENDPOINT_PREFIX=https://r.jina.ai/http://",
    ],
}


def build_template(search_provider: str, extraction_provider: str) -> str:
    normalized_search_provider = search_provider.strip().lower()
    normalized_extraction_provider = extraction_provider.strip().lower()

    if normalized_search_provider not in SEARCH_PROVIDER_SNIPPETS:
        raise ValueError(f"Unsupported search provider: {search_provider}")
    if normalized_extraction_provider not in EXTRACTION_PROVIDER_SNIPPETS:
        raise ValueError(f"Unsupported extraction provider: {extraction_provider}")

    lines = [
        "# Minimal real-search onboarding template",
        "# Fill the API key values, save as .env, then run:",
        "#   python run_real_search_acceptance.py",
        "",
        "# LLM",
        "LLM_BASE_URL=",
        "LLM_API_KEY=",
        "LLM_MODEL=",
        "",
        "# Search",
        *SEARCH_PROVIDER_SNIPPETS[normalized_search_provider],
        "",
        "# Extraction",
        *EXTRACTION_PROVIDER_SNIPPETS[normalized_extraction_provider],
        "",
        "# Local runtime paths",
        "SECTORBREAKER_DB_PATH=data/sectorbreaker.sqlite3",
        "SECTORBREAKER_EXPORT_ROOT=exports",
    ]
    return "\n".join(lines) + "\n"


def _parse_args(args: list[str]) -> tuple[str, str, Path | None]:
    positional: list[str] = []
    write_path: Path | None = None
    index = 0
    while index < len(args):
        current = args[index]
        if current == "--write":
            if index + 1 >= len(args):
                raise ValueError("Missing path after --write")
            write_path = Path(args[index + 1])
            index += 2
            continue
        positional.append(current)
        index += 1

    search_provider = positional[0] if positional else os.getenv("SECTORBREAKER_TEMPLATE_SEARCH_PROVIDER", "tavily")
    extraction_provider = (
        positional[1] if len(positional) > 1 else os.getenv("SECTORBREAKER_TEMPLATE_EXTRACTION_PROVIDER", "http")
    )
    return search_provider, extraction_provider, write_path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    try:
        search_provider, extraction_provider, write_path = _parse_args(args)
        rendered = build_template(search_provider, extraction_provider)
        if write_path is not None:
            write_path.write_text(rendered, encoding="utf-8")
            print(f"Wrote template to {write_path}")
            return 0
        print(rendered, end="")
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
