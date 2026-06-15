"""Deterministic on-page technical-SEO/AEO findings from crawled pages.

Read-only, credential-free, works on any site — the substance of a sellable
audit and the seed of the technical-SEO engine (specs/technical-seo-engine.md).
Operates only on the data the crawler already captures (title, headings, text);
meta-description / llms.txt / robots checks are a follow-up that needs the
crawler to capture head tags and extra fetches.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .crawl import Page, SiteSnapshot

_TITLE_MAX = 60
_TITLE_MIN = 15
_THIN_CONTENT_CHARS = 200


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # high | medium | low
    title: str
    detail: str
    recommendation: str
    url: str | None = None


def _looks_duplicated(title: str) -> bool:
    """True if the title repeats a meaningful block back-to-back (e.g. a site
    name doubled by a broken title template)."""
    normalized = re.sub(r"[^a-z0-9]+", "", title.lower())
    if len(normalized) < 8:
        return False
    half = len(normalized) // 2
    for size in range(6, half + 1):
        segment = normalized[:size]
        if normalized.startswith(segment * 2):
            return True
    return False


def audit_page(page: Page) -> list[Finding]:
    findings: list[Finding] = []
    title = page.title.strip()

    if not title:
        findings.append(
            Finding(
                "missing_title", "high", "Missing page title",
                f"{page.url} has no <title> tag.",
                "Add a unique, descriptive <title> (~50–60 chars).", page.url,
            )
        )
    else:
        if _looks_duplicated(title):
            findings.append(
                Finding(
                    "duplicated_title", "high", "Duplicated text in title",
                    f"The title looks duplicated: {title!r}.",
                    "Fix the title template so the site/page name isn't repeated.",
                    page.url,
                )
            )
        if len(title) > _TITLE_MAX:
            findings.append(
                Finding(
                    "title_too_long", "low", "Title may be truncated",
                    f"Title is {len(title)} characters.",
                    f"Keep titles ~{_TITLE_MIN}–{_TITLE_MAX} chars so they aren't cut off.",
                    page.url,
                )
            )
        elif len(title) < _TITLE_MIN:
            findings.append(
                Finding(
                    "title_too_short", "low", "Title is very short",
                    f"Title is only {len(title)} characters.",
                    "Expand the title with the page's primary topic.", page.url,
                )
            )

    if not page.headings:
        findings.append(
            Finding(
                "missing_h1", "medium", "No heading found",
                f"{page.url} has no H1–H3 headings.",
                "Add a clear H1 stating the page's main topic.", page.url,
            )
        )

    if len(page.text) < _THIN_CONTENT_CHARS:
        findings.append(
            Finding(
                "thin_content", "medium", "Thin content",
                f"{page.url} has ~{len(page.text)} characters of text.",
                "Add substantive, answer-first content AI engines can extract.",
                page.url,
            )
        )

    return findings


def audit_snapshot(snapshot: SiteSnapshot) -> list[Finding]:
    findings: list[Finding] = []
    for page in snapshot.pages:
        findings.extend(audit_page(page))
    return findings
