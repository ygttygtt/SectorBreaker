import json
from pathlib import Path

import pytest

from backend.app.config_store import load_runtime_config, save_runtime_config


def test_runtime_config_write_is_atomic_and_keeps_valid_backup(tmp_path: Path) -> None:
    path = tmp_path / "sectorbreaker.runtime-config.json"
    save_runtime_config(path, {"api_key": "first", "mode": "tavily"})
    save_runtime_config(path, {"api_key": "second", "mode": "multi"})

    assert load_runtime_config(path) == {"api_key": "second", "mode": "multi"}
    assert load_runtime_config(path.with_name(f"{path.name}.bak")) == {
        "api_key": "first",
        "mode": "tavily",
    }
    assert not list(tmp_path.glob("*.tmp"))


def test_runtime_config_recovers_from_malformed_primary(tmp_path: Path) -> None:
    path = tmp_path / "sectorbreaker.runtime-config.json"
    save_runtime_config(path, {"api_key": "first"})
    save_runtime_config(path, {"api_key": "second"})
    path.write_text("{broken", encoding="utf-8")

    assert load_runtime_config(path) == {"api_key": "first"}


def test_runtime_config_fails_without_valid_primary_or_backup(tmp_path: Path) -> None:
    path = tmp_path / "sectorbreaker.runtime-config.json"
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(RuntimeError, match="runtime config is unreadable"):
        load_runtime_config(path)
