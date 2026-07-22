"""Local persistence for runtime search/LLM configuration."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


def get_runtime_config_path(database_path: Path) -> Path:
    return database_path.with_name(f"{database_path.stem}.runtime-config.json")


def load_runtime_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    try:
        return _read_config(config_path)
    except (json.JSONDecodeError, OSError) as primary_error:
        backup_path = _backup_path(config_path)
        if backup_path.exists():
            try:
                return _read_config(backup_path)
            except (json.JSONDecodeError, OSError):
                pass
        raise RuntimeError(f"runtime config is unreadable: {config_path.name}") from primary_error


def save_runtime_config(config_path: Path, payload: dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    json.loads(rendered)

    if config_path.exists():
        try:
            _read_config(config_path)
        except (json.JSONDecodeError, OSError):
            pass
        else:
            _atomic_copy(config_path, _backup_path(config_path))

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path.parent,
            prefix=f".{config_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        _restrict_permissions(temp_path)
        os.replace(temp_path, config_path)
        temp_path = None
        _restrict_permissions(config_path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _read_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("runtime config root must be an object", str(payload), 0)
    return payload


def _backup_path(config_path: Path) -> Path:
    return config_path.with_name(f"{config_path.name}.bak")


def _atomic_copy(source: Path, target: Path) -> None:
    temp_target = target.with_name(f".{target.name}.tmp")
    try:
        shutil.copyfile(source, temp_target)
        _restrict_permissions(temp_target)
        os.replace(temp_target, target)
        _restrict_permissions(target)
    finally:
        temp_target.unlink(missing_ok=True)


def _restrict_permissions(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        # Windows ACLs may require administrator policy. Never make a valid
        # atomic write fail merely because chmod semantics are unavailable.
        pass
