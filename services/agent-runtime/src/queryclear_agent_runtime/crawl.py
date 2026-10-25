from __future__ import annotations

import http.client
import json
import ipaddress
import re
import socket
import ssl
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import quote, urldefrag, urljoin, urlparse


_MAX_RESPONSE_BYTES = 2_000_000
_MAX_REDIRECTS = 3
_DEFAULT_REQUEST_TIMEOUT_SECONDS = 4.0
_ALLOWED_PORTS = {"http": 80, "https": 443}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_USER_AGENT = "QueryClearReadinessPreview/1.0 (+https://www.queryclear.com/privacy)"
_DNS_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="queryclear-dns")


class UnsafeUrlError(ValueError):
    """The requested crawl target is not a public web address."""


class CrawlFetchError(RuntimeError):
    """A public web target could not be fetched within the crawler limits."""


class CrawlHttpError(CrawlFetchError):
    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(f"The website returned HTTP {status}.")


class CrawlBudgetExceeded(CrawlFetchError):
    """The shared crawl deadline expired before another page could be fetched."""


def _remaining_seconds(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    return deadline - time.monotonic()


def _require_budget(deadline: float | None) -> float | None:
    remaining = _remaining_seconds(deadline)
    if remaining is not None and remaining <= 0:
        raise CrawlBudgetExceeded("The website crawl exceeded its time limit.")
    return remaining


def _parsed_public_url(url: str):  # type: ignore[no-untyped-def]
    if not url or len(url) > 2048:
        raise UnsafeUrlError("Enter a valid public website URL.")
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_PORTS or not parsed.hostname:
        raise UnsafeUrlError("Only public http and https websites can be checked.")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("Website URLs cannot include credentials.")
    try:
        port = parsed.port or _ALLOWED_PORTS[scheme]
    except ValueError as exc:
        raise UnsafeUrlError("The website URL has an invalid port.") from exc
    if port != _ALLOWED_PORTS[scheme]:
        raise UnsafeUrlError("Only standard website ports can be checked.")

    hostname = parsed.hostname.rstrip(".").lower()
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or hostname.endswith(".internal")
        or hostname.endswith(".home.arpa")
    ):
        raise UnsafeUrlError("Local and private addresses cannot be checked.")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise UnsafeUrlError("Local and private addresses cannot be checked.")
    return parsed, hostname.encode("idna").decode("ascii"), port


def normalize_public_site_url(url: str) -> str:
    """Return a canonical public website origin for a site-level audit."""
    parsed, hostname, port = _parsed_public_url(url.strip())
    default_port = _ALLOWED_PORTS[parsed.scheme.lower()]
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port != default_port:
        host = f"{host}:{port}"
    return f"{parsed.scheme.lower()}://{host}/"


def _public_addresses(
    hostname: str, port: int, *, timeout: float | None = None
) -> tuple[str, ...]:
    try:
        if timeout is None:
            records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        else:
            if timeout <= 0:
                raise CrawlFetchError("The website hostname resolution timed out.")
            future = _DNS_EXECUTOR.submit(
                socket.getaddrinfo, hostname, port, 0, socket.SOCK_STREAM
            )
            try:
                records = future.result(timeout=timeout)
            except FutureTimeoutError as exc:
                future.cancel()
                raise CrawlFetchError(
                    "The website hostname resolution timed out."
                ) from exc
    except socket.gaierror as exc:
        raise CrawlFetchError("The website hostname could not be resolved.") from exc
    addresses = tuple(dict.fromkeys(record[4][0].split("%", 1)[0] for record in records))
    if not addresses:
        raise CrawlFetchError("The website hostname could not be resolved.")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise UnsafeUrlError("The website resolved to an invalid address.") from exc
        if not ip.is_global:
            raise UnsafeUrlError("The website resolved to a local or private address.")
    return addresses


