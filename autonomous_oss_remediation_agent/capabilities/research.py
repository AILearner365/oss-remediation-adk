from __future__ import annotations

import base64
import ipaddress
import socket
from dataclasses import asdict, dataclass
from enum import Enum
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ResearchStatus(str, Enum):
    SUCCESS = "success"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    HTTP_NETWORK_FAILURE = "http_network_failure"
    EXTRACTION_FAILURE = "extraction_failure"


@dataclass(frozen=True)
class ResearchResult:
    status: ResearchStatus
    source: str
    content: str = ""
    results: tuple[dict[str, str], ...] = ()
    error: str | None = None
    truncated: bool = False
    media_type: str | None = None
    raw_content: str = ""
    raw_bytes_b64: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        value["results"] = list(self.results)
        return value


class ResearchProvider(Protocol):
    def search(self, query: str) -> ResearchResult: ...

    def fetch(self, url: str) -> ResearchResult: ...


class HttpResearchProvider:
    def __init__(self, *, enabled: bool, timeout_seconds: int = 15, max_response_bytes: int = 100_000):
        self.enabled = enabled
        self.timeout_seconds = max(1, min(timeout_seconds, 60))
        self.max_response_bytes = max(1_000, min(max_response_bytes, 2_000_000))

    def search(self, query: str) -> ResearchResult:
        if not self.enabled:
            return ResearchResult(ResearchStatus.UNAVAILABLE, "research", error="Network disabled by runtime policy")
        normalized = query.strip()
        if not normalized or len(normalized) > 500:
            return ResearchResult(ResearchStatus.BLOCKED, "research", error="Query must contain 1-500 characters")
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(normalized)}"
        fetched = self._retrieve(url)
        if fetched.status != ResearchStatus.SUCCESS:
            return ResearchResult(fetched.status, url, error=fetched.error, truncated=fetched.truncated,
                                  media_type=fetched.media_type, raw_content=fetched.raw_content,
                                  raw_bytes_b64=fetched.raw_bytes_b64)
        parser = _SearchParser()
        try:
            parser.feed(fetched.content)
        except Exception as exc:
            return ResearchResult(ResearchStatus.EXTRACTION_FAILURE, url, error=str(exc), truncated=fetched.truncated,
                                  media_type=fetched.media_type, raw_content=fetched.raw_content,
                                  raw_bytes_b64=fetched.raw_bytes_b64)
        if not parser.results:
            return ResearchResult(
                ResearchStatus.EXTRACTION_FAILURE,
                url,
                error="Search response contained no extractable results",
                truncated=fetched.truncated,
                media_type=fetched.media_type, raw_content=fetched.raw_content,
                raw_bytes_b64=fetched.raw_bytes_b64,
            )
        return ResearchResult(
            ResearchStatus.SUCCESS,
            url,
            results=tuple(parser.results),
            truncated=fetched.truncated,
            media_type=fetched.media_type, raw_content=fetched.raw_content,
            raw_bytes_b64=fetched.raw_bytes_b64,
        )

    def fetch(self, url: str) -> ResearchResult:
        if not self.enabled:
            return ResearchResult(ResearchStatus.UNAVAILABLE, url, error="Network disabled by runtime policy")
        blocked = _public_url_error(url)
        if blocked:
            return ResearchResult(ResearchStatus.BLOCKED, url, error=blocked)
        fetched = self._retrieve(url)
        if fetched.status != ResearchStatus.SUCCESS:
            return fetched
        if fetched.media_type in {"text/html", "application/xhtml+xml"}:
            parser = _TextParser()
            try:
                parser.feed(fetched.content)
                content = parser.text()
            except Exception as exc:
                return ResearchResult(ResearchStatus.EXTRACTION_FAILURE, fetched.source, error=str(exc),
                                      truncated=fetched.truncated, media_type=fetched.media_type,
                                      raw_content=fetched.raw_content, raw_bytes_b64=fetched.raw_bytes_b64)
        else:
            content = fetched.content
        if not content:
            return ResearchResult(
                ResearchStatus.EXTRACTION_FAILURE,
                fetched.source,
                error="Response contained no extractable text",
                truncated=fetched.truncated,
                media_type=fetched.media_type, raw_content=fetched.raw_content,
                raw_bytes_b64=fetched.raw_bytes_b64,
            )
        return ResearchResult(ResearchStatus.SUCCESS, fetched.source, content=content,
                              truncated=fetched.truncated, media_type=fetched.media_type,
                              raw_content=fetched.raw_content, raw_bytes_b64=fetched.raw_bytes_b64)

    def _retrieve(self, url: str) -> ResearchResult:
        blocked = _public_url_error(url)
        if blocked:
            return ResearchResult(ResearchStatus.BLOCKED, url, error=blocked)
        parsed = urlsplit(url)
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
        except OSError as exc:
            return ResearchResult(ResearchStatus.HTTP_NETWORK_FAILURE, url, error=f"Hostname resolution failed: {exc}")
        if any(not ipaddress.ip_address(address).is_global for address in addresses):
            return ResearchResult(
                ResearchStatus.BLOCKED,
                url,
                error="Private, loopback, link-local, and otherwise non-public destinations are blocked",
            )
        request = Request(url, headers={"User-Agent": "oss-remediation-agent/1.0"})
        try:
            with build_opener(_PublicRedirectHandler()).open(request, timeout=self.timeout_seconds) as response:
                content_type = response.headers.get_content_type()
                body = response.read(self.max_response_bytes + 1)
                truncated = len(body) > self.max_response_bytes
                body = body[: self.max_response_bytes]
                charset = response.headers.get_content_charset() or "utf-8"
                raw = body.decode(charset, errors="replace")
                supported = (content_type.startswith("text/") or content_type in {
                    "application/xhtml+xml", "application/xml", "application/json"}
                    or content_type.endswith("+xml") or content_type.endswith("+json"))
                if not supported:
                    return ResearchResult(
                        ResearchStatus.EXTRACTION_FAILURE,
                        response.geturl(),
                        error=f"Unsupported public content type: {content_type}",
                        truncated=truncated, media_type=content_type, raw_content=raw,
                        raw_bytes_b64=base64.b64encode(body).decode("ascii"),
                    )
                return ResearchResult(
                    ResearchStatus.SUCCESS,
                    response.geturl(),
                    content=raw, raw_content=raw, media_type=content_type,
                    raw_bytes_b64=base64.b64encode(body).decode("ascii"),
                    truncated=truncated,
                )
        except _BlockedResearchError as exc:
            return ResearchResult(ResearchStatus.BLOCKED, url, error=str(exc))
        except HTTPError as exc:
            return ResearchResult(ResearchStatus.HTTP_NETWORK_FAILURE, url, error=f"HTTP {exc.code}: {exc.reason}")
        except (URLError, TimeoutError, OSError) as exc:
            return ResearchResult(ResearchStatus.HTTP_NETWORK_FAILURE, url, error=str(exc))


