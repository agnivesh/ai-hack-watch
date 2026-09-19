"""Generate the static site data from data.md.

Produces incidents.json, days-since-badge.svg and feed.xml, and
optionally back-fills Wayback Machine archive links into data.md.

Fails loudly (exit code 1) when data.md is invalid, so the site can
never silently serve stale, empty, or partially-parsed data.

Usage:
    python3 scripts/generate.py                # full run incl. Wayback archiving
    python3 scripts/generate.py --no-archive   # skip Wayback (local dev)
"""

import argparse
import html
import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
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
ARCHIVE_URL_RE = re.compile(r"^\*\*URL:\*\*\s*(\S+)", re.M)
ARCHIVE_FIELD_RE = re.compile(r"^\*\*Archive:\*\*\s*(.*)$", re.M)
ARCHIVE_FILL_RE = re.compile(r"(^\*\*Archive:\*\*)\s*$", re.M)
WAYBACK_URL_RE = re.compile(r"https?://web\.archive\.org/web/\d+/\S+")

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
    """Best-effort Wayback Machine snapshot for url; "" when none is found."""
    snapshot = ""
    for _ in range(2):  # transient failures on save are common; retry once
        result = _curl([f"https://web.archive.org/save/{url}"], ARCHIVE_SAVE_TIMEOUT)
        if not result:
            continue
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

    Returns the (possibly rewritten) text plus a count of archive links
    written back into data.md.
    """
    blocks = re.split(r"^---\s*$", text, flags=re.M)
    changed = 0
    for index, block in enumerate(blocks):
        if not block.strip().startswith("## "):
            continue
        url_match = ARCHIVE_URL_RE.search(block)
        archive_match = ARCHIVE_FIELD_RE.search(block)
        if not (url_match and archive_match and not archive_match.group(1).strip()):
            continue
        url = url_match.group(1).strip()
        try:
            snapshot = request_archive_snapshot(url)
        except Exception as error:  # never let archiving break the build
            print(f"::warning::Wayback archiving failed for {url}: {error}")
            continue
        if snapshot:
            blocks[index] = ARCHIVE_FILL_RE.sub(r"\1 " + snapshot, block, flags=re.M)
            changed += 1
            print(f"Archive added: {snapshot}")
        else:
            print(f"::warning::No Wayback snapshot returned for {url}")
    return "\n---\n".join(blocks), changed


def build_incidents(entries):
    incidents = [
        {
            "date": entry["date"],
            "source": entry["source"],
            "title": entry["title"],
            "description": entry["description"],
            "url": entry["url"],
            "archive": entry.get("archive", ""),
            "role": entry["ai_role"],
            "category": entry["category"],
            "slug": datamd.slugify(entry["title"]),
        }
        for entry in entries
    ]
    incidents.sort(key=lambda item: item["date"], reverse=True)
    return incidents


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
        items.append(
            f"<item><title>{html.escape(article['title'])}</title>"
            f"<link>{html.escape(article['url'])}</link>"
            f'<guid isPermaLink="true">{html.escape(article["url"])}</guid>'
            f"<pubDate>{article['date']}T00:00:00Z</pubDate>"
            f"<description>{html.escape(article['description'])}</description></item>"
        )
    build_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
    args = parser.parse_args(argv)

    text = DATA_PATH.read_text(encoding="utf-8")

    if not args.no_archive:
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

    incidents = build_incidents(entries)
    if not incidents:
        print(f"ERROR: no incidents found in {DATA_PATH.name}; refusing to write an empty dataset.")
        return 1

    INCIDENTS_PATH.write_text(
        json.dumps(incidents, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    latest = incidents[0]
    days = max(0, (datetime.now(timezone.utc).date() - date.fromisoformat(latest["date"])).days)
    BADGE_PATH.write_text(render_badge(days, latest["date"]), encoding="utf-8")
    FEED_PATH.write_text(render_feed(incidents), encoding="utf-8")

    print(f"Generated {len(incidents)} incident(s); {len(warnings)} warning(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())