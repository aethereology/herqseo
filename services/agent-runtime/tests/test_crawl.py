from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    CrawlBudgetExceeded,
    CrawlFetchError,
    HttpPageFetcher,
    Page,
    SiteResources,
    SiteSnapshot,
    UnsafeUrlError,
    check_site_resources,
    crawl_site,
    normalize_public_site_url,
    parse_page,
)
from queryclear_agent_runtime import crawl as crawl_module  # noqa: E402


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

    def test_returns_partial_snapshot_when_budget_expires_after_first_page(self) -> None:
        class _BudgetFetcher:
            def __init__(self) -> None:
                self.fetched: list[str] = []

            def fetch(self, url: str) -> str:
                raise AssertionError("deadline-aware path was not used")

            def fetch_until(self, url: str, deadline: float | None) -> str:
                self.fetched.append(url)
                if len(self.fetched) == 1:
                    return '<title>Home</title><a href="/slow">Slow</a><a href="/later">Later</a>'
                raise CrawlBudgetExceeded("budget exhausted")

        fetcher = _BudgetFetcher()
        snapshot = crawl_site(fetcher, "https://example.com", deadline=10_000_000.0)

        self.assertEqual([page.title for page in snapshot.pages], ["Home"])
        self.assertEqual(
            fetcher.fetched,
            ["https://example.com/", "https://example.com/slow"],
        )

    def test_budget_expiry_before_first_page_remains_an_explicit_error(self) -> None:
        with self.assertRaises(CrawlBudgetExceeded):
            crawl_site(_FakeFetcher({}), "https://example.com", deadline=-1.0)


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

    def test_resource_checks_use_the_site_origin_not_a_submitted_path(self) -> None:
        fetcher = _FakeFetcher(
            {
                "https://example.com/robots.txt": "User-agent: *",
                "https://example.com/llms.txt": "# Guide",
            }
        )
        check_site_resources(fetcher, "https://example.com/some/page?utm_source=test")
        self.assertEqual(
            fetcher.fetched,
            ["https://example.com/robots.txt", "https://example.com/llms.txt"],
        )

    def test_expired_resource_budget_is_unknown_not_a_false_missing_signal(self) -> None:
        resources = check_site_resources(
            _FakeFetcher({}), "https://example.com", deadline=-1.0
        )
        self.assertIsNone(resources.has_robots_txt)
        self.assertIsNone(resources.has_llms_txt)


class PublicFetchSecurityTest(unittest.TestCase):
    def test_site_url_normalization_keeps_only_the_public_origin(self) -> None:
        self.assertEqual(
            normalize_public_site_url("https://Example.COM/path?q=1#fragment"),
            "https://example.com/",
        )

    def test_site_url_normalization_rejects_unsafe_targets(self) -> None:
        for url in (
            "file:///etc/passwd",
            "http://localhost:3000/",
            "http://127.0.0.1/",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.2.3.4/",
            "http://[::1]/",
            "https://user:password@example.com/",
            "https://example.com:8443/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(UnsafeUrlError):
                    normalize_public_site_url(url)

    @patch.object(crawl_module.socket, "getaddrinfo")
    def test_dns_resolution_rejects_a_mixed_public_private_answer(self, resolve) -> None:
        resolve.return_value = [
            (crawl_module.socket.AF_INET, crawl_module.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (crawl_module.socket.AF_INET, crawl_module.socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443)),
        ]
        with self.assertRaises(UnsafeUrlError):
            crawl_module._public_addresses("example.com", 443)

    @patch.object(crawl_module.time, "monotonic", return_value=100.0)
    @patch.object(crawl_module.http.client, "HTTPConnection")
    @patch.object(crawl_module.socket, "getaddrinfo")
    def test_http_connection_is_pinned_to_the_validated_address(self, resolve, connection_cls, _clock) -> None:
        resolve.return_value = [
            (crawl_module.socket.AF_INET, crawl_module.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
        ]
        response = connection_cls.return_value.getresponse.return_value
        response.status = 200
        response.getheaders.return_value = [("content-type", "text/html")]
        response.read.return_value = b"<title>Safe</title>"

        status, _, body = crawl_module._fetch_public_url("http://example.com/", 5.0)

        self.assertEqual(status, 200)
        self.assertEqual(body, b"<title>Safe</title>")
        connection_cls.assert_called_once_with("93.184.216.34", port=80, timeout=5.0)

    @patch.object(
        crawl_module.time,
        "monotonic",
        side_effect=[100.0, 100.0, 100.0, 101.0, 101.0, 101.0],
    )
    @patch.object(crawl_module.http.client, "HTTPConnection")
    @patch.object(crawl_module.socket, "getaddrinfo")
    def test_resolved_addresses_share_one_per_hop_timeout(
        self, resolve, connection_cls, _clock
    ) -> None:
        resolve.return_value = [
            (crawl_module.socket.AF_INET, crawl_module.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
            (crawl_module.socket.AF_INET, crawl_module.socket.SOCK_STREAM, 6, "", ("93.184.216.35", 80)),
        ]
        first = unittest.mock.MagicMock()
        first.request.side_effect = OSError("first address unavailable")
        second = unittest.mock.MagicMock()
        response = second.getresponse.return_value
        response.status = 200
        response.getheaders.return_value = [("content-type", "text/html")]
        response.read.return_value = b"<title>Safe</title>"
        connection_cls.side_effect = [first, second]

        status, _, _ = crawl_module._fetch_public_url("http://example.com/", 4.0)

        self.assertEqual(status, 200)
        self.assertEqual(connection_cls.call_args_list[0].kwargs["timeout"], 4.0)
        self.assertEqual(connection_cls.call_args_list[1].kwargs["timeout"], 3.0)

    @patch.object(crawl_module, "_fetch_public_url")
    def test_http_fetcher_passes_four_second_cap_and_shared_deadline(self, fetch) -> None:
        fetch.return_value = (200, {"content-type": "text/html"}, b"<title>Safe</title>")

        deadline = 1_000_000_000_000.0
        HttpPageFetcher().fetch_until("https://example.com/", deadline)

        fetch.assert_called_once_with(
            "https://example.com/", 4.0, deadline=deadline
        )

    @patch.object(crawl_module, "_fetch_public_url")
    def test_redirect_to_private_network_is_rejected_before_second_fetch(self, fetch) -> None:
        fetch.return_value = (302, {"location": "http://169.254.169.254/latest/meta-data/"}, b"")
        with self.assertRaises(UnsafeUrlError):
            HttpPageFetcher().fetch("https://example.com/")
        self.assertEqual(fetch.call_count, 1)

    @patch.object(crawl_module, "_fetch_public_url")
    def test_non_text_and_encoded_responses_are_rejected(self, fetch) -> None:
        fetch.return_value = (200, {"content-type": "image/png"}, b"png")
        with self.assertRaises(CrawlFetchError):
            HttpPageFetcher().fetch("https://example.com/")

        fetch.return_value = (
            200,
            {"content-type": "text/html", "content-encoding": "gzip"},
            b"compressed",
        )
        with self.assertRaises(CrawlFetchError):
            HttpPageFetcher().fetch("https://example.com/")


if __name__ == "__main__":
    unittest.main()
