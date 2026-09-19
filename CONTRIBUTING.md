# Contributing

Thanks for helping maintain **AI Hack Watch**.

The project is intentionally simple: contributors add or correct entries in `data.md`, and GitHub Actions generates the data used by the static website.

## What makes a good contribution?

An article should be a substantive report about AI being involved in hacking or cybersecurity activity.

Examples can include:

- AI models or agents being used in cyber operations
- AI-assisted exploitation or vulnerability research
- Demonstrated AI-enabled attacks
- Security research showing meaningful autonomous or semi-autonomous hacking behaviour
- Major incidents where AI materially contributed to the cyber activity

Please avoid stories that are only about hypothetical future capabilities, ordinary AI security vulnerabilities with no meaningful hacking activity, or generic AI/cybersecurity news.

## Sources

Please prefer sources that are **free to read without a subscription or login**.

Good sources include:

- Security researchers' original reports
- Company threat-intelligence reports
- Government or academic publications
- Free-to-read reporting from reputable news organisations
- Public incident reports

A paywalled source can be included when it is the original or most authoritative source for a significant story, but **please provide a free-to-read source when one is reasonably available**.

Do not use search-result pages as the article URL.

## Date format

Dates **must use ISO 8601 calendar-date format**:

```text
YYYY-MM-DD
```

Example:

```text
2026-09-19
```

Use the publication date of the source article/report where possible.

If a source gives a more precise timestamp but the site only needs a calendar date, use the calendar date.

## Adding an article

Add an entry to `data.md` using this format:

```md
---

## Article headline

**Date:** 2026-09-19
**Source:** Example Security Research
**URL:** https://example.com/article
**AI role:** AI security research
**Category:** Security research

A short factual description of the incident or research.
```

### Ordering does not matter

You do **not** need to manually place an article between two dates.

For example, if the file contains:

```text
2026-09-19
2026-09-17
```

and your contribution is dated:

```text
2026-09-18
```

the GitHub Action sorts the generated data automatically:

```text
2026-09-19
2026-09-18
2026-09-17
```

The website therefore always displays the timeline chronologically, newest first.

## Keep descriptions factual

Descriptions should briefly explain what happened without exaggeration.

Prefer:

> Security researchers reported that an AI agent was used to identify and exploit vulnerabilities in a test environment.

Avoid:

> AI has gone completely rogue and can now hack anything.

When something is disputed, uncertain, or only alleged, make that clear in the description.

## Pull requests

Please submit contributions as a pull request rather than directly editing generated files.

A typical contribution is:

1. Fork the repository.
2. Create a branch.
3. Add or update the relevant entry in `data.md`.
4. Check that the date is `YYYY-MM-DD`.
5. Check that the URL works.
6. Prefer a free-to-read source.
7. Open a pull request.
8. A maintainer reviews the contribution.
9. Once merged, GitHub Actions regenerates `incidents.json`.

## Do not edit `incidents.json`

`incidents.json` is generated automatically.

Changes to it should normally not be included in a pull request. Edit `data.md` instead.

## Corrections and updates

If an existing entry contains an incorrect date, title, source, URL, or description, submit a pull request correcting `data.md`.

If a story has multiple credible reports, prefer the most authoritative and freely accessible source.

## Duplicate stories

Before submitting, check whether the same incident is already represented.

If multiple sources report the same underlying incident, generally keep one timeline entry rather than adding several entries for the same event. A correction or better source can be submitted as an edit to the existing entry.

## Generated files and automation

The workflow in `.github/workflows/update-site.yml`:

1. Runs when `data.md` changes.
2. Parses the Markdown.
3. Validates the required fields.
4. Sorts articles by date.
5. Generates `incidents.json`.
6. Commits the generated file back to the repository.

The site reads `incidents.json`, not `data.md`, when it is displayed.


### Archive

`Archive` is optional. Add a known Wayback Machine snapshot if you have one; otherwise the build workflow will attempt to create one automatically.
