"""Generate the static site data from data.md.

Produces incidents.json, days-since-badge.svg and feed.xml, and
optionally back-fills Wayback Machine archive links into data.md.

Fails loudly (exit code 1) when data.md is invalid, so the site can
never silently serve stale, empty, or partially-parsed data.

Usage:
    python3 scripts/generate.py --write-archives  # push path: archive + rewrite data.md
    python3 scripts/generate.py --no-archive       # skip Wayback (local dev, daily badge)
    python3 scripts/generate.py                    # in-memory archives, no data.md rewrite
"""

import argparse
import html
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote

import datamd

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data.md"
INCIDENTS_PATH = ROOT / "incidents.json"
BADGE_PATH = ROOT / "days-since-badge.svg"
FEED_PATH = ROOT / "feed.xml"

USER_AGENT = "ai-hack-watch/1.0"
ARCHIVE_SAVE_TIMEOUT = 30
ARCHIVE_CDX_TIMEOUT = 20
URL_FIELD_RE = re.compile(r"^\*\*URL(?: (\d+))?:\*\*[ \t]*(\S+)", re.M)
ARCHIVE_ANY_RE = re.compile(r"^\*\*Archive(?: (\d+))?:\*\*[ \t]*(.*)$", re.M)
WAYBACK_URL_RE = re.compile(r"https?://web\.archive\.org/web/\d+/\S+")
CONTENT_LOCATION_RE = re.compile(r"^content-location:\s*(.+)$", re.I | re.M)

_BADGE_SCRIPT = """<script><![CDATA[
var latest=document.documentElement.getAttribute("data-latest");
if(latest){
var d=Math.max(0,Math.floor((Date.UTC(new Date().getUTCFullYear(),new Date().getUTCMonth(),new Date().getUTCDate())-Date.parse(latest+"T00:00:00Z"))/86400000));
var value=(d+" "+(d===1?"day":"days")),lw=170,vw=Math.max(70,20+value.length*8),total=lw+vw;
document.documentElement.setAttribute("width",total);
document.documentElement.setAttribute("aria-label","AI Hack Watch: "+d);
document.getElementById("box").setAttribute("width",total);
var vb=document.getElementById("value-box");vb.setAttribute("x",lw);vb.setAttribute("width",vw);
var t=document.getElementById("value");t.setAttribute("x",lw+vw/2);t.textContent=value;
}
]]></script>"""


