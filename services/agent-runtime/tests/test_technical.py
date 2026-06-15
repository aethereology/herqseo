from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    Finding,
    Page,
    SiteResources,
    SiteSnapshot,
    audit_site_resources,
    audit_snapshot,
)


def _page(
    url="https://x.com/",
    title="A Clear Descriptive Page Title",
    headings=("Main heading",),
    text="word " * 100,
    meta_description="A clear summary of the page for snippets.",
    has_structured_data=True,
):
    return Page(
        url=url, title=title, headings=headings, text=text,
        meta_description=meta_description, has_structured_data=has_structured_data,
    )


def _codes(findings):
    return {f.code for f in findings}


class TechnicalAuditTest(unittest.TestCase):
    def test_clean_page_has_no_high_severity_findings(self) -> None:
        findings = audit_snapshot(SiteSnapshot("https://x.com", (_page(),)))
        self.assertFalse([f for f in findings if f.severity == "high"])

    def test_missing_title(self) -> None:
        findings = audit_snapshot(SiteSnapshot("https://x.com", (_page(title=""),)))
        self.assertIn("missing_title", _codes(findings))

    def test_detects_duplicated_title(self) -> None:
        # the real mortgagebyhumans.wordpress.com case
        page = _page(title="mortgagebyhumansmortgagebyhumansWordPress.com")
        findings = audit_snapshot(SiteSnapshot("https://x.com", (page,)))
        dup = [f for f in findings if f.code == "duplicated_title"]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0].severity, "high")
        self.assertIsInstance(dup[0], Finding)

    def test_missing_h1(self) -> None:
        findings = audit_snapshot(SiteSnapshot("https://x.com", (_page(headings=()),)))
        self.assertIn("missing_h1", _codes(findings))

    def test_thin_content(self) -> None:
        findings = audit_snapshot(SiteSnapshot("https://x.com", (_page(text="short"),)))
        self.assertIn("thin_content", _codes(findings))

    def test_missing_meta_description(self) -> None:
        findings = audit_snapshot(SiteSnapshot("https://x.com", (_page(meta_description=""),)))
        self.assertIn("missing_meta_description", _codes(findings))

    def test_missing_structured_data(self) -> None:
        findings = audit_snapshot(
            SiteSnapshot("https://x.com", (_page(has_structured_data=False),))
        )
        self.assertIn("missing_structured_data", _codes(findings))

    def test_clean_page_has_no_meta_or_schema_finding(self) -> None:
        codes = _codes(audit_snapshot(SiteSnapshot("https://x.com", (_page(),))))
        self.assertNotIn("missing_meta_description", codes)
        self.assertNotIn("missing_structured_data", codes)

    def test_aggregates_across_pages_and_carries_url(self) -> None:
        snapshot = SiteSnapshot(
            "https://x.com",
            (_page(url="https://x.com/a", title=""), _page(url="https://x.com/b")),
        )
        findings = audit_snapshot(snapshot)
        missing = [f for f in findings if f.code == "missing_title"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0].url, "https://x.com/a")


class SiteResourceFindingsTest(unittest.TestCase):
    def test_flags_missing_robots_and_llms(self) -> None:
        findings = audit_site_resources(
            SiteResources(has_robots_txt=False, has_llms_txt=False), "https://x.com"
        )
        codes = _codes(findings)
        self.assertIn("missing_robots_txt", codes)
        self.assertIn("missing_llms_txt", codes)
        self.assertTrue(all(f.severity == "low" for f in findings))

    def test_no_findings_when_both_present(self) -> None:
        findings = audit_site_resources(
            SiteResources(has_robots_txt=True, has_llms_txt=True), "https://x.com"
        )
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
