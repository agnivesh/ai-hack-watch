import argparse
import html
import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import datamd


INCIDENT_LIMIT = 20
ROOT = Path(__file__).resolve().parents[1]
START_MARKER = "<!-- PRE_RENDERED_TIMELINE_START -->"
END_MARKER = "<!-- PRE_RENDERED_TIMELINE_END -->"
MARKER_PATTERN = re.compile(
    f"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", re.DOTALL
)


def load_site_url():
    """Read the public site URL from config.js, if configured."""
    config_path = ROOT / "config.js"
    match = re.search(r'siteUrl\s*:\s*"([^"]+)"', config_path.read_text(encoding="utf-8"))
    return match.group(1).rstrip("/") if match else ""


def inject_site_urls(index, site_url):
    """Fill canonical/og:url/og:image tags with the public site URL.

    Idempotent: safe to run against an already-injected index.html.
    Returns (updated_index, number_of_injections_applied).
    """
    if not site_url:
        return index, 0
    substitutions = [
        (r'(<link rel="canonical" href=")[^"]*(">)', rf'\g<1>{site_url}\g<2>'),
        (r'(<meta property="og:url" content=")[^"]*(">)', rf'\g<1>{site_url}\g<2>'),
        (
            r'(<meta property="og:image" content=")[^"]*days-since-badge\.svg(">)',
            rf'\g<1>{site_url}/days-since-badge.svg\g<2>',
        ),
    ]
    applied = 0
    for pattern, replacement in substitutions:
        index, count = re.subn(pattern, replacement, index, count=1)
        applied += count
    return index, applied


def text(value, fallback=""):
    return str(value) if value else fallback


def safe_url(value):
    url = text(value)
    parsed_url = urlparse(url)
    if parsed_url.scheme in {"http", "https"} and parsed_url.netloc:
        return url
    return ""


def format_date(value):
    incident_date = date.fromisoformat(text(value))
    return incident_date.strftime("%d %b %Y")


def render_link(url, label):
    if not url:
        return ""
    return (
        f'<a href="{html.escape(url, quote=True)}" target="_blank" '
        f'rel="noopener noreferrer">{label}</a>'
    )


def render_article(article):
    title = html.escape(text(article.get("title"), "Untitled incident"))
    source = html.escape(text(article.get("source"), "Unknown source"))
    description = html.escape(text(article.get("description")))
    role = html.escape(text(article.get("role")))
    category = html.escape(text(article.get("category")))
    slug = html.escape(
        datamd.slugify(article.get("slug") or article.get("title")), quote=True
    )
    source_link = render_link(safe_url(article.get("url")), "Read source ↗")
    archive_link = render_link(safe_url(article.get("archive")), "Archived copy ↗")
    extra_links = "".join(
        render_link(safe_url(extra_url), "Alternative source ↗")
        for extra_url in (article.get("urls") or [])[1:]
    )
    tags = "".join(
        f'<button type="button" class="tag tag-filter" data-filter="{html.escape(tag, quote=True)}" aria-pressed="false">{tag}</button>'
        for tag in (role, category) if tag
    )
    links = "".join(
        link for link in (source_link, archive_link, extra_links) if link
    )

    return f'''      <article class="item" id="{slug}">
        <div class="date">{format_date(article.get("date"))}</div>
        <div class="dot-wrap"><div class="dot"></div></div>
        <div class="card">
          <div class="source">{source}</div>
          <h3>{title} <a class="permalink" href="#{slug}">#</a></h3>
          <div class="tags">{tags}</div>
          <p>{description}</p>
          <div class="card-links">{links}</div>
        </div>
      </article>'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.environ.get("AI_HACK_WATCH_INCIDENT_LIMIT", INCIDENT_LIMIT)),
        help=f"how many most-recent incidents to pre-render (default: {INCIDENT_LIMIT})",
    )
    args = parser.parse_args(argv)
    data_path = ROOT / "incidents.json"
    index_path = ROOT / "index.html"
    data = json.loads(data_path.read_text())
    incidents = data.get("incidents", data)  # backward compat with old flat array
    incidents.sort(key=lambda article: article["date"], reverse=True)
    articles = "\n".join(render_article(article) for article in incidents[:args.limit])
    rendered_timeline = f"{START_MARKER}\n{articles}\n      {END_MARKER}"
    index = index_path.read_text()
    updated_index, replacements = MARKER_PATTERN.subn(rendered_timeline, index)
    if replacements != 1:
        raise ValueError("Expected exactly one pre-rendered timeline marker block")
    site_url = load_site_url()
    updated_index, injected = inject_site_urls(updated_index, site_url)
    if site_url and injected == 0:
        print("::warning::Could not inject site URL into index.html (template may have changed)")
    index_path.write_text(updated_index)


if __name__ == "__main__":
    main()