def _public_url_error(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "Only absolute public HTTP(S) URLs are allowed"
    if parsed.username or parsed.password:
        return "Authenticated URLs are not allowed"
    try:
        host_ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        host_ip = None
    if host_ip is not None and not host_ip.is_global:
        return "Private, loopback, link-local, and otherwise non-public destinations are blocked"
    return None


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._ignored = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            value = " ".join(data.split())
            if value:
                self._parts.append(value)

    def text(self) -> str:
        return "\n".join(self._parts)


class _SearchParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._url: str | None = None
        self._title: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and "result__a" in (values.get("class") or ""):
            href = values.get("href") or ""
            query_url = parse_qs(urlsplit(href).query).get("uddg", [href])[0]
            self._url = unquote(query_url)
            self._title = []

    def handle_data(self, data: str) -> None:
        if self._url is not None:
            self._title.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._url is not None:
            title = " ".join("".join(self._title).split())
            if title and not _public_url_error(self._url):
                self.results.append({"title": title, "url": self._url})
            self._url = None
            self._title = []


class _PublicRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        blocked = _public_url_error(newurl)
        if blocked:
            raise _BlockedResearchError(blocked)
        parsed = urlsplit(newurl)
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
        except OSError as exc:
            raise URLError(f"Hostname resolution failed: {exc}") from exc
        if any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise _BlockedResearchError("Redirect to a non-public destination was blocked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _BlockedResearchError(URLError):
    pass