def _curl(args, timeout):
    """Run curl with a capped timeout; return the result or None."""
    try:
        return subprocess.run(
            ["curl", "-L", "-sS", "--max-time", str(timeout), "-A", USER_AGENT, *args],
            capture_output=True,
            text=True,
            timeout=timeout + 5,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _http_status(result):
    """HTTP status from a curl run that appended -w '\\n%{http_code}'."""
    if not result:
        return 0
    tail = result.stdout.rstrip().rsplit("\n", 1)[-1].strip()
    return int(tail) if tail.isdigit() else 0


def existing_snapshot(url):
    """Return an existing Wayback snapshot for url, or "".

    Checks the availability API first because it is much cheaper than
    requesting a fresh save, then falls back to CDX if the API does not
    answer. Returning early avoids most of the rate limiting that used to
    make archiving fail for every URL in a run.
    """
    query = "https://archive.org/wayback/available?url=" + quote(url, safe="")
    result = _curl([query], ARCHIVE_CDX_TIMEOUT)
    if result and result.returncode == 0:
        try:
            payload = json.loads(result.stdout)
        except ValueError:
            payload = None
        if payload is not None:
            closest = (payload.get("archived_snapshots") or {}).get("closest") or {}
            snapshot = closest.get("url") or ""
            if closest.get("available") and snapshot:
                return snapshot.replace("http://web.archive.org", "https://web.archive.org", 1)
            return ""  # the API answered: no snapshot exists yet

    query = (
        "https://web.archive.org/cdx/search/cdx?url="
        + quote(url, safe="")
        + "&output=json&filter=statuscode:200&fl=timestamp,original"
        "&limit=1&sort=reverse"
    )
    result = _curl([query], ARCHIVE_CDX_TIMEOUT)
    if result and result.returncode == 0:
        try:
            rows = json.loads(result.stdout)
            if len(rows) > 1:
                return f"https://web.archive.org/web/{rows[1][0]}/{rows[1][1]}"
        except ValueError:
            pass
    return ""


def save_snapshot(url):
    """Ask Wayback to archive url now.

    Returns (snapshot, transient). A transient failure means the service
    is rate limiting or offline, which the caller uses to stop asking for
    the rest of the run instead of flooding a struggling service.
    """
    result = _curl(
        ["-D", "-", "-w", "\n%{http_code}", f"https://web.archive.org/save/{url}"],
        ARCHIVE_SAVE_TIMEOUT,
    )
    status = _http_status(result)
    output = result.stdout if result else ""
    header = CONTENT_LOCATION_RE.search(output)
    if header:
        location = header.group(1).strip().splitlines()[0].strip()
        if location.startswith("http"):
            return location, False
        return "https://web.archive.org" + location, False
    match = WAYBACK_URL_RE.search(output)
    if match:
        return match.group(0).rstrip('"'), False
    # 429, every 5xx, and a missing response all mean "try again later".
    # 520 in particular is what Wayback returns while it is degraded.
    if status == 0 or status == 429 or 500 <= status < 600 or "Temporarily Offline" in output:
        return "", True
    print(f"::warning::Wayback refused to archive {url} (HTTP {status or 'no response'})")
    return "", False


# A single degraded service must not turn one run into a retry storm.
ARCHIVE_MAX_TRANSIENT_FAILURES = 2
_archive_transient_failures = 0
_archive_disabled = False


def reset_archive_state():
    """Reset the per-run Wayback circuit breaker."""
    global _archive_transient_failures, _archive_disabled
    _archive_transient_failures = 0
    _archive_disabled = False


def request_archive_snapshot(url):
    """Best-effort Wayback snapshot for url; "" when none is available.

    Existing snapshots are used first. New saves stop after a couple of
    consecutive transient failures so an outage costs two requests, not
    one per URL.
    """
    global _archive_transient_failures, _archive_disabled
    if _archive_disabled:
        return ""
    snapshot = existing_snapshot(url)
    if snapshot:
        _archive_transient_failures = 0
        return snapshot
    snapshot, transient = save_snapshot(url)
    if snapshot:
        _archive_transient_failures = 0
        return snapshot
    if transient:
        _archive_transient_failures += 1
        if _archive_transient_failures >= ARCHIVE_MAX_TRANSIENT_FAILURES and not _archive_disabled:
            _archive_disabled = True
            print(
                "::warning::Wayback appears unavailable; skipping further archive "
                "requests this run and retrying on the next run."
            )
    return ""


def archive_field_line(number, value):
    """Markdown line for the archive snapshot of source `number`."""
    label = "Archive" if number == 1 else f"Archive {number}"
    return f"**{label}:** {value}"


def set_archive_fields(block, updates):
    """Fill or insert per-source Archive fields in one data.md block.

    Existing fields are rewritten in place. Missing ones are inserted
    after the last existing Archive field, so field order stays stable
    across repeated runs.
    """
    lines = block.splitlines()
    for number in sorted(updates):
        value = updates[number]
        target = None
        for index, line in enumerate(lines):
            match = ARCHIVE_ANY_RE.match(line)
            if match and int(match.group(1) or 1) == number:
                target = index
                break
        if target is not None:
            lines[target] = archive_field_line(number, value)
            continue
        insert_at = None
        for index, line in enumerate(lines):
            if ARCHIVE_ANY_RE.match(line):
                insert_at = index + 1
        if insert_at is None:
            for index, line in enumerate(lines):
                if re.match(r"^\*\*URL(?: \d+)?:\*\*", line):
                    insert_at = index + 1
        if insert_at is None:
            for index, line in enumerate(lines):
                if re.match(r"^\*\*Source(?: \d+)?:\*\*", line):
                    insert_at = index + 1
        lines.insert(len(lines) if insert_at is None else insert_at, archive_field_line(number, value))
    return "\n".join(lines)


def archive_missing_links(text):
    """Add Wayback snapshots for every source whose Archive field is empty.

    Each `**URL n:**` pairs with `**Archive n:**`; the primary source keeps
    the unnumbered `**Archive:**`. Returns the (possibly rewritten) text
    plus a count of archive links written back into data.md.
    """
    blocks = re.split(r"^---\s*$", text, flags=re.M)
    changed = 0
    reset_archive_state()
    for index, block in enumerate(blocks):
        if not block.strip().startswith("## "):
            continue
        urls = [(int(number or 1), url) for number, url in URL_FIELD_RE.findall(block)]
        if not urls:
            continue
        existing = {
            int(number or 1): value.strip()
            for number, value in ARCHIVE_ANY_RE.findall(block)
        }
        updates = {}
        for number, url in urls:
            if existing.get(number):
                continue
            try:
                snapshot = request_archive_snapshot(url)
            except Exception as error:  # never let archiving break the build
                print(f"::warning::Wayback archiving failed for {url}: {error}")
                continue
            if snapshot:
                updates[number] = snapshot
                print(f"Archive added: {snapshot}")
            else:
                print(f"::warning::No Wayback snapshot returned for {url}")
            if not _archive_disabled:
                time.sleep(0.5)  # stay well inside archive.org's rate limits
        if updates:
            blocks[index] = set_archive_fields(block, updates)
            changed += len(updates)
    # The split consumes the newline after each separator, so rejoin with it
    # to keep the file byte-identical apart from the new Archive fields.
    return "---\n".join(blocks), changed


SCHEMA_VERSION = 3
CHUNK_SIZE = 20  # hint for future pagination


def format_rfc822_date(date_value):
    """Format a YYYY-MM-DD calendar date as an RFC-822 pubDate (midnight UTC)."""
    parsed = date.fromisoformat(date_value)
    dt = datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
    return format_datetime(dt, usegmt=True)


def format_rfc822_now(now=None):
    now = now or datetime.now(timezone.utc)
    return format_datetime(now.astimezone(timezone.utc), usegmt=True)


def assign_unique_slugs(titles):
    """Dedupe title slugs deterministically: base, base-2, base-3, ..."""
    counts = {}
    slugs = []
    for title in titles:
        base = datamd.slugify(title)
        counts[base] = counts.get(base, 0) + 1
        if counts[base] == 1:
            slugs.append(base)
        else:
            slugs.append(f"{base}-{counts[base]}")
    return slugs


def apply_archives_in_memory(entries):
    """Fill missing per-source Archive values in-memory (no data.md rewrite).

    Used for daily badge refreshes and local builds so data.md is only
    rewritten when --write-archives is passed explicitly.
    """
    reset_archive_state()
    for entry in entries:
        urls = entry.get("urls") or ([entry["url"]] if entry.get("url") else [])
        archives = list(entry.get("archives") or [])
        archives += [""] * (len(urls) - len(archives))
        for index, url in enumerate(urls):
            if archives[index]:
                continue
            try:
                snapshot = request_archive_snapshot(url)
            except Exception as error:  # never let archiving break the build
                print(f"::warning::Wayback archiving failed for {url}: {error}")
                continue
            if snapshot:
                archives[index] = snapshot
                print(f"Archive resolved (in-memory): {snapshot}")
            else:
                print(f"::warning::No Wayback snapshot returned for {url}")
        entry["archives"] = archives
        entry["archive"] = archives[0] if archives else ""
    return entries


def incident_record(entry, slug):
    """Build one incidents.json record, padding archives to align with urls."""
    urls = list(entry.get("urls") or [entry["url"]])
    archives = list(entry.get("archives") or [])
    archives += [""] * (len(urls) - len(archives))
    return {
        "date": entry["date"],
        "updated": entry.get("updated", ""),
        "source": entry["source"],
        "sources": list(entry.get("sources") or [entry["source"]]),
        "title": entry["title"],
        "description": entry["description"],
        "url": entry["url"],
        "urls": urls,
        "archive": archives[0] if archives else entry.get("archive", ""),
        "archives": archives[: len(urls)],
        "role": entry["ai_role"],
        "category": entry["category"],
        "slug": slug,
    }


def build_incidents(entries):
    # Sort newest-first first so slug dedupe is deterministic:
    # the newest duplicate keeps the base slug.
    sorted_entries = sorted(entries, key=lambda e: e["date"], reverse=True)
    slugs = assign_unique_slugs([e["title"] for e in sorted_entries])
    incidents = [
        incident_record(entry, slug)
        for entry, slug in zip(sorted_entries, slugs)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "chunk_size": CHUNK_SIZE,
        "total": len(incidents),
        "taxonomy": {
            "roles": list(datamd.ALLOWED_ROLES),
            "categories": list(datamd.ALLOWED_CATEGORIES),
        },
        "incidents": incidents,
    }


def render_badge(days, latest_date):
    value = f"{days} days"
    label_width = 170
    value_width = max(70, 20 + len(value) * 8)
    total_width = label_width + value_width
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="28" '
        f'role="img" aria-label="AI Hack Watch: {days}" data-latest="{latest_date}">'
        f'<rect id="box" width="{total_width}" height="28" rx="4" fill="#111"/>'
        f'<rect id="value-box" x="{label_width}" width="{value_width}" height="28" '
        f'rx="4" fill="#d9ff3f"/>'
        f'<text id="label" x="{label_width / 2}" y="18" fill="#fff" '
        f'font-family="Arial" font-size="11" text-anchor="middle">AI Hack Watch</text>'
        f'<text id="value" x="{label_width + value_width / 2}" y="18" fill="#111" '
        f'font-family="Arial" font-size="12" font-weight="700" '
        f'text-anchor="middle">{html.escape(value)}</text>'
        + _BADGE_SCRIPT
        + "</svg>"
    )


