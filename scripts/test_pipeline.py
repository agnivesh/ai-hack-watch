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
        except Exception as error:  # noqa: BLE001 - report any test crash and keep running
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


def two_source_sample():
    """SAMPLE with a second source and an archive for each."""
    return SAMPLE.replace(
        "**URL:** https://example.com/report",
        "**URL:** https://example.com/report\n"
        "**Source 2:** Mirror Research\n**URL 2:** https://example.org/mirror",
    ).replace(
        "**Archive:**",
        "**Archive:** https://web.archive.org/web/20260101000000/https://example.com/report\n"
        "**Archive 2:** https://web.archive.org/web/20260102000000/https://example.org/mirror",
    )


@check("parse_blocks pairs numbered archives with numbered sources")
def numbered_archives():
    [entry] = datamd.parse_blocks(two_source_sample())
    assert entry["archive"] == "https://web.archive.org/web/20260101000000/https://example.com/report"
    assert entry["archives"] == [
        "https://web.archive.org/web/20260101000000/https://example.com/report",
        "https://web.archive.org/web/20260102000000/https://example.org/mirror",
    ]


@check("invalid extra archive URL is an error")
def bad_extra_archive():
    broken = two_source_sample().replace(
        "**Archive 2:** https://web.archive.org/web/20260102000000/https://example.org/mirror",
        "**Archive 2:** ftp://bad.example",
    )
    errors, _ = datamd.validate_entries(datamd.parse_blocks(broken))
    assert any("invalid Archive 2" in error for error in errors), errors


@check("archive without a matching source URL is an error")
def orphan_archive():
    broken = SAMPLE.replace(
        "**Archive:**",
        "**Archive 2:** https://web.archive.org/web/20260102000000/https://example.org/mirror",
    )
    errors, _ = datamd.validate_entries(datamd.parse_blocks(broken))
    assert any("no matching URL 2" in error for error in errors), errors


@check("build_incidents carries index-aligned archives")
def archives_in_json():
    record = generate.build_incidents(datamd.parse_blocks(two_source_sample()))["incidents"][0]
    assert record["archive"].endswith("/https://example.com/report")
    assert record["archives"] == [
        "https://web.archive.org/web/20260101000000/https://example.com/report",
        "https://web.archive.org/web/20260102000000/https://example.org/mirror",
    ]


@check("archive_missing_links fills every source archive")
def archive_backfill_per_source():
    text = SAMPLE.replace(
        "**URL:** https://example.com/report",
        "**URL:** https://example.com/report\n"
        "**Source 2:** Mirror Research\n**URL 2:** https://example.org/mirror",
    )
    calls = []
    original = generate.request_archive_snapshot
    generate.request_archive_snapshot = (
        lambda url: calls.append(url) or f"https://web.archive.org/web/1/{url}"
    )
    try:
        updated, changed = generate.archive_missing_links(text)
    finally:
        generate.request_archive_snapshot = original
    assert changed == 2, changed
    assert "**Archive:** https://web.archive.org/web/1/https://example.com/report" in updated
    assert "**Archive 2:** https://web.archive.org/web/1/https://example.org/mirror" in updated
    assert calls == ["https://example.com/report", "https://example.org/mirror"], calls
    errors, _ = datamd.validate_entries(datamd.parse_blocks(updated))
    assert not errors, errors


@check("set_archive_fields keeps the block's trailing blank lines")
def set_archive_fields_preserves_trailing():
    block = "## Title\n\n**Source:** Example\n**URL:** https://example.com/report\n\nBody.\n\n"
    updated = generate.set_archive_fields(block, {1: "https://web.archive.org/web/1/x"})
    assert updated.endswith("Body.\n\n"), repr(updated)
    assert "**Archive:** https://web.archive.org/web/1/x" in updated


@check("archive_missing_links preserves formatting when nothing is missing")
def archive_roundtrip_is_stable():
    text = SAMPLE.replace("**Archive:**", "**Archive:** https://web.archive.org/web/1/x")
    original = generate.request_archive_snapshot
    generate.request_archive_snapshot = lambda url: (_ for _ in ()).throw(AssertionError(url))
    try:
        updated, changed = generate.archive_missing_links(text)
    finally:
        generate.request_archive_snapshot = original
    assert changed == 0, changed
    assert updated == text, updated


@check("prerender links the archive of every source")
def prerender_source_archives():
    record = generate.build_incidents(datamd.parse_blocks(two_source_sample()))["incidents"][0]
    html_out = prerender.render_article(record)
    assert "Mirror Research ↗" in html_out, html_out
    assert "Archived Mirror Research ↗" in html_out, html_out


