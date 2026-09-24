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
ARCHIVE_URL_RE = re.compile(r"^\*\*URL(?: \d+)?:\*\*[ \t]*(\S+)", re.M)
ARCHIVE_FIELD_RE = re.compile(r"^\*\*Archive:\*\*[ \t]*(.*)$", re.M)
ARCHIVE_FILL_RE = re.compile(r"(^\*\*Archive:\*\*)[ \t]*$", re.M)
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


def request_archive_snapshot(url):
    """Best-effort Wayback Machine snapshot for url; "" when none is found.

    The save endpoint announces the new snapshot via the Content-Location
    response header (not the body), so headers are captured with curl -D.
    """
    snapshot = ""
    for _ in range(2):  # transient failures on save are common; retry once
        result = _curl(
            ["-D", "-", f"https://web.archive.org/save/{url}"], ARCHIVE_SAVE_TIMEOUT
        )
        if not result:
            continue
        header = CONTENT_LOCATION_RE.search(result.stdout)
        if header:
            location = header.group(1).strip().splitlines()[0].strip()
            if location.startswith("http"):
                snapshot = location
            else:
                snapshot = "https://web.archive.org" + location
            break
        match = WAYBACK_URL_RE.search(result.stdout)
        if match:
            snapshot = match.group(0).rstrip('"')
            break
    if not snapshot:
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
                    snapshot = f"https://web.archive.org/web/{rows[1][0]}/{rows[1][1]}"
            except ValueError:
                pass
    return snapshot


def archive_missing_links(text):
    """Add Wayback snapshots for incidents whose Archive field is empty.

    Tries each listed source URL (primary first) until one snapshot is
    captured. Returns the (possibly rewritten) text plus a count of
    archive links written back into data.md.
    """
    blocks = re.split(r"^---\s*$", text, flags=re.M)
    changed = 0
    for index, block in enumerate(blocks):
        if not block.strip().startswith("## "):
            continue
        urls = re.findall(r"^\*\*URL(?: \d+)?:\*\*\s*(\S+)", block, re.M)
        archive_match = ARCHIVE_FIELD_RE.search(block)
        if not (urls and archive_match and not archive_match.group(1).strip()):
            continue
        snapshot = ""
        for url in urls:
            try:
                snapshot = request_archive_snapshot(url)
            except Exception as error:  # never let archiving break the build
                print(f"::warning::Wayback archiving failed for {url}: {error}")
                continue
            if snapshot:
                break
        if snapshot:
            blocks[index] = ARCHIVE_FILL_RE.sub(r"\1 " + snapshot, block)
            changed += 1
            print(f"Archive added: {snapshot}")
        else:
            print(f"::warning::No Wayback snapshot returned for {'; '.join(urls)}")
    return "\n---\n".join(blocks), changed


SCHEMA_VERSION = 1
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
    """Fill missing Archive values in-memory (no data.md rewrite).

    Used for daily badge refreshes and local builds so data.md is only
    rewritten when --write-archives is passed explicitly.
    """
    for entry in entries:
        if entry.get("archive"):
            continue
        for url in entry.get("urls") or ([entry["url"]] if entry.get("url") else []):
            try:
                snapshot = request_archive_snapshot(url)
            except Exception as error:  # never let archiving break the build
                print(f"::warning::Wayback archiving failed for {url}: {error}")
                continue
            if snapshot:
                entry["archive"] = snapshot
                print(f"Archive resolved (in-memory): {snapshot}")
                break
        else:
            urls = entry.get("urls") or [entry.get("url", "")]
            print(f"::warning::No Wayback snapshot returned for {'; '.join(urls)}")
    return entries


def build_incidents(entries):
    # Sort newest-first first so slug dedupe is deterministic:
    # the newest duplicate keeps the base slug.
    sorted_entries = sorted(entries, key=lambda e: e["date"], reverse=True)
    slugs = assign_unique_slugs([e["title"] for e in sorted_entries])
    incidents = [
        {
            "date": entry["date"],
            "source": entry["source"],
            "title": entry["title"],
            "description": entry["description"],
            "url": entry["url"],
            "urls": list(entry.get("urls") or [entry["url"]]),
            "archive": entry.get("archive", ""),
            "role": entry["ai_role"],
            "category": entry["category"],
            "slug": slug,
        }
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
            pub_date = format_rfc822_date(article["date"])
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