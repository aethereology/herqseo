"""Offline regression corpus: markup facts must not be inferred from unrelated signals."""
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from queryclear_agent_runtime.crawl import parse_page, check_site_resources, CrawlHttpError
from queryclear_agent_runtime.technical import audit_page, audit_site_resources

class EvidenceAccuracyTest(unittest.TestCase):
    def codes(self, html):
        return {f.code for f in audit_page(parse_page("https://example.com/", html))}

    def test_h2_does_not_mask_missing_h1(self):
        self.assertIn("missing_h1", self.codes("<h2>Services</h2>"))
        self.assertNotIn("missing_h1", self.codes("<h1>Services</h1><h2>Details</h2>"))

    def test_json_ld_syntax_is_checked_without_inventing_schema_validity(self):
        for content in ['{"@type":', '', 'null', '[]']:
            with self.subTest(content=content):
                self.assertIn("invalid_json_ld", self.codes(f'<script type="application/ld+json">{content}</script>'))
        self.assertNotIn("invalid_json_ld", self.codes('<script type="application/ld+json">{"@type":"WebPage"}</script>'))

    def test_parser_depth_limit_does_not_crash_the_audit(self):
        with patch("queryclear_agent_runtime.crawl.json.loads", side_effect=RecursionError):
            self.assertIn("invalid_json_ld", self.codes('<script type="application/ld+json">[]</script>'))

    def test_script_text_does_not_become_page_evidence(self):
        page = parse_page("https://example.com", '<script type="application/ld+json">{"name":"Fake headline"}</script><h1>Real headline</h1>')
        self.assertEqual(page.text, "Real headline")

    def test_resource_absence_requires_observed_not_found(self):
        for status, expected in [(404, False), (410, False), (403, None), (429, None), (500, None)]:
            with self.subTest(status=status):
                class Fetcher:
                    def fetch(self, url): raise CrawlHttpError(status)
                resources = check_site_resources(Fetcher(), "https://example.com")
                self.assertIs(resources.has_robots_txt, expected)
                self.assertEqual(bool(audit_site_resources(resources, "https://example.com")), expected is False)

    def test_timeout_is_unknown_and_empty_resource_is_present(self):
        class Failed:
            def fetch(self, url): raise TimeoutError()
        class Empty:
            def fetch(self, url): return ""
        self.assertIsNone(check_site_resources(Failed(), "https://example.com").has_robots_txt)
        self.assertTrue(check_site_resources(Empty(), "https://example.com").has_robots_txt)
