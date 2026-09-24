"""Regression tests for the AI Hack Watch data pipeline (stdlib only).

Covers the shared parser/validator (scripts/datamd.py), the site
generator (scripts/generate.py), and the prerender step
(scripts/prerender_timeline.py).

Run:
    python3 scripts/test_pipeline.py
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import datamd
import generate
import prerender_timeline as prerender
import story_bot

ROOT = Path(__file__).resolve().parents[1]

FAILURES = []
TESTS = []


def check(label):
    """Collect a test; tests run in main() (no side effects on import)."""
    def decorator(fn):
        TESTS.append((label, fn))
        return fn

    return decorator


def run_tests():
    for label, fn in TESTS:
        try:
            fn()
            print(f"PASS  {label}")
        except AssertionError as error:
            FAILURES.append(label)
            print(f"FAIL  {label}: {error}")
        except Exception as error:
            FAILURES.append(label)
            print(f"ERROR {label}: {type(error).__name__}: {error}")


SAMPLE = """---

## Test incident

**Date:** 2026-01-01
**Source:** Example Research
**URL:** https://example.com/report
**Archive:**
**AI role:** Autonomous
**Category:** Security research

A short factual description of the event's impact.
"""


@check("parse_blocks extracts incident fields")
def parse_fields():
    [entry] = datamd.parse_blocks(SAMPLE)
    assert entry["title"] == "Test incident"
    assert entry["date"] == "2026-01-01"
    assert entry["ai_role"] == "Autonomous"
    assert entry["description"].startswith("A short factual")


@check("parse_blocks ignores non-incident prose")
def parse_prose():
    entries = datamd.parse_blocks("# Title\n\nIntro text.\n\n" + SAMPLE)
    assert len(entries) == 1


@check("current data.md parses and validates cleanly")
def parse_real_data():
    entries = datamd.parse_blocks((ROOT / "data.md").read_text(encoding="utf-8"))
    assert len(entries) >= 13, len(entries)
    errors, warnings = datamd.validate_entries(entries)
    assert not errors, errors
    assert not warnings, warnings


@check("missing required field is an error")
def missing_field():
    broken = SAMPLE.replace("**Source:** Example Research", "**Source:**")
    errors, _ = datamd.validate_entries(datamd.parse_blocks(broken))
    assert any("missing source" in error for error in errors)


@check("malformed date is an error")
def malformed_date():
    broken = SAMPLE.replace("**Date:** 2026-01-01", "**Date:** 2026/01/01")
    errors, _ = datamd.validate_entries(datamd.parse_blocks(broken))
    assert any("date must be YYYY-MM-DD" in error for error in errors)


@check("future date is an error")
def future_date():
    broken = SAMPLE.replace("**Date:** 2026-01-01", "**Date:** 2999-01-01")
    errors, _ = datamd.validate_entries(datamd.parse_blocks(broken))
    assert any("date is in the future" in error for error in errors)


@check("invalid URL is an error")
def invalid_url():
    broken = SAMPLE.replace("https://example.com/report", "ftp://example.com/report")
    errors, _ = datamd.validate_entries(datamd.parse_blocks(broken))
    assert any("invalid URL" in error for error in errors)


@check("unknown AI role is an error")
def role_enum():
    broken = SAMPLE.replace("**AI role:** Autonomous", "**AI role:** Kwyjibo")
    errors, _ = datamd.validate_entries(datamd.parse_blocks(broken))
    assert any("not in the allowed set" in error for error in errors), errors


@check("unknown category is an error")
def category_enum():
    broken = SAMPLE.replace("**Category:** Security research", "**Category:** CyberOps")
    errors, _ = datamd.validate_entries(datamd.parse_blocks(broken))
    assert any("not in the allowed set" in error for error in errors), errors


@check("bogus Archive URL is an error; empty Archive is fine")
def archive_format():
    bad = SAMPLE.replace("**Archive:**", "**Archive:** not-a-url")
    errors, _ = datamd.validate_entries(datamd.parse_blocks(bad))
    assert any("invalid Archive URL" in error for error in errors)
    errors, _ = datamd.validate_entries(datamd.parse_blocks(SAMPLE))
    assert not errors


@check("duplicate URLs produce a warning, not an error")
def duplicate_url():
    duplicate = SAMPLE + (
        "\n---\n\n## Duplicate report\n\n"
        "**Date:** 2026-01-02\n**Source:** Other Research\n"
        "**URL:** https://example.com/report\n**Archive:**\n"
        "**AI role:** AI-assisted\n**Category:** Malware\n\n"
        "Another entry with the same URL.\n"
    )
    errors, warnings = datamd.validate_entries(datamd.parse_blocks(duplicate))
    assert not errors
    assert any("Duplicate URL" in warning for warning in warnings)


@check("parse_blocks supports multiple source URLs")
def multi_url():
    multi = SAMPLE.replace(
        "**URL:** https://example.com/report",
        "**URL:** https://example.com/report\n"
        "**Source 2:** Mirror Research\n**URL 2:** https://example.org/mirror",
    )
    [entry] = datamd.parse_blocks(multi)
    assert entry["url"] == "https://example.com/report"
    assert entry["urls"] == ["https://example.com/report", "https://example.org/mirror"]
    assert entry["source"] == "Example Research"
    assert entry["sources"] == ["Example Research", "Mirror Research"]


@check("invalid extra URL is an error")
def bad_extra_url():
    broken = SAMPLE.replace(
        "**URL:** https://example.com/report",
        "**URL:** https://example.com/report\n**URL 2:** ftp://bad.example",
    )
    errors, _ = datamd.validate_entries(datamd.parse_blocks(broken))
    assert any("invalid URL 2+" in error for error in errors), errors


@check("duplicate URLs across fields are flagged")
def dup_extra_url():
    duplicated = SAMPLE.replace(
        "**URL:** https://example.com/report",
        "**URL:** https://example.com/report\n**URL 2:** https://example.com/report",
    )
    _, warnings = datamd.validate_entries(datamd.parse_blocks(duplicated))
    assert any("Duplicate URL" in warning for warning in warnings), warnings


@check("build_incidents carries the urls array")
def urls_in_json():
    incidents = generate.build_incidents(datamd.parse_blocks(SAMPLE))
    assert incidents["incidents"][0]["url"] == "https://example.com/report"
    assert incidents["incidents"][0]["urls"] == ["https://example.com/report"]


@check("stray markdown markers on values are rejected")
def stray_markers():
    bad = SAMPLE.replace(
        "**Archive:**",
        "**Archive:** https://web.archive.org/web/20260919113042/x**",
    )
    errors, _ = datamd.validate_entries(datamd.parse_blocks(bad))
    assert any('ends with stray "**"' in error for error in errors), errors


@check("story_bot parses and validates a valid issue body")
def bot_valid():
    body = """### Article URL

