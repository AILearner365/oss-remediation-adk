from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import quote_plus, urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup
from google.adk.tools import FunctionTool


DEFAULT_TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 2_000_000
MAX_CONTENT_CHARS = 40_000


def _error(status: str, message: str, **details: Any) -> dict[str, Any]:
    return {"status": status, "error": message, **details}


def _validate_public_https_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        return "Only HTTPS URLs are supported."
    if not parsed.hostname:
        return "URL must include a hostname."
    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".local"):
        return "Local destinations are not supported."
    try:
        addresses = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return "Hostname could not be resolved."
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            return "Private, loopback, link-local, or otherwise non-public destinations are not supported."
    return None


def search_web(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search the public web through Google using the host's normal network/proxy settings.

    This is a lightweight POC for environments where managed Google Search grounding is
    unavailable. It respects the same corporate network controls as other local HTTP calls.
    """
    if not query.strip():
        return _error("invalid_query", "Search query must not be empty.")

    limit = max(1, min(max_results, 10))
    search_url = f"https://www.google.com/search?q={quote_plus(query)}&num={limit}"

    try:
        with requests.get(
            search_url,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            allow_redirects=False,
        ) as response:
            if response.status_code in (401, 403):
                return _error(
                    "access_blocked",
                    "Google Search was denied or blocked by the current network policy.",
                    url=response.url,
                    http_status=response.status_code,
                    server=response.headers.get("Server"),
                )
            if not response.ok:
                return _error(
                    "http_error",
                    f"Search request failed with status {response.status_code}.",
                    url=response.url,
                    http_status=response.status_code,
                )

            soup = BeautifulSoup(response.text, "lxml")
            results: list[dict[str, str]] = []
            seen: set[str] = set()

            for anchor in soup.select("a"):
                href = anchor.get("href", "")
                heading = anchor.find("h3")
                if not heading or not href:
                    continue

                if href.startswith("/url?q="):
                    href = href.split("/url?q=", 1)[1].split("&", 1)[0]
                elif not href.startswith("https://"):
                    continue

                parsed = urlparse(href)
                if parsed.scheme != "https" or not parsed.hostname:
                    continue
                if parsed.hostname.endswith("google.com"):
                    continue
                if href in seen:
                    continue

                seen.add(href)
                results.append({
                    "title": heading.get_text(" ", strip=True),
                    "url": href,
                })
                if len(results) >= limit:
                    break

            if not results:
                return _error(
                    "no_results",
                    "No structured search results could be extracted. Google may have returned a challenge or changed its HTML.",
                    url=response.url,
                )

            return {
                "status": "ok",
                "query": query,
                "results": results,
            }
    except requests.RequestException as exc:
        return _error("network_error", str(exc), url=search_url)


def fetch_web_page(url: str) -> dict[str, Any]:
    """Fetch text from a public HTTPS page using the host's normal network/proxy settings.

    Corporate proxy, TLS, authentication, and filtering policies are intentionally inherited
    from the Python process environment. This tool does not bypass blocked destinations.
    """
    validation_error = _validate_public_https_url(url)
    if validation_error:
        return _error("invalid_url", validation_error, url=url)

    try:
        with requests.get(
            url,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                if not location:
                    return _error("http_error", "Redirect response did not include a Location header.", url=url)
                return _error(
                    "redirect_not_followed",
                    "Redirects are not followed automatically. Fetch the returned public HTTPS URL explicitly if appropriate.",
                    url=url,
                    location=location,
                    http_status=response.status_code,
                )

            server = response.headers.get("Server")
            if response.status_code in (401, 403):
                return _error(
                    "access_blocked",
                    "The destination denied access or was blocked by the current network policy.",
                    url=response.url,
                    http_status=response.status_code,
                    server=server,
                )
            if not response.ok:
                return _error(
                    "http_error",
                    f"HTTP request failed with status {response.status_code}.",
                    url=response.url,
                    http_status=response.status_code,
                    server=server,
                )

            content_type = response.headers.get("Content-Type", "")
            media_type = content_type.split(";", 1)[0].strip().lower()
            if media_type not in {"text/html", "text/plain", "application/json", "application/xml", "text/xml"}:
                return _error(
                    "unsupported_content",
                    f"Unsupported content type: {content_type or 'unknown'}",
                    url=response.url,
                    content_type=content_type,
                )

            body = bytearray()
            for chunk in response.iter_content(chunk_size=16_384):
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    return _error(
                        "response_too_large",
                        f"Response exceeds the {MAX_RESPONSE_BYTES}-byte limit.",
                        url=response.url,
                    )

            response.encoding = response.encoding or "utf-8"
            text = body.decode(response.encoding, errors="replace")
            if media_type == "text/html":
                try:
                    from bs4 import BeautifulSoup
                except ImportError:
                    return _error(
                        "missing_dependency",
                        "HTML extraction requires beautifulsoup4. Install the project dependency before using this tool.",
                        url=response.url,
                    )
                soup = BeautifulSoup(text, "html.parser")
                for element in soup(["script", "style", "noscript", "svg"]):
                    element.decompose()
                title = soup.title.get_text(" ", strip=True) if soup.title else None
                text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
            else:
                title = None
                extraction_method = "direct"

            return {
                "status": "ok",
                "url": response.url,
                "title": title,
                "content_type": content_type,
                "extraction_method": extraction_method,
                "content": text[:MAX_CONTENT_CHARS],
                "truncated": len(text) > MAX_CONTENT_CHARS,
            }
    except requests.RequestException as exc:
        return _error("network_error", str(exc), url=url)


WEB_TOOLS = [FunctionTool(search_web), FunctionTool(fetch_web_page)]
