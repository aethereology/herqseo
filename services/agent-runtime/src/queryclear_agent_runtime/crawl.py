from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Protocol


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    headings: tuple[str, ...]
    text: str
    meta_description: str = ""
    has_structured_data: bool = False


@dataclass(frozen=True)
class SiteSnapshot:
    domain: str
    pages: tuple[Page, ...]


class PageFetcher(Protocol):
    def fetch(self, url: str) -> str:
        ...


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

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name.lower(): (value or "") for name, value in attrs}
        if "itemscope" in attr:
            self.has_structured_data = True
        if tag in ("script", "style"):
            if tag == "script" and "ld+json" in attr.get("type", "").lower():
                self.has_structured_data = True
            self._skip += 1
        elif tag == "meta":
            if attr.get("name", "").lower() == "description" and not self.meta_description:
                self.meta_description = " ".join(attr.get("content", "").split())
        elif tag == "title":
            self._in_title = True
        elif tag in ("h1", "h2", "h3"):
            self._heading_tag = tag
            self._heading_buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
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
    )


def crawl_site(
    fetcher: PageFetcher,
    domain: str,
    seed_paths: tuple[str, ...] = ("/",),
    *,
    max_pages: int = 5,
) -> SiteSnapshot:
    """Fetch a bounded set of seed paths for one domain.

    M0 deliberately fetches an explicit seed-path list rather than following
    links; link-discovery crawling is P1-3 (domain ingestion).
    """
    base = domain.rstrip("/")
    pages: list[Page] = []
    for path in seed_paths[:max_pages]:
        url = path if path.startswith("http") else base + path
        pages.append(parse_page(url, fetcher.fetch(url)))
    return SiteSnapshot(domain=domain, pages=tuple(pages))


@dataclass(frozen=True)
class SiteResources:
    has_robots_txt: bool
    has_llms_txt: bool


def check_site_resources(fetcher: PageFetcher, domain: str) -> SiteResources:
    """Probe a domain for /robots.txt and /llms.txt presence.

    A failed fetch (404, network error) counts as absent — we only assert
    presence when the file is reachable and non-empty.
    """
    base = domain.rstrip("/")

    def _present(path: str) -> bool:
        try:
            return bool(fetcher.fetch(base + path).strip())
        except Exception:  # any fetch failure -> treat as absent
            return False

    return SiteResources(
        has_robots_txt=_present("/robots.txt"),
        has_llms_txt=_present("/llms.txt"),
    )


class HttpPageFetcher:
    """HTTP fetcher backed by ``httpx``, imported lazily so the package stays
    importable without the dependency (e.g. in CI; tests inject a fake)."""

    def __init__(self, *, timeout: float = 10.0, client: object | None = None) -> None:
        self._timeout = timeout
        self._client = client

    def fetch(self, url: str) -> str:
        client = self._get_client()
        response = client.get(url)
        response.raise_for_status()
        return response.text

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            import httpx  # lazy: optional dependency

            self._client = httpx.Client(timeout=self._timeout, follow_redirects=True)
        return self._client