class FakeCurl:
    def __init__(self, stdout, returncode=0):
        self.stdout = stdout
        self.returncode = returncode


@check("existing_snapshot asks the availability API first")
def availability_first():
    calls = []
    payload = (
        '{"archived_snapshots": {"closest": {"available": true,'
        ' "url": "http://web.archive.org/web/20260101/https://example.com/x"}}}'
    )
    original = generate._curl
    generate._curl = lambda args, timeout: calls.append(args[0]) or FakeCurl(payload)
    try:
        snapshot = generate.existing_snapshot("https://example.com/x")
    finally:
        generate._curl = original
    assert snapshot == "https://web.archive.org/web/20260101/https://example.com/x", snapshot
    assert calls and calls[0].startswith("https://archive.org/wayback/available"), calls


@check("request_archive_snapshot skips saving when a snapshot exists")
def no_save_when_existing():
    calls = []
    original_existing, original_save = generate.existing_snapshot, generate.save_snapshot
    generate.existing_snapshot = lambda url: calls.append("existing") or "https://web.archive.org/x"
    generate.save_snapshot = lambda url: calls.append("save") or ("", False)
    try:
        snapshot = generate.request_archive_snapshot("https://example.com/x")
    finally:
        generate.existing_snapshot, generate.save_snapshot = original_existing, original_save
    assert snapshot == "https://web.archive.org/x"
    assert calls == ["existing"], calls


@check("save_snapshot reports a 429 as a transient failure")
def save_429_is_transient():
    original = generate._curl
    generate._curl = lambda args, timeout: FakeCurl("Wayback Machine\n429")
    try:
        snapshot, transient = generate.save_snapshot("https://example.com/x")
    finally:
        generate._curl = original
    assert snapshot == "", snapshot
    assert transient is True, transient


@check("5xx and connection failures count as transient")
def save_5xx_is_transient():
    for body in ("Wayback Machine\n520", "curl: (28) timed out\n000"):
        original = generate._curl
        generate._curl = lambda args, timeout, body=body: FakeCurl(body)
        try:
            snapshot, transient = generate.save_snapshot("https://example.com/x")
        finally:
            generate._curl = original
        assert snapshot == "", (body, snapshot)
        assert transient is True, (body, transient)


@check("the Wayback circuit breaker stops after two transient failures")
def archive_breaker_trips():
    calls = []
    original_existing, original_save = generate.existing_snapshot, generate.save_snapshot
    generate.existing_snapshot = lambda url: ""
    generate.save_snapshot = lambda url: calls.append(url) or ("", True)
    generate.reset_archive_state()
    try:
        results = [generate.request_archive_snapshot(f"https://example.com/{i}") for i in range(4)]
    finally:
        generate.existing_snapshot, generate.save_snapshot = original_existing, original_save
        generate.reset_archive_state()
    assert results == ["", "", "", ""], results
    assert calls == ["https://example.com/0", "https://example.com/1"], calls


@check("reset_archive_state re-enables archiving for the next run")
def archive_breaker_reset():
    calls = []
    original_existing, original_save = generate.existing_snapshot, generate.save_snapshot
    generate.existing_snapshot = lambda url: ""
    generate.save_snapshot = lambda url: calls.append(url) or ("", True)
    generate.reset_archive_state()
    try:
        for i in range(3):
            generate.request_archive_snapshot(f"https://example.com/{i}")
        generate.reset_archive_state()
        generate.request_archive_snapshot("https://example.com/after-reset")
    finally:
        generate.existing_snapshot, generate.save_snapshot = original_existing, original_save
        generate.reset_archive_state()
    assert calls == [
        "https://example.com/0",
        "https://example.com/1",
        "https://example.com/after-reset",
    ], calls


@check("a successful snapshot resets the transient-failure count")
def archive_breaker_success_resets():
    calls = []
    original_existing, original_save = generate.existing_snapshot, generate.save_snapshot
    generate.existing_snapshot = lambda url: ""
    results = [("", True), ("https://web.archive.org/web/1/x", False), ("", True), ("", True)]
    generate.save_snapshot = lambda url: calls.append(url) or results.pop(0)
    generate.reset_archive_state()
    try:
        snapshots = [generate.request_archive_snapshot(f"https://example.com/{i}") for i in range(4)]
    finally:
        generate.existing_snapshot, generate.save_snapshot = original_existing, original_save
        generate.reset_archive_state()
    assert snapshots == ["", "https://web.archive.org/web/1/x", "", ""], snapshots
    assert len(calls) == 4, calls


