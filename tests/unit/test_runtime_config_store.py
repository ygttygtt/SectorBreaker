from pathlib import Path

from backend.app.config_store import get_runtime_config_path, load_runtime_config, save_runtime_config


def test_runtime_config_store_round_trip(tmp_path: Path) -> None:
    config_path = get_runtime_config_path(tmp_path / "sectorbreaker.sqlite3")
    payload = {
        "search_provider_mode": "multi",
        "tavily_api_key": "tvly-test-key",
        "serper_api_key": "serper-test-key",
    }

    save_runtime_config(config_path, payload)

    assert load_runtime_config(config_path) == payload


def test_runtime_config_store_returns_empty_dict_when_missing(tmp_path: Path) -> None:
    config_path = get_runtime_config_path(tmp_path / "sectorbreaker.sqlite3")

    assert load_runtime_config(config_path) == {}
