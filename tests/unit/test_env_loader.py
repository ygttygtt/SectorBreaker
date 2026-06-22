import os
from pathlib import Path

from backend.app.env import load_local_env


def test_load_local_env_sets_missing_environment_values(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TAVILY_API_KEY=test-tavily-key\nCONTENT_EXTRACTION_PROVIDER=jina\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("CONTENT_EXTRACTION_PROVIDER", raising=False)

    load_local_env(env_file)

    assert os.getenv("TAVILY_API_KEY") == "test-tavily-key"
    assert os.getenv("CONTENT_EXTRACTION_PROVIDER") == "jina"


def test_load_local_env_does_not_override_existing_values(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TAVILY_API_KEY=file-value\n", encoding="utf-8")

    monkeypatch.setenv("TAVILY_API_KEY", "existing-value")

    load_local_env(env_file)

    assert os.getenv("TAVILY_API_KEY") == "existing-value"
