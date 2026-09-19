import html
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


INCIDENT_LIMIT = 20
START_MARKER = "<!-- PRE_RENDERED_TIMELINE_START -->"
END_MARKER = "<!-- PRE_RENDERED_TIMELINE_END -->"
MARKER_PATTERN = re.compile(
    f"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", re.DOTALL
)


def text(value, fallback=""):
    return str(value) if value else fallback


def safe_url(value):
    url = text(value)
    parsed_url = urlparse(url)
    if parsed_url.scheme in {"http", "https"} and parsed_url.netloc:
        return url
    return ""


def slugify(value):
    normalized = re.sub(r"[^\w\s-]", "", text(value).lower()).strip()
    return re.sub(r"[-\s]+", "-", normalized) or "incident"


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
    slug = html.escape(slugify(article.get("slug") or article.get("title")), quote=True)
    source_link = render_link(safe_url(article.get("url")), "Read source ↗")
    archive_link = render_link(safe_url(article.get("archive")), "Archived copy ↗")
    tags = "".join(
        f'<button type="button" class="tag tag-filter" data-filter="{html.escape(tag, quote=True)}" aria-pressed="false">{tag}</button>'
        for tag in (role, category) if tag
    )
    links = "".join(link for link in (source_link, archive_link) if link)

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


def main():
    root_path = Path(__file__).resolve().parents[1]
    data_path = root_path / "incidents.json"
    index_path = root_path / "index.html"
    incidents = json.loads(data_path.read_text())
    incidents.sort(key=lambda article: article["date"], reverse=True)
    articles = "\n".join(render_article(article) for article in incidents[:INCIDENT_LIMIT])
    rendered_timeline = f"{START_MARKER}\n{articles}\n      {END_MARKER}"
    index = index_path.read_text()
    updated_index, replacements = MARKER_PATTERN.subn(rendered_timeline, index)
    if replacements != 1:
        raise ValueError("Expected exactly one pre-rendered timeline marker block")
    index_path.write_text(updated_index)


if __name__ == "__main__":
    main()
