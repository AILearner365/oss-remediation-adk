from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


class EvidenceHttpClient:
    """Small bounded HTTP cache that records source-level measurements."""

    def __init__(self, cache_dir: Path, timeout: int = 30, retries: int = 2):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.retries = retries
        self.metrics = {"network_requests": 0, "cache_hits": 0,
                        "network_failures": 0, "retries": 0,
                        "response_bytes": 0, "elapsed_seconds": 0.0}

    def request(self, url: str, payload: dict | None = None) -> tuple[bytes, dict]:
        body = None if payload is None else json.dumps(payload, sort_keys=True).encode()
        key = hashlib.sha256(url.encode() + b"\0" + (body or b"")).hexdigest()
        cached = self.cache_dir / key
        provenance = {"url": url, "method": "POST" if body else "GET",
                      "request_sha256": key, "cache": False}
        if cached.exists():
            data = cached.read_bytes()
            self.metrics["cache_hits"] += 1
            provenance.update({"cache": True, "bytes": len(data)})
            return data, provenance
        headers = {"User-Agent": "spring-boot-release-intelligence-feasibility/1"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        started = time.monotonic()
        last_error = None
        for attempt in range(self.retries + 1):
            if attempt:
                self.metrics["retries"] += 1
                time.sleep(0.25 * attempt)
            try:
                req = urllib.request.Request(url, data=body, headers=headers)
                self.metrics["network_requests"] += 1
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    data = response.read(5_000_001)
                    if len(data) > 5_000_000:
                        raise ValueError("response exceeded 5 MB evidence bound")
                    cached.write_bytes(data)
                    self.metrics["response_bytes"] += len(data)
                    self.metrics["elapsed_seconds"] += time.monotonic() - started
                    provenance.update({"bytes": len(data), "status": response.status})
                    return data, provenance
            except (urllib.error.URLError, TimeoutError) as exc:
                self.metrics["network_failures"] += 1
                last_error = exc
        self.metrics["elapsed_seconds"] += time.monotonic() - started
        raise RuntimeError(f"HTTP request failed after retries: {url}: {last_error}")

    def json(self, url: str, payload: dict | None = None) -> tuple[dict, dict]:
        data, provenance = self.request(url, payload)
        return json.loads(data), provenance
