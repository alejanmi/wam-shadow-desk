"""Settings and secrets.

Secrets come only from the process environment or a local `.env` file.
Nothing in this repository may contain a key. `require()` fails loudly with
the name of the missing variable instead of silently running without data.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class MissingSecret(RuntimeError):
    pass


def load_dotenv(path: str | Path = ".env") -> dict[str, str]:
    """Minimal .env reader (KEY=VALUE lines). Existing env vars win."""
    p = Path(path)
    loaded: dict[str, str] = {}
    if not p.exists():
        return loaded
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingSecret(f"{name} is not set. Add it to .env (see .env.example).")
    return value


@dataclass(frozen=True)
class Settings:
    data_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(data_dir=Path(os.environ.get("SHADOWDESK_DATA", "./data")))