def render_feed(incidents):
    items = []
    for article in incidents:
        # Stable guid from slug (URLs can change); pubDate/lastBuildDate
        # must be RFC-822 for RSS readers.
        guid = f"ai-hack-watch:{article.get('slug') or datamd.slugify(article['title'])}"
        try:
            # Revisions keep their guid but move pubDate, so readers show an
            # update rather than a brand-new item.
            pub_date = format_rfc822_date(article.get("updated") or article["date"])
        except ValueError:
            pub_date = format_rfc822_now()
        items.append(
            f"<item><title>{html.escape(article['title'])}</title>"
            f"<link>{html.escape(article['url'])}</link>"
            f'<guid isPermaLink="false">{html.escape(guid)}</guid>'
            f"<pubDate>{pub_date}</pubDate>"
            f"<description>{html.escape(article['description'])}</description></item>"
        )
    build_time = format_rfc822_now()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel><title>AI Hack Watch</title>'
        "<description>Public timeline of notable AI hacking and AI-enabled"
        " cyber incidents.</description>"
        f"<link>./</link><lastBuildDate>{build_time}</lastBuildDate>"
        + "".join(items)
        + "</channel></rss>\n"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--no-archive", action="store_true", help="skip Wayback Machine archiving"
    )
    parser.add_argument(
        "--write-archives",
        action="store_true",
        help="rewrite data.md with newly archived URLs (push path only)",
    )
    args = parser.parse_args(argv)

    text = DATA_PATH.read_text(encoding="utf-8")

    if args.write_archives and args.no_archive:
        print("ERROR: --write-archives and --no-archive are mutually exclusive")
        return 1

    if args.write_archives:
        text, changed = archive_missing_links(text)
        if changed:
            DATA_PATH.write_text(text, encoding="utf-8")

    entries = datamd.parse_blocks(text)
    errors, warnings = datamd.validate_entries(entries)
    for warning in warnings:
        print("WARNING: " + warning)
    if errors:
        for error in errors:
            print("ERROR: " + error)
        print(
            f"Refusing to generate site data: {len(errors)} error(s) in "
            f"{DATA_PATH.name}. Fix them and re-run."
        )
        return 1

    if not args.no_archive and not args.write_archives:
        # Resolve archives in-memory so daily/local builds get archive
        # links in JSON/feed without mutating data.md (avoids merge races).
        entries = apply_archives_in_memory(entries)

    incidents = build_incidents(entries)
    if not incidents["incidents"]:
        print(f"ERROR: no incidents found in {DATA_PATH.name}; refusing to write an empty dataset.")
        return 1

    INCIDENTS_PATH.write_text(
        json.dumps(incidents, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    latest = incidents["incidents"][0]
    days = max(0, (datetime.now(timezone.utc).date() - date.fromisoformat(latest["date"])).days)
    BADGE_PATH.write_text(render_badge(days, latest["date"]), encoding="utf-8")
    FEED_PATH.write_text(render_feed(incidents["incidents"]), encoding="utf-8")

    print(f"Generated {incidents['total']} incident(s); {len(warnings)} warning(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())