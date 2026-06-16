from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    Page,
    SiteResources,
    SiteSnapshot,
    check_site_resources,
    crawl_site,
    parse_page,
)


class _FakeFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages
        self.fetched: list[str] = []

    def fetch(self, url: str) -> str:
        self.fetched.append(url)
        return self._pages[url]


_HTML = """
<html>
  <head><title>  Invoice Automation for SaaS </title>
    <meta name="description" content="  Automate AP invoices for finance teams. ">
    <script type="application/ld+json">{"@type":"Organization"}</script>
    <style>.x{color:red}</style>
  </head>
  <body>
    <h1>Automate your invoices</h1>
    <script>var a = 1;</script>
    <h2>Built for finance teams</h2>
    <p>QueryClear helps    finance teams move faster.</p>
  </body>
</html>
"""


class ParsePageTest(unittest.TestCase):
    def test_extracts_title_headings_and_text(self) -> None:
        page = parse_page("https://example.com/", _HTML)

        self.assertEqual(page.title, "Invoice Automation for SaaS")
        self.assertEqual(page.headings, ("Automate your invoices", "Built for finance teams"))
        self.assertIn("QueryClear helps finance teams move faster.", page.text)
        # script/style content is excluded
        self.assertNotIn("var a", page.text)
        self.assertNotIn("color:red", page.text)

    def test_extracts_meta_description_and_structured_data(self) -> None:
        page = parse_page("https://example.com/", _HTML)
        self.assertEqual(page.meta_description, "Automate AP invoices for finance teams.")
        self.assertTrue(page.has_structured_data)

    def test_extracts_links(self) -> None:
        page = parse_page(
            "https://example.com/",
            '<a href="/pricing">Pricing</a><a href="https://other.test/">Offsite</a>',
        )
        self.assertEqual(page.links, ("/pricing", "https://other.test/"))

    def test_missing_meta_and_schema_default_empty(self) -> None:
        page = parse_page("https://example.com/", "<title>Bare</title><h1>Hi</h1>")
        self.assertEqual(page.meta_description, "")
        self.assertFalse(page.has_structured_data)

    def test_detects_microdata_as_structured_data(self) -> None:
        page = parse_page("https://example.com/", '<div itemscope itemtype="x">a</div>')
        self.assertTrue(page.has_structured_data)

    def test_truncates_text(self) -> None:
        html = "<html><body><p>" + ("word " * 1000) + "</p></body></html>"
        page = parse_page("https://example.com/", html, max_text_chars=50)
        self.assertEqual(len(page.text), 50)


class CrawlSiteTest(unittest.TestCase):
    def test_fetches_seed_paths_and_builds_snapshot(self) -> None:
        fetcher = _FakeFetcher(
            {
                "https://example.com/": _HTML,
                "https://example.com/pricing": "<title>Pricing</title>",
            }
        )

        snapshot = crawl_site(fetcher, "https://example.com", ("/", "/pricing"))

        self.assertIsInstance(snapshot, SiteSnapshot)
        self.assertEqual(snapshot.domain, "https://example.com")
        self.assertEqual(len(snapshot.pages), 2)
        self.assertEqual(fetcher.fetched, ["https://example.com/", "https://example.com/pricing"])
        self.assertIsInstance(snapshot.pages[0], Page)
        self.assertEqual(snapshot.pages[1].title, "Pricing")

    def test_respects_max_pages(self) -> None:
        fetcher = _FakeFetcher({"https://example.com/": _HTML})
        snapshot = crawl_site(fetcher, "https://example.com/", ("/", "/a", "/b"), max_pages=1)
        self.assertEqual(len(snapshot.pages), 1)
        self.assertEqual(fetcher.fetched, ["https://example.com/"])

    def test_discovers_same_domain_links(self) -> None:
        fetcher = _FakeFetcher(
            {
                "https://example.com/": (
                    '<title>Home</title><a href="/pricing">Pricing</a>'
                    '<a href="https://other.test/">Other</a>'
                ),
                "https://example.com/pricing": '<title>Pricing</title><a href="/contact">Contact</a>',
                "https://example.com/contact": "<title>Contact</title>",
            }
        )

        snapshot = crawl_site(fetcher, "https://example.com", ("/",), max_pages=3)

        self.assertEqual(
            [page.url for page in snapshot.pages],
            ["https://example.com/", "https://example.com/pricing", "https://example.com/contact"],
        )

    def test_skips_broken_discovered_links(self) -> None:
        fetcher = _FakeFetcher(
            {
                "https://example.com/": '<title>Home</title><a href="/missing">Missing</a>',
            }
        )

        snapshot = crawl_site(fetcher, "https://example.com", ("/",), max_pages=2)

        self.assertEqual(len(snapshot.pages), 1)
        self.assertEqual(fetcher.fetched, ["https://example.com/", "https://example.com/missing"])

    def test_can_disable_link_discovery(self) -> None:
        fetcher = _FakeFetcher(
            {
                "https://example.com/": '<title>Home</title><a href="/pricing">Pricing</a>',
                "https://example.com/pricing": "<title>Pricing</title>",
            }
        )

        snapshot = crawl_site(fetcher, "https://example.com", ("/",), follow_links=False)

        self.assertEqual(len(snapshot.pages), 1)
        self.assertEqual(fetcher.fetched, ["https://example.com/"])


class SiteResourcesTest(unittest.TestCase):
    def test_detects_present_and_absent_resources(self) -> None:
        # robots.txt present (non-empty); llms.txt missing -> fetch raises KeyError
        fetcher = _FakeFetcher({"https://example.com/robots.txt": "Sitemap: /sitemap.xml"})
        resources = check_site_resources(fetcher, "https://example.com/")
        self.assertIsInstance(resources, SiteResources)
        self.assertTrue(resources.has_robots_txt)
        self.assertFalse(resources.has_llms_txt)

    def test_empty_file_counts_as_absent(self) -> None:
        fetcher = _FakeFetcher(
            {"https://example.com/robots.txt": "   ", "https://example.com/llms.txt": "# Guide"}
        )
        resources = check_site_resources(fetcher, "https://example.com")
        self.assertFalse(resources.has_robots_txt)
        self.assertTrue(resources.has_llms_txt)


if __name__ == "__main__":
    unittest.main()