@check("parse_blocks reads the optional Updated date")
def parse_updated():
    [entry] = datamd.parse_blocks(SAMPLE.replace("**Date:** 2026-01-01", "**Date:** 2026-01-01\n**Updated:** 2026-02-03"))
    assert entry["date"] == "2026-01-01"
    assert entry["updated"] == "2026-02-03"


@check("Updated before the incident date is an error")
def updated_before_date():
    broken = SAMPLE.replace("**Date:** 2026-01-01", "**Date:** 2026-01-01\n**Updated:** 2025-12-31")
    errors, _ = datamd.validate_entries(datamd.parse_blocks(broken))
    assert any("before the incident date" in error for error in errors), errors


@check("Updated must be an ISO date")
def updated_format():
    broken = SAMPLE.replace("**Date:** 2026-01-01", "**Date:** 2026-01-01\n**Updated:** last Tuesday")
    errors, _ = datamd.validate_entries(datamd.parse_blocks(broken))
    assert any("updated must be YYYY-MM-DD" in error for error in errors), errors


@check("build_incidents carries updated without moving the incident date")
def updated_in_json():
    sample = SAMPLE.replace("**Date:** 2026-01-01", "**Date:** 2026-01-01\n**Updated:** 2026-02-03")
    record = generate.build_incidents(datamd.parse_blocks(sample))["incidents"][0]
    assert record["date"] == "2026-01-01"
    assert record["updated"] == "2026-02-03"


@check("feed pubDate follows Updated and the guid stays stable")
def feed_uses_updated():
    sample = SAMPLE.replace("**Date:** 2026-01-01", "**Date:** 2026-01-01\n**Updated:** 2026-02-03")
    incidents = generate.build_incidents(datamd.parse_blocks(sample))["incidents"]
    feed = ET.fromstring(generate.render_feed(incidents))
    item = feed.find("channel/item")
    assert item.findtext("pubDate") == generate.format_rfc822_date("2026-02-03")
    assert item.findtext("guid") == f"ai-hack-watch:{incidents[0]['slug']}"


@check("prerender shows the Updated label")
def prerender_updated_label():
    sample = SAMPLE.replace("**Date:** 2026-01-01", "**Date:** 2026-01-01\n**Updated:** 2026-02-03")
    record = generate.build_incidents(datamd.parse_blocks(sample))["incidents"][0]
    html_out = prerender.render_article(record)
    assert '<span class="updated">Updated 03 Feb 2026</span>' in html_out, html_out


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


@check("story_bot treats _No response_ placeholders as empty (issue #35)")
def bot_no_response_placeholder():
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

_No response_

### Second source URL (optional)

_No response_

### Second source name (optional)

_No response_
"""
    fields = story_bot.parse_body(body)
    assert story_bot.validate(fields) == [], story_bot.validate(fields)
    entry = story_bot.draft_entry(fields, "Test incident")
    assert "**URL 2:**" not in entry
    assert "**Source 2:**" not in entry


@check("story_bot drafts second source URLs")
def bot_second_url():
    body = """### Article URL

https://example.com/report

### Second source URL (optional)

https://example.org/mirror

### Second source name (optional)

Mirror Research

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

_No response_
"""
    fields = story_bot.parse_body(body)
    assert story_bot.validate(fields) == [], story_bot.validate(fields)
    entry = story_bot.draft_entry(fields, "Test incident")
    assert "**URL 2:** https://example.org/mirror" in entry
    assert "**Source 2:** Mirror Research" in entry
    entries = datamd.parse_blocks(entry)
    errors, _ = datamd.validate_entries(entries)
    assert not errors, errors
    built = generate.build_incidents(entries)
    assert built["incidents"][0]["urls"] == [
        "https://example.com/report",
        "https://example.org/mirror",
    ]


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
    import subprocess
    import tempfile
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
            check=False,
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


@check("render_llms_txt follows the llmstxt.org layout")
def llms_txt():
    incidents = generate.build_incidents(datamd.parse_blocks(SAMPLE))
    text = generate.render_llms_txt(incidents)
    lines = text.splitlines()
    assert lines[0] == "# AI Hack Watch"
    assert lines[2].startswith("> ")
    assert "## Data" in lines and "## Optional" in lines
    assert f"covers {incidents['total']} incident" in text
    assert "(https://aihackwatch.com/incidents.json)" in text


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
    # Regression: prerender holds 20, dataset holds all — timeline must
    # rebuild on count mismatch, never hydrate a prefix as complete.
    assert "existing.length === wanted.length" in js
    assert "wanted.slice(0, existing.length)" not in js
    # Regression: per-source archives must render in the client too.
    assert "article.archives" in js
    assert "article.updated" in js


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