https://example.com/report

### Publication date

2026-08-01

### Source

Example Research

### AI role

Autonomous

### Category

Malware

### Short factual description

A test description of the incident.

### Checks

- [x] Not already in timeline

### Existing Wayback snapshot (optional)

"""
    fields = story_bot.parse_body(body)
    assert story_bot.validate(fields) == [], story_bot.validate(fields)
    entry = story_bot.draft_entry(fields, "Test incident")
    assert "**Category:** Malware" in entry
    assert "**Archive:**" in entry


@check("story_bot rejects bad dates, roles, and categories")
def bot_invalid():
    body = """### Article URL

https://example.com/report

### Publication date

2026/08/01

### Source

Example Research

### AI role

Kwyjibo

### Category

CyberOps

### Short factual description

A test description.

"""
    fields = story_bot.parse_body(body)
    errors = story_bot.validate(fields)
    assert any("date must be YYYY-MM-DD" in e for e in errors), errors
    assert any("not in the allowed set" in e or "one of" in e for e in errors)


@check("story_bot --write appends a valid entry to data.md")
def bot_write(tmp=None):
    import tempfile
    import subprocess
    with tempfile.TemporaryDirectory() as tmpdir:
        data_path = Path(tmpdir) / "data.md"
        data_path.write_text(
            (ROOT / "data.md").read_text(encoding="utf-8"), encoding="utf-8"
        )
        before = len(datamd.parse_blocks(data_path.read_text(encoding="utf-8")))
        body_path = Path(tmpdir) / "body.md"
        body_path.write_text(
            """### Article URL

https://example.com/report

