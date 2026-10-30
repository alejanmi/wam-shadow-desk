"""Snapshot store: layer L0 (provenance).

Every response the loop uses is written to disk once, with a SHA-256 of the
exact bytes, the redacted URL that produced it and when it was fetched.
Downstream code never calls the network directly; it asks the store, which
in `live` mode fetches-and-records and in `replay` mode reads the recorded
bytes. That makes every number reproducible and every claim traceable to the
query that produced it.

Layout:  <root>/<as_of>/<source>/<key>.body  +  <key>.meta.json
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from shadowdesk.core.http import HttpResponse, redact_url


class SnapshotMissing(KeyError):
    pass


@dataclass(frozen=True)
class Provenance:
    source: str
    key: str
    url: str          # redacted
    fetched_at: str   # ISO-8601 UTC
    sha256: str
    bytes: int
    as_of: str

    def ref(self) -> str:
        """Short reference for reports and inquiry records."""
        return f"{self.source}:{self.key}@{self.as_of}#sha256={self.sha256[:12]}"


def _safe(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9._=-]+", "_", key)[:150] or "item"


class SnapshotStore:
    def __init__(self, root: str | Path, as_of: str, mode: str = "replay",
                 fetcher: Callable[[str, dict[str, str] | None], HttpResponse] | None = None):
        if mode not in {"live", "replay"}:
            raise ValueError("mode must be 'live' or 'replay'")
        if mode == "live" and fetcher is None:
            raise ValueError("live mode needs a fetcher")
        self.root = Path(root)
        self.as_of = as_of
        self.mode = mode
        self._fetcher = fetcher

    def _paths(self, source: str, key: str) -> tuple[Path, Path]:
        d = self.root / self.as_of / _safe(source)
        k = _safe(key)
        return d / f"{k}.body", d / f"{k}.meta.json"

    def get(self, source: str, key: str, url: str, headers: dict[str, str] | None = None) -> tuple[bytes, Provenance]:
        body_p, meta_p = self._paths(source, key)
        if body_p.exists() and meta_p.exists():
            return body_p.read_bytes(), Provenance(**json.loads(meta_p.read_text(encoding="utf-8")))
        if self.mode == "replay":
            raise SnapshotMissing(f"no snapshot for {source}:{key} on {self.as_of} under {self.root}")
        resp = self._fetcher(url, headers)  # type: ignore[misc]
        prov = Provenance(
            source=source, key=key, url=redact_url(url),
            fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            sha256=hashlib.sha256(resp.body).hexdigest(), bytes=len(resp.body), as_of=self.as_of,
        )
        body_p.parent.mkdir(parents=True, exist_ok=True)
        body_p.write_bytes(resp.body)
        meta_p.write_text(json.dumps(asdict(prov), indent=2), encoding="utf-8")
        return resp.body, prov

    def get_json(self, source: str, key: str, url: str, headers: dict[str, str] | None = None) -> tuple[Any, Provenance]:
        body, prov = self.get(source, key, url, headers)
        return json.loads(body.decode("utf-8")), prov

    def verify(self) -> list[str]:
        """Re-hash every stored body; return keys whose bytes no longer match."""
        bad = []
        for meta_p in (self.root / self.as_of).rglob("*.meta.json"):
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            body_p = meta_p.with_name(meta_p.name.replace(".meta.json", ".body"))
            if not body_p.exists() or hashlib.sha256(body_p.read_bytes()).hexdigest() != meta["sha256"]:
                bad.append(f"{meta['source']}:{meta['key']}")
        return bad
