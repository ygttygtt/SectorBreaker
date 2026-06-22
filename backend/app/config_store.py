"""Local persistence for runtime search/LLM configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def get_runtime_config_path(database_path: Path) -> Path:
    return database_path.with_name(f"{database_path.stem}.runtime-config.json")


def load_runtime_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text(encoding="utf-8"))


def save_runtime_config(config_path: Path, payload: dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
