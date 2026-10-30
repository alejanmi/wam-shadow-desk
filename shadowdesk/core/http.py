"""Standard-library HTTP with timeouts, bounded retries and key redaction.

`redact_url` is applied to every URL that is logged or written to a snapshot,
so an API key can never end up in a snapshot, report or ledger row.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

_SECRET_PARAMS = re.compile(r"(?i)([?&](?:apikey|api_key|key|token|access_token)=)[^&#]*")


def redact_url(url: str) -> str:
    return _SECRET_PARAMS.sub(r"\1REDACTED", url)


@dataclass
class HttpResponse:
    status: int
    body: bytes
    url: str  # redacted


class HttpError(RuntimeError):
    pass


def fetch(url: str, *, headers: dict[str, str] | None = None, timeout: float = 20.0,
          retries: int = 2, backoff: float = 1.5) -> HttpResponse:
    """GET `url`. Retries on 429/5xx and network errors, never on 4xx."""
    hdrs = {"User-Agent": "wam-shadow-desk/0.1", "Accept": "*/*"}
    hdrs.update(headers or {})
    last: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=hdrs, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return HttpResponse(status=resp.status, body=resp.read(), url=redact_url(url))
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                last = e
            else:
                raise HttpError(f"HTTP {e.code} for {redact_url(url)}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        if attempt < retries:
            time.sleep(backoff * (attempt + 1))
    raise HttpError(f"giving up on {redact_url(url)}: {last}")