class _PinnedHttpsConnection(http.client.HTTPSConnection):
    """TLS connects to a validated IP while certificates/SNI use the hostname."""

    def __init__(self, hostname: str, address: str, port: int, timeout: float) -> None:
        super().__init__(hostname, port=port, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def _request_target(parsed) -> str:  # type: ignore[no-untyped-def]
    path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
    query = quote(parsed.query, safe="=&?/:;+,%@-._~")
    return f"{path}?{query}" if query else path


def _decode_body(body: bytes, content_type: str) -> str:
    charset_match = re.search(r"charset\s*=\s*[\"']?([^;\s\"']+)", content_type, re.I)
    charset = charset_match.group(1) if charset_match else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _fetch_public_url(
    url: str, timeout: float, *, deadline: float | None = None
) -> tuple[int, dict[str, str], bytes]:
    """Fetch one URL hop within one timeout shared by all resolved addresses.

    ``timeout`` is a per-hop ceiling, not a per-IP retry allowance. ``deadline``
    is the optional crawl-wide monotonic deadline. DNS and every socket stage
    are checked against the same clocks before work continues.
    """
    _require_budget(deadline)
    hop_deadline = time.monotonic() + timeout
    if deadline is not None:
        hop_deadline = min(hop_deadline, deadline)
    parsed, hostname, port = _parsed_public_url(url)
    dns_timeout = hop_deadline - time.monotonic()
    try:
        addresses = _public_addresses(hostname, port, timeout=dns_timeout)
    except CrawlFetchError as exc:
        if deadline is not None and time.monotonic() >= deadline:
            raise CrawlBudgetExceeded(
                "The website crawl exceeded its time limit."
            ) from exc
        raise
    target = _request_target(parsed)
    host_header = f"[{hostname}]" if ":" in hostname else hostname
    last_error: Exception | None = None

    for address in addresses:
        remaining = hop_deadline - time.monotonic()
        if remaining <= 0:
            break
        connection: http.client.HTTPConnection
        if parsed.scheme.lower() == "https":
            connection = _PinnedHttpsConnection(hostname, address, port, remaining)
        else:
            connection = http.client.HTTPConnection(address, port=port, timeout=remaining)
        try:
            connection.request(
                "GET",
                target,
                headers={
                    "Host": host_header,
                    "User-Agent": _USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            remaining = hop_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("request deadline expired")
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            response = connection.getresponse()
            remaining = hop_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("response deadline expired")
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            headers = {name.lower(): value for name, value in response.getheaders()}
            declared = headers.get("content-length")
            if declared:
                try:
                    declared_bytes = int(declared)
                    if declared_bytes < 0 or declared_bytes > _MAX_RESPONSE_BYTES:
                        raise CrawlFetchError("The website response is too large to audit.")
                except ValueError as exc:
                    raise CrawlFetchError("The website returned an invalid response length.") from exc
            body = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(body) > _MAX_RESPONSE_BYTES:
                raise CrawlFetchError("The website response is too large to audit.")
            return response.status, headers, body
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            last_error = exc
        finally:
            connection.close()
    if deadline is not None and time.monotonic() >= deadline:
        raise CrawlBudgetExceeded("The website crawl exceeded its time limit.") from last_error
    if time.monotonic() >= hop_deadline:
        raise CrawlFetchError("The website request timed out.") from last_error
    raise CrawlFetchError("The public website could not be reached.") from last_error


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    headings: tuple[str, ...]
    text: str
    meta_description: str = ""
    has_structured_data: bool = False
    links: tuple[str, ...] = ()
    h1_count: int | None = None
    invalid_json_ld: int = 0


@dataclass(frozen=True)
class SiteSnapshot:
    domain: str
    pages: tuple[Page, ...]


class PageFetcher(Protocol):
    def fetch(self, url: str) -> str:
        ...


def _fetch_before_deadline(
    fetcher: PageFetcher, url: str, deadline: float | None
) -> str:
    _require_budget(deadline)
    fetch_until = getattr(fetcher, "fetch_until", None)
    if callable(fetch_until):
        return fetch_until(url, deadline)
    return fetcher.fetch(url)


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._in_title = False
        self._heading_tag: str | None = None
        self._heading_buf: list[str] = []
        self.title_parts: list[str] = []
        self.headings: list[str] = []
        self.text_parts: list[str] = []
        self.meta_description: str = ""
        self.has_structured_data: bool = False
        self.links: list[str] = []
        self.h1_count = 0
        self.invalid_json_ld = 0
        self._json_ld_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name.lower(): (value or "") for name, value in attrs}
        if "itemscope" in attr:
            self.has_structured_data = True
        if tag == "a":
            href = attr.get("href", "").strip()
            if href:
                self.links.append(href)
        if tag in ("script", "style"):
            if tag == "script" and attr.get("type", "").lower().strip() == "application/ld+json":
                self.has_structured_data = True
                self._json_ld_parts = []
            self._skip += 1
        elif tag == "meta":
            if attr.get("name", "").lower() == "description" and not self.meta_description:
                self.meta_description = " ".join(attr.get("content", "").split())
        elif tag == "title":
            self._in_title = True
        elif tag in ("h1", "h2", "h3"):
            if tag == "h1":
                self.h1_count += 1
            self._heading_tag = tag
            self._heading_buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            if tag == "script" and self._json_ld_parts is not None:
                try:
                    value = json.loads("".join(self._json_ld_parts))
                    if not isinstance(value, (dict, list)) or not value:
                        self.invalid_json_ld += 1
                except (ValueError, TypeError, RecursionError):
                    self.invalid_json_ld += 1
                self._json_ld_parts = None
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag == self._heading_tag:
            heading = " ".join("".join(self._heading_buf).split())
            if heading:
                self.headings.append(heading)
            self._heading_tag = None
            self._heading_buf = []

    def handle_data(self, data: str) -> None:
        if self._skip:
            if self._json_ld_parts is not None:
                self._json_ld_parts.append(data)
            return
        if self._in_title:
            self.title_parts.append(data)
            return
        if self._heading_tag is not None:
            self._heading_buf.append(data)
        stripped = data.strip()
        if stripped:
            self.text_parts.append(stripped)


def parse_page(url: str, html: str, *, max_text_chars: int = 2000) -> Page:
    extractor = _Extractor()
    extractor.feed(html)
    title = " ".join("".join(extractor.title_parts).split())
    text = " ".join(" ".join(extractor.text_parts).split())[:max_text_chars]
    return Page(
        url=url,
        title=title,
        headings=tuple(extractor.headings),
        text=text,
        meta_description=extractor.meta_description,
        has_structured_data=extractor.has_structured_data,
        links=tuple(dict.fromkeys(extractor.links)),
        h1_count=extractor.h1_count,
        invalid_json_ld=extractor.invalid_json_ld,
    )


def _same_domain_url(base_url: str, href: str) -> str | None:
    absolute = urldefrag(urljoin(base_url, href))[0]
    parsed = urlparse(absolute)
    base = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc.lower() != base.netloc.lower():
        return None
    return absolute


def crawl_site(
    fetcher: PageFetcher,
    domain: str,
    seed_paths: tuple[str, ...] = ("/",),
    *,
    max_pages: int = 5,
    follow_links: bool = True,
    deadline: float | None = None,
) -> SiteSnapshot:
    """Fetch bounded pages, returning a partial crawl if its deadline expires.

    A deadline before the first successful page is an explicit error. Once at
    least one page is available, expiry stops link discovery without discarding
    the useful evidence already collected.
    """
    base = domain.rstrip("/")
    queued = deque(path if path.startswith("http") else base + path for path in seed_paths)
    seen: set[str] = set()
    pages: list[Page] = []
    seed_urls = set(queued)
    while queued and len(pages) < max_pages:
        url = queued.popleft()
        if url in seen:
            continue
        seen.add(url)
        try:
            html = _fetch_before_deadline(fetcher, url, deadline)
        except CrawlBudgetExceeded:
            if pages:
                break
            raise
        except Exception:
            if url in seed_urls:
                raise
            continue
        page = parse_page(url, html)
        pages.append(page)
        if not follow_links:
            continue
        for href in page.links:
            linked = _same_domain_url(url, href)
            if linked is not None and linked not in seen:
                queued.append(linked)
    return SiteSnapshot(domain=domain, pages=tuple(pages))


@dataclass(frozen=True)
class SiteResources:
    has_robots_txt: bool | None
    has_llms_txt: bool | None


def check_site_resources(
    fetcher: PageFetcher, domain: str, *, deadline: float | None = None
) -> SiteResources:
    """Probe a domain for /robots.txt and /llms.txt presence.

    Only HTTP 404/410 establish absence. Network/access failures are unknown;
    an empty but reachable resource is still present.
    """
    base = normalize_public_site_url(domain).rstrip("/")

    def _present(path: str) -> bool | None:
        try:
            _fetch_before_deadline(fetcher, base + path, deadline)
            return True
        except CrawlBudgetExceeded:
            # Unknown is not absent. A budget-expired optional probe must not
            # create a false SEO defect in the prospect's report.
            return None
        except CrawlHttpError as exc:
            return False if exc.status in (404, 410) else None
        except Exception:
            # Network failures and access blocks cannot establish absence.
            return None

    return SiteResources(
        has_robots_txt=_present("/robots.txt"),
        has_llms_txt=_present("/llms.txt"),
    )


class HttpPageFetcher:
    """Bounded public-web fetcher with pinned DNS and explicit redirects.

    Every request and redirect resolves first, rejects any non-global address,
    then connects to the validated IP. This prevents the public audit from being
    used to reach private services, cloud metadata, or a DNS-rebinding target.
    """

    def __init__(
        self,
        *,
        timeout: float = _DEFAULT_REQUEST_TIMEOUT_SECONDS,
        client: object | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = timeout
        self._client = client

    def fetch(self, url: str) -> str:
        return self.fetch_until(url, None)

    def fetch_until(self, url: str, deadline: float | None) -> str:
        # A client can be injected by isolated unit tests. Production wiring
        # never injects one and always uses the pinned transport below.
        _require_budget(deadline)
        if self._client is not None:
            response = self._client.get(url)
            response.raise_for_status()
            return response.text

        current = url
        for redirects in range(_MAX_REDIRECTS + 1):
            _require_budget(deadline)
            status, headers, body = _fetch_public_url(
                current, self._timeout, deadline=deadline
            )
            if status in _REDIRECT_STATUSES:
                location = headers.get("location", "").strip()
                if not location or len(location) > 2048 or redirects >= _MAX_REDIRECTS:
                    raise CrawlFetchError("The website returned an invalid redirect chain.")
                current = urljoin(current, location)
                _parsed_public_url(current)
                continue
            if status < 200 or status >= 300:
                raise CrawlHttpError(status)

            encoding = headers.get("content-encoding", "").lower()
            if encoding not in {"", "identity"}:
                raise CrawlFetchError("The website returned an unsupported compressed response.")
            content_type = headers.get("content-type", "").lower()
            media_type = content_type.split(";", 1)[0].strip()
            if media_type and not (
                media_type.startswith("text/") or media_type == "application/xhtml+xml"
            ):
                raise CrawlFetchError("The website did not return a text or HTML page.")
            return _decode_body(body, content_type)
        raise CrawlFetchError("The website returned too many redirects.")
