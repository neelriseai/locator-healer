"""Environment helpers with file fallback support."""

from __future__ import annotations

import os
from pathlib import Path


def get_env(name: str, default: str | None = None) -> str | None:
    process_value = os.getenv(name)
    if process_value is not None:
        return process_value
    file_value = _file_env_values().get(name)
    if file_value is None:
        return default
    if _looks_like_placeholder(file_value):
        return default
    return file_value


def load_env_into_process(
    include_env: bool = True,
    include_example: bool = False,
    override: bool = False,
) -> None:
    env_file, env_example_file = _candidate_env_files()
    ordered_sources: list[Path] = []
    if include_example and env_example_file is not None:
        ordered_sources.append(env_example_file)
    if include_env and env_file is not None:
        ordered_sources.append(env_file)

    for source in ordered_sources:
        for key, value in _parse_env_file(source).items():
            if _looks_like_placeholder(value):
                continue
            if not override and os.getenv(key) is not None:
                continue
            os.environ[key] = value


def _file_env_values() -> dict[str, str]:
    merged: dict[str, str] = {}
    env_file, env_example_file = _candidate_env_files()
    if env_example_file is not None:
        merged.update(_parse_env_file(env_example_file))
    if env_file is not None:
        merged.update(_parse_env_file(env_file))
    return merged


def _candidate_env_files() -> tuple[Path | None, Path | None]:
    start = Path.cwd().resolve()
    for base in (start, *start.parents):
        env_file = base / ".env"
        env_example_file = base / ".env.example"
        if env_file.exists() or env_example_file.exists():
            return (env_file if env_file.exists() else None, env_example_file if env_example_file.exists() else None)
    return (None, None)


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return out
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        value = _strip_matching_quotes(value)
        out[key] = value
    return out


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and ((value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'"))):
        return value[1:-1]
    return value


def _looks_like_placeholder(value: str) -> bool:
    normalized = (value or "").strip().casefold()
    if not normalized:
        return True
    placeholder_tokens = (
        "<your-",
        "<user>",
        "<password>",
        "<host>",
        "<db>",
        "placeholder",
    )
    if any(token in normalized for token in placeholder_tokens):
        return True
    if "<" in normalized and ">" in normalized:
        return True
    return False
