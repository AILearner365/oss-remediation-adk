from __future__ import annotations

import base64
import ipaddress
import socket
from dataclasses import asdict, dataclass, replace
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
    SOURCE_TRUNCATED = "source_truncated"


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
    failure_code: str | None = None
    recovery: str | None = None
    http_status: int | None = None
    acquired_bytes: int = 0
    byte_limit: int = 0
    acquisition_succeeded: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        value["results"] = list(self.results)
        return value


class ResearchProvider(Protocol):
    def search(self, query: str) -> ResearchResult: ...

    def fetch(self, url: str) -> ResearchResult: ...


class HttpResearchProvider:
    def __init__(self, *, enabled: bool, timeout_seconds: int = 15, max_response_bytes: int = 2_000_000):
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
            return fetched
        parser = _SearchParser()
        try:
            parser.feed(fetched.content)
        except Exception as exc:
            return _extraction_failure(fetched, str(exc))
        if not parser.results:
            return _extraction_failure(fetched, "Search response contained no extractable results")
        return replace(fetched, content="", results=tuple(parser.results))

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
                return _extraction_failure(fetched, str(exc))
        else:
            content = fetched.content
        if not content:
            return _extraction_failure(fetched, "Response contained no extractable text")
        return replace(fetched, content=content)

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
                return self._read_response(response, getattr(response, "status", 200))
        except _BlockedResearchError as exc:
            return ResearchResult(ResearchStatus.BLOCKED, url, error=str(exc))
        except HTTPError as exc:
            with exc:
                return self._read_response(exc, exc.code)
        except (URLError, TimeoutError, OSError) as exc:
            return ResearchResult(ResearchStatus.HTTP_NETWORK_FAILURE, url, error=str(exc))

    def _read_response(self, response, status: int) -> ResearchResult:
        # Bound the whole source, not just visible text: large CSS/script prefixes
        # need room, but neither extraction nor retention can grow without limit.
        body = response.read(self.max_response_bytes + 1)
        truncated = len(body) > self.max_response_bytes
        body = body[:self.max_response_bytes]
        charset = response.headers.get_content_charset() or "utf-8"
        try:
            raw = body.decode(charset, errors="replace")
        except LookupError:
            raw = body.decode("utf-8", errors="replace")
        media = response.headers.get_content_type()
        result = ResearchResult(
            ResearchStatus.SUCCESS, response.geturl(), content=raw, raw_content=raw,
            raw_bytes_b64=base64.b64encode(body).decode("ascii"), media_type=media,
            truncated=truncated, acquired_bytes=len(body), byte_limit=self.max_response_bytes,
            http_status=status, acquisition_succeeded=200 <= status < 300,
            recovery=("Only a source prefix was acquired; retained artifacts cannot supply the missing tail. "
                      "Use a smaller supported public source if the needed evidence is absent.") if truncated else None,
        )
        lowered = raw.lower()
        challenge = media in {"text/html", "application/xhtml+xml"} and (
            ('id="challenge-form"' in lowered and 'anomaly.js' in lowered)
            or ('captcha' in lowered and ('verify you are human' in lowered or 'confirm you are human' in lowered))
            or ('cf-chl-' in lowered and 'just a moment' in lowered)
        )
        if challenge or status in {403, 429}:
            return replace(result, status=ResearchStatus.BLOCKED, content="",
                           failure_code="BOT_CHALLENGE" if challenge else "HTTP_ACCESS_BLOCKED",
                           error="Source returned a bot challenge" if challenge else f"HTTP access blocked ({status})",
                           recovery="Do not retry or solve the challenge automatically. Use an accessible official source with research_fetch, or other available evidence; preserve uncertainty. Search provider replacement requires explicit configuration and approval.")
        if not 200 <= status < 300:
            return replace(result, status=ResearchStatus.HTTP_NETWORK_FAILURE, content="",
                           failure_code="HTTP_ERROR", error=f"HTTP {status}",
                           recovery="Use another accessible source or report the evidence as unavailable.")
        supported = (media.startswith("text/") or media in {"application/xhtml+xml", "application/xml", "application/json"}
                     or media.endswith("+xml") or media.endswith("+json"))
        if not supported:
            return _extraction_failure(result, f"Unsupported public content type: {media}")
        return result


def _extraction_failure(result: ResearchResult, error: str) -> ResearchResult:
    return replace(result, content="",
                   status=ResearchStatus.SOURCE_TRUNCATED if result.truncated else ResearchStatus.EXTRACTION_FAILURE,
                   failure_code="SOURCE_LIMIT_BEFORE_USABLE_CONTENT" if result.truncated else "EXTRACTION_FAILED",
                   error=error,
                   recovery=result.recovery if result.truncated else
                   "The retained response did not yield usable evidence. Inspect its raw reference or use another supported public source; this is not evidence of absence.")


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
