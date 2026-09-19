"""Shared parsing and validation for the data.md incident database.

Both the site generator (scripts/generate.py) and the pull-request
validator (scripts/validate_contribution.py) use this module, so the two
pipelines can never drift apart. Where behaviour overlaps with the
client-side script.js (slugify), the Python version mirrors it exactly.
"""

import re
import unicodedata
from datetime import date, datetime, timezone
from urllib.parse import urlparse

BLOCK_SPLIT_RE = re.compile(r"^---\s*$", re.M)
HEADING_RE = re.compile(r"^##\s+(.+)$")
FIELD_RE = re.compile(
    r"^\*\*(Date|Source|URL|Archive|AI role|Category):\*\*\s*(.*)$", re.I
)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

REQUIRED_FIELDS = ("date", "source", "url", "ai_role", "category")
ALLOWED_ROLES = ("Autonomous", "AI-assisted", "AI-targeted", "AI security research", "Unclear")


def slugify(value):
    """URL-safe slug, matching script.js slugify (NFKD-decomposed)."""
    lowered = unicodedata.normalize("NFKD", str(value).lower())
    stripped = re.sub(r"[^\w\s-]", "", lowered).strip()
    return re.sub(r"-+", "-", re.sub(r"\s+", "-", stripped)) or "incident"


def split_blocks(text):
    return [block.strip() for block in BLOCK_SPLIT_RE.split(text) if block.strip()]


def parse_blocks(text):
    """Parse data.md into incident dicts.

    Only blocks whose first line is a level-2 heading ("## ") are treated
    as incidents. Intro prose and separators are ignored. Blocks that
    cannot be split into a heading and a title are skipped.
    """
    entries = []
    for block in split_blocks(text):
        if not block.startswith("## "):
            continue
        heading = HEADING_RE.match(block.splitlines()[0])
        if not heading:
            continue
        fields = {}
        for line in block.splitlines()[1:]:
            field_match = FIELD_RE.match(line)
            if field_match:
                fields[field_match.group(1).lower().replace(" ", "_")] = (
                    field_match.group(2).strip()
                )
        parts = re.split(r"\n\s*\n", block, maxsplit=2)
        description = parts[-1].strip() if len(parts) >= 3 else ""
        entries.append(
            {
                "title": heading.group(1).strip(),
                "date": fields.get("date", ""),
                "source": fields.get("source", ""),
                "url": fields.get("url", ""),
                "archive": fields.get("archive", ""),
                "ai_role": fields.get("ai_role", ""),
                "category": fields.get("category", ""),
                "description": description,
            }
        )
    return entries


def validate_entries(entries):
    """Validate parsed entries; return (errors, warnings).

    Errors are conditions that must block generation or merging (missing
    fields, malformed/future dates, invalid URLs). Warnings are advisory
    (duplicate URLs, likely duplicate stories).
    """
    errors, warnings = [], []
    complete = []
    for entry in entries:
        title = entry["title"]
        missing = [field for field in REQUIRED_FIELDS if not entry.get(field)]
        if missing:
            errors.append(f"{title}: missing {', '.join(missing)}")
            continue
        complete.append(entry)
        date_value = entry["date"]
        if not DATE_RE.fullmatch(date_value):
            errors.append(f"{title}: date must be YYYY-MM-DD")
        else:
            try:
                if date.fromisoformat(date_value) > datetime.now(timezone.utc).date():
                    errors.append(f"{title}: date is in the future")
            except ValueError:
                errors.append(f"{title}: invalid ISO date")
        parsed_url = urlparse(entry["url"])
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            errors.append(f"{title}: invalid URL")
        if entry["ai_role"] not in ALLOWED_ROLES:
            errors.append(
                f'{title}: AI role "{entry["ai_role"]}" is not in the allowed set '
                f"({', '.join(ALLOWED_ROLES)})"
            )
        archive_value = entry.get("archive", "")
        if archive_value:
            parsed_archive = urlparse(archive_value)
            if parsed_archive.scheme not in ("http", "https") or not parsed_archive.netloc:
                errors.append(f"{title}: invalid Archive URL")

    by_url = {}
    for entry in complete:
        by_url.setdefault(entry["url"], []).append(entry)
    for url, matches in by_url.items():
        if len(matches) > 1:
            warnings.append("Duplicate URL: " + url)

    def words(value):
        return set(re.findall(r"[a-z0-9]+", value.lower()))

    for index, first in enumerate(complete):
        for second in complete[index + 1:]:
            if first["date"] != second["date"]:
                continue
            first_words, second_words = words(first["title"]), words(second["title"])
            similarity = len(first_words & second_words) / max(
                1, len(first_words | second_words)
            )
            if similarity >= 0.7:
                warnings.append(
                    'Likely duplicate on {}: {} / {}'.format(
                        first["date"], first["title"], second["title"]
                    )
                )
    return errors, warnings