### Publication date

2026-08-01

### Source

Example Research

### AI role

Autonomous

### Category

Malware

### Short factual description

A test description.

""",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "story_bot.py"),
                "--body",
                str(body_path),
                "--root",
                tmpdir,
                "--number",
                "42",
                "--title",
                "Test incident",
                "--write",
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        entries = datamd.parse_blocks(data_path.read_text(encoding="utf-8"))
        assert len(entries) == before + 1, len(entries)
        assert (Path(tmpdir) / ".story-pr-body.md").is_file()


@check("slugify matches the client-side behaviour (NFKD)")
def slug_parity():
    assert datamd.slugify("Café hack") == "cafe-hack"
    assert datamd.slugify("Ünïcode") == "unicode"
    assert datamd.slugify("  Multiple   spaces  ") == "multiple-spaces"
    assert datamd.slugify("!!!punctuation!!!") == "punctuation"


@check("build_incidents sorts newest first")
def sorting():
    entries = datamd.parse_blocks(SAMPLE + """
---

## Older incident

**Date:** 2025-01-01
**Source:** Example Research
**URL:** https://example.com/old
**Archive:**
**AI role:** Unclear
**Category:** Other

Earlier story.
""")
    incidents = generate.build_incidents(entries)
    assert incidents["incidents"][0]["title"] == "Test incident"
    assert incidents["incidents"][1]["title"] == "Older incident"


@check("render_feed escapes and wraps incidents well-formed")
def feed():
    incidents = generate.build_incidents(datamd.parse_blocks(SAMPLE))
    feed = generate.render_feed(incidents["incidents"])
    assert feed.startswith('<?xml version="1.0"')
    assert '<rss version="2.0">' in feed
    assert "&#x27;" in feed  # apostrophe escaped
    assert feed.endswith("</rss>\n")
    ET.fromstring(feed)  # well-formed


@check("render_badge is well-formed XML with data-latest")
def badge():
    svg = generate.render_badge(0, "2026-09-19")
    assert 'data-latest="2026-09-19"' in svg
    assert "<script><![CDATA[" in svg
    ET.fromstring(svg)


@check("inject_site_urls fills canonical/og tags idempotently")
def inject():
    template = (
        '<link rel="canonical" href="">\n'
        '<meta property="og:url" content="">\n'
        '<meta property="og:image" content="days-since-badge.svg">\n'
    )
    updated, applied = prerender.inject_site_urls(template, "https://example.org/site")
    assert applied == 3, applied
    assert 'href="https://example.org/site"' in updated
    assert 'content="https://example.org/site"' in updated
    assert "example.org/site/days-since-badge.svg" in updated
    again, _ = prerender.inject_site_urls(updated, "https://example.org/site")
    assert again == updated  # idempotent


@check("inject_site_urls replaces a previously injected domain")
def inject_domain_change():
    template = (
        '<link rel="canonical" href="https://old.example/site">\n'
        '<meta property="og:url" content="https://old.example/site">\n'
        '<meta property="og:image" content="https://old.example/site/days-since-badge.svg">\n'
    )
    updated, applied = prerender.inject_site_urls(template, "https://new.example/site")
    assert applied == 3, applied
    assert "old.example" not in updated
    assert 'href="https://new.example/site"' in updated
    assert "new.example/site/days-since-badge.svg" in updated


@check("site URL is configured in config.js")
def site_url_configured():
    config = (ROOT / "config.js").read_text(encoding="utf-8")
    assert "siteUrl" in config
    assert "https://" in config


@check("feed dates are RFC-822 and guids are stable slugs")
def feed_rfc822_guid():
    import email.utils
    incidents = generate.build_incidents(datamd.parse_blocks(SAMPLE))
    feed = generate.render_feed(incidents["incidents"])
    assert 'isPermaLink="false"' in feed, feed[:500]
    assert "ai-hack-watch:test-incident" in feed
    assert "T00:00:00Z</pubDate>" not in feed
    # Thu 01 Jan 2026 00:00:00 GMT
    assert "Jan 2026" in feed and "GMT" in feed
    root = ET.fromstring(feed)
    pub_dates = [el.text for el in root.iter("pubDate")]
    assert pub_dates, "no pubDates"
    for value in pub_dates:
        assert email.utils.parsedate_to_datetime(value) is not None, value
    guids = [el.text for el in root.iter("guid")]
    assert guids == ["ai-hack-watch:test-incident"], guids


@check("format_rfc822_date matches known weekday")
def rfc822_weekday():
    # 2026-09-22 is a Tuesday
    assert generate.format_rfc822_date("2026-09-22") == "Tue, 22 Sep 2026 00:00:00 GMT"


@check("duplicate titles get unique slugs")
def unique_slugs():
    dup = SAMPLE + """
