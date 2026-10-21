"""Bounded HTTPS access to explicitly approved public source hosts."""

from __future__ import annotations

import hashlib
import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ALLOWED_HOSTS = frozenset(
    {
        "sdmx.oecd.org",
        "www.oecd.org",
        "oecd.org",
        "stats.bis.org",
        "data.bis.org",
        "www.bis.org",
        "bis.org",
        "api.imf.org",
        "data.imf.org",
        "www.imf.org",
        "imf.org",
        "data-api.ecb.europa.eu",
        "www.ecb.europa.eu",
        "ecb.europa.eu",
        "ec.europa.eu",
        "commission.europa.eu",
        "api.worldbank.org",
        "thedocs.worldbank.org",
        "www.worldbank.org",
        "worldbank.org",
        "databank.worldbank.org",
        "datahelpdesk.worldbank.org",
        "fred.stlouisfed.org",
        "www.stlouisfed.org",
        "stlouisfed.org",
        "www.eia.gov",
    }
)
USER_AGENT = "MacroLab/0.1 (local academic source feasibility probe; keyless public data)"


class NetworkBoundaryError(ValueError):
    """The requested URL falls outside the authorised source boundary."""


def validate_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        raise NetworkBoundaryError(f"URL outside the approved HTTPS source boundary: {url}")


class CheckedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> urllib.request.Request | None:
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True)
class FetchRecord:
    source: str
    probe_id: str
    snapshot_id: str
    attempt: int
    url: str
    final_url: str | None
    retrieved_utc: str
    status: int | None
    mime_type: str | None
    sha256: str | None
    size_bytes: int | None
    raw_path: str | None
    body_complete: bool
    elapsed_seconds: float
    error: str | None


@dataclass(frozen=True)
class FetchResult:
    body: bytes | None
    record: FetchRecord


class SourceClient:
    """No environment proxies, authentication handlers, cookies or key discovery."""

    def __init__(
        self,
        root: Path,
        snapshot_id: str,
        *,
        timeout: float = 25,
        retries: int = 1,
        max_bytes: int = 16_000_000,
        pause: float = 1.0,
    ) -> None:
        self.root = root
        self.snapshot_id = snapshot_id
        self.timeout = timeout
        self.retries = retries
        self.max_bytes = max_bytes
        self.pause = pause
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), CheckedRedirectHandler()
        )

    def fetch(self, source: str, probe_id: str, url: str, accept: str) -> FetchResult:
        validate_url(url)
        for attempt in range(1, self.retries + 2):
            result = self._attempt(source, probe_id, url, accept, attempt)
            if result.record.status not in (None, 429, 500, 502, 503, 504):
                return result
            if (
                isinstance(result.record.error, str)
                and "NetworkBoundaryError" in result.record.error
            ):
                return result
            if attempt <= self.retries:
                time.sleep(self.pause * attempt)
        return result

    def _attempt(
        self, source: str, probe_id: str, url: str, accept: str, attempt: int
    ) -> FetchResult:
        start = time.monotonic()
        timestamp = datetime.now(UTC).isoformat()
        status: int | None = None
        mime: str | None = None
        final_url: str | None = None
        body: bytes | None = None
        error: str | None = None
        response: Any = None
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": accept}
            )
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                status = response.status
                final_url = response.geturl()
                validate_url(final_url)
                mime = response.headers.get("Content-Type")
                received = response.read(self.max_bytes + 1)
                if len(received) > self.max_bytes:
                    raise ValueError(
                        f"Response exceeds {self.max_bytes} bytes; not retained truncated"
                    )
                body = received
                if status >= 400:
                    error = f"HTTP {status}"
        except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException) as exc:
            error = f"{type(exc).__name__}: {exc}"
        raw_path: str | None = None
        digest: str | None = None
        if body is not None:
            digest = hashlib.sha256(body).hexdigest()
            target = self.root / "data" / "raw" / source / self.snapshot_id
            target.mkdir(parents=True, exist_ok=True)
            file = target / f"{probe_id}-attempt-{attempt}.bin"
            with file.open("xb") as stream:
                stream.write(body)
            raw_path = str(file.relative_to(self.root))
        record = FetchRecord(
            source,
            probe_id,
            self.snapshot_id,
            attempt,
            url,
            final_url,
            timestamp,
            status,
            mime,
            digest,
            len(body) if body is not None else None,
            raw_path,
            body is not None,
            round(time.monotonic() - start, 6),
            error,
        )
        manifest = self.root / "data" / "manifests" / "raw_manifest.jsonl"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with manifest.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(record), sort_keys=True) + "\n")
        return FetchResult(body, record)
