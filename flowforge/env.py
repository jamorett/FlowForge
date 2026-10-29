"""Minimal .env loader (no third-party dependency).

Reads KEY=VALUE lines from a `.env` file into ``os.environ``. Real
environment variables always win. Supports blank lines, `#` comments,
`export ` prefixes, and single/double-quoted values. Anything fancier
belongs in a real config file, not a secret file.
"""

from __future__ import annotations

import os
from pathlib import Path


def _parse_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.lower().startswith("export "):
        line = line[7:].lstrip()
    key, sep, value = line.partition("=")
    if not sep:
        return None
    key = key.strip()
    if not key or not key.replace("_", "").isalnum():
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return key, value


def load_dotenv(dotenv_path: str | Path | None = None, override: bool = False) -> bool:
    """Load `.env` into the environment. Return True if the file was read."""
    path = Path(dotenv_path) if dotenv_path is not None else Path(".env")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        parsed = _parse_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if override or key not in os.environ:
            os.environ[key] = value
    return True