---

## Test incident

**Date:** 2025-01-01
**Source:** Example Research
**URL:** https://example.com/old
**Archive:**
**AI role:** Unclear
**Category:** Other

Earlier story with the same headline.
"""
    incidents = generate.build_incidents(datamd.parse_blocks(dup))
    slugs = [i["slug"] for i in incidents["incidents"]]
    assert slugs[0] == "test-incident", slugs
    assert slugs[1] == "test-incident-2", slugs
    assert len(set(slugs)) == 2


@check("duplicate slugs warn")
def duplicate_slug_warning():
    dup = SAMPLE + """
---

## Test incident

**Date:** 2025-01-01
**Source:** Example Research
**URL:** https://example.com/old
**Archive:**
**AI role:** Unclear
**Category:** Other

Earlier story.
"""
    _, warnings = datamd.validate_entries(datamd.parse_blocks(dup))
    assert any("Duplicate slug" in w for w in warnings), warnings


@check("build_incidents emits taxonomy matching datamd")
def taxonomy_emitted():
    incidents = generate.build_incidents(datamd.parse_blocks(SAMPLE))
    assert incidents["taxonomy"]["roles"] == list(datamd.ALLOWED_ROLES)
    assert incidents["taxonomy"]["categories"] == list(datamd.ALLOWED_CATEGORIES)


@check("issue template options match datamd taxonomy")
def issue_template_parity():
    text = (ROOT / ".github" / "ISSUE_TEMPLATE" / "story-submission.yml").read_text(encoding="utf-8")
    for role in datamd.ALLOWED_ROLES:
        assert role in text, f"role missing from issue template: {role}"
    for cat in datamd.ALLOWED_CATEGORIES:
        assert cat in text, f"category missing from issue template: {cat}"


@check("script.js uses UTC dates, namespaced filters, full breakdown")
def script_js_conventions():
    js = (ROOT / "script.js").read_text(encoding="utf-8")
    assert 'timeZone:"UTC"' in js or 'timeZone: "UTC"' in js
    assert "T00:00:00Z" in js
    assert "data-filter-type" in js
    assert "slice(0, 3)" not in js and "slice(0,3)" not in js
    assert "slice(0, 8)" not in js and "slice(0,8)" not in js
    assert "siteTaxonomy" in js


@check("prerender includes filter dimensions for progressive enhancement")
def prerender_attrs():
    incidents = generate.build_incidents(datamd.parse_blocks(SAMPLE))
    html_out = prerender.render_article(incidents["incidents"][0])
    assert 'data-role="Autonomous"' in html_out, html_out
    assert 'data-category="Security research"' in html_out
    assert 'data-filter-type="role"' in html_out
    assert 'data-filter-type="category"' in html_out


@check("apply_archives_in_memory skips network when archive present")
def archives_in_memory_noop():
    [entry] = datamd.parse_blocks(SAMPLE.replace("**Archive:**", "**Archive:** https://web.archive.org/web/20260101/https://example.com/report"))
    calls = []
    orig = generate.request_archive_snapshot
    generate.request_archive_snapshot = lambda url: calls.append(url) or "SHOULD-NOT-HAPPEN"
    try:
        out = generate.apply_archives_in_memory([dict(entry)])
        assert out[0]["archive"].startswith("https://web.archive.org")
        assert calls == [], calls
    finally:
        generate.request_archive_snapshot = orig


@check("test collection is deferred (import has no side effects)")
def deferred_collection():
    assert len(TESTS) >= 10, len(TESTS)
    # FAILURES is only populated by run_tests(), not by import.
    assert isinstance(FAILURES, list)


def main():
    print("AI Hack Watch pipeline tests")
    print("-" * 30)
    run_tests()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())