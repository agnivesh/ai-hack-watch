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

BLOCK_SPLIT_RE = re.compile(r"^---\s*$", re.MULTILINE)
HEADING_RE = re.compile(r"^##\s+(.+)$")
FIELD_RE = re.compile(
    r"^\*\*(Date|Updated|Source|URL|Archive|AI role|Category)( \d+)?:\*\*\s*(.*)$", re.IGNORECASE
)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

REQUIRED_FIELDS = ("date", "source", "url", "ai_role", "category")
ALLOWED_ROLES = ("Autonomous", "AI-assisted", "AI-targeted", "AI security research", "Unclear")
ALLOWED_CATEGORIES = (
    "Security research",
    "Vulnerability research",
    "Cyber operations",
    "Malware",
    "Credential theft",
    "Cloud infrastructure",
    "AI model compromise",
    "Other",
)


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

    Multiple sources are supported with numbered fields (`**URL 2:**`,
    `**Source 3:**`, ...); the first value is primary and all values are
    kept ordered in `urls`/`sources`. Numbered archives (`**Archive 2:**`)
    pair with the source of the same number and are returned in
    `archives`, which is index-aligned with `urls`. `archive` stays the
    primary snapshot for consumers that predate per-source archives.

    `**Updated:**` is the optional date of the latest material revision
    of an entry; `date` remains the first public disclosure.
    """
    entries = []
    for block in split_blocks(text):
        if not block.startswith("## "):
            continue
        heading = HEADING_RE.match(block.splitlines()[0])
        if not heading:
            continue
        values = {}
        for line in block.splitlines()[1:]:
            field_match = FIELD_RE.match(line)
            if field_match:
                key = field_match.group(1).lower().replace(" ", "_")
                number = int(field_match.group(2)) if field_match.group(2) else 1
                values.setdefault(key, {})[number] = field_match.group(3).strip()

        def first(key, values=values):
            numbered = values.get(key, {})
            return numbered.get(1, "")

        def ordered(key, values=values):
            return [value for _, value in sorted(values.get(key, {}).items())]

        sources = ordered("source")
        urls = ordered("url")
        archives_by_number = values.get("archive", {})
        archive_span = max([len(urls), *archives_by_number]) if urls or archives_by_number else 0
        archives = [archives_by_number.get(number, "") for number in range(1, archive_span + 1)]
        parts = re.split(r"\n\s*\n", block, maxsplit=2)
        description = parts[-1].strip() if len(parts) >= 3 else ""
        entries.append(
            {
                "title": heading.group(1).strip(),
                "date": first("date"),
                "updated": first("updated"),
                "source": sources[0] if sources else "",
                "sources": sources,
                "url": urls[0] if urls else "",
                "urls": urls,
                "archive": archives[0] if archives else "",
                "archives": archives,
                "ai_role": first("ai_role"),
                "category": first("category"),
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
        updated_value = entry.get("updated", "")
        if updated_value:
            if not DATE_RE.fullmatch(updated_value):
                errors.append(f"{title}: updated must be YYYY-MM-DD")
            else:
                try:
                    updated_date = date.fromisoformat(updated_value)
                    if updated_date > datetime.now(timezone.utc).date():
                        errors.append(f"{title}: updated date is in the future")
                    try:
                        if updated_date < date.fromisoformat(date_value):
                            errors.append(f"{title}: updated date is before the incident date")
                    except ValueError:
                        pass  # the primary date error is reported above
                except ValueError:
                    errors.append(f"{title}: invalid ISO updated date")
        parsed_url = urlparse(entry["url"])
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            errors.append(f"{title}: invalid URL")
        for extra_url in entry.get("urls", [])[1:]:
            parsed_extra = urlparse(extra_url)
            if parsed_extra.scheme not in ("http", "https") or not parsed_extra.netloc:
                errors.append(f"{title}: invalid URL 2+: {extra_url}")
        if entry["ai_role"] not in ALLOWED_ROLES:
            errors.append(
                f'{title}: AI role "{entry["ai_role"]}" is not in the allowed set '
                f"({', '.join(ALLOWED_ROLES)})"
            )
        if entry["category"] not in ALLOWED_CATEGORIES:
            errors.append(
                f'{title}: category "{entry["category"]}" is not in the allowed set '
                f"({', '.join(ALLOWED_CATEGORIES)})"
            )
        archive_values = entry.get("archives") or ([entry["archive"]] if entry.get("archive") else [])
        for index, archive_value in enumerate(archive_values, start=1):
            if not archive_value:
                continue
            parsed_archive = urlparse(archive_value)
            if parsed_archive.scheme not in ("http", "https") or not parsed_archive.netloc:
                label = "Archive" if index == 1 else f"Archive {index}"
                errors.append(f"{title}: invalid {label} URL")
            if index > len(entry.get("urls") or [entry["url"]]):
                errors.append(f"{title}: Archive {index} has no matching URL {index}")
        for label, value in (("source", entry["source"]), ("url", entry["url"])):
            if value.endswith("**"):
                errors.append(f'{title}: {label} ends with stray "**"')
        for index, archive_value in enumerate(archive_values, start=1):
            if archive_value.endswith("**"):
                label = "archive" if index == 1 else f"archive {index}"
                errors.append(f'{title}: {label} ends with stray "**"')

    by_url = {}
    for entry in complete:
        for url in entry.get("urls") or [entry["url"]]:
            by_url.setdefault(url, []).append(entry["title"])
    for url, titles in by_url.items():
        if len(titles) > 1:
            warnings.append("Duplicate URL: " + url)

    by_slug = {}
    for entry in complete:
        by_slug.setdefault(slugify(entry["title"]), []).append(entry["title"])
    for slug, titles in by_slug.items():
        if len(titles) > 1:
            warnings.append(
                f'Duplicate slug "{slug}": {" / ".join(titles)} '
                "(generator will dedupe with -2, -3 suffixes)"
            )

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