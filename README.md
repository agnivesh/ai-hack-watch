# AI Hack Watch

A static single-page site tracking notable AI hacking and AI-enabled cyber incidents.

![Days since last AI hack](https://aihackwatch.com/days-since-badge.svg)

- **Live site:** https://aihackwatch.com
- **RSS:** https://aihackwatch.com/feed.xml
- **Dataset (JSON):** https://aihackwatch.com/incidents.json

## Features

- Large "days since" counter.
- Chronological public timeline.
- Structured metadata for AI role and incident category.
- Filters by AI role/category.
- Click any role or category label (filter bar, story tags, or breakdown) to show only matching incidents.
- Incident counts and longest observed streak.
- RSS feed generated automatically.
- GitHub Issue Form for non-technical story submissions.
- Pull request template and contribution guide.
- Automated PR validation.
- Automated pipeline tests (`scripts/test_pipeline.py`).
- GitHub Action that turns `data.md` into `incidents.json`, `feed.xml`, and a pre-rendered recent timeline.

## Data workflow

You edit **`data.md`**.

```text
data.md
   ↓
Pull request / merge
   ↓
GitHub Action
   ↓
incidents.json + feed.xml + index.html
   ↓
GitHub Pages
```

The generated files and the pre-rendered timeline should not normally be edited manually.

## Article format

```md
---

## Article headline

**Date:** 2026-09-19
**Source:** Example Security Research
**URL:** https://example.com/article
**AI role:** Autonomous
**Category:** Security research

Short factual description of the story.
```

### Required metadata

- `Date` — ISO 8601 calendar date: `YYYY-MM-DD`
- `Source`
- `URL`
- `AI role`
- `Category`

### Multiple sources

If a story has more than one authoritative source, add optional numbered fields so readers still have a working link if one publisher goes down:

```md
**Source:** Sysdig Threat Research Team
**URL:** https://www.sysdig.com/blog/jadepuffer-agentic-ransomware-for-automated-database-extortion
**Source 2:** Dark Reading
**URL 2:** https://www.darkreading.com/cyberattacks-data-breaches/jadepuffer-first-complete-llm-driven-ransomware-attack
```

All source URLs appear on the timeline; the first is the primary citation.

### AI roles

- `Autonomous`
- `AI-assisted`
- `AI-targeted`
- `AI security research`
- `Unclear`

### Ordering

Contributors do not need to insert an article in the right chronological position. The Action sorts generated data by date, newest first.

## Contributions

Read [`CONTRIBUTING.md`](CONTRIBUTING.md).

You can contribute in two ways:

1. Edit `data.md` in a pull request.
2. Use the **Submit a story** GitHub Issue Form.

The site links visitors to the issue form. The repository URL is set in `config.js`:

```js
window.SITE_CONFIG = {
  repositoryUrl: "https://github.com/agnivesh/ai-hack-watch",
  siteUrl: "https://aihackwatch.com"
};
```

## Methodology

Read [`METHODOLOGY.md`](METHODOLOGY.md) for what qualifies, AI-role definitions, source preferences, date rules, corrections, and calculation details.

## Development

Run the pipeline and its tests locally (skipping Wayback archiving, which would rewrite `data.md`):

```bash
python3 scripts/test_pipeline.py          # regression tests
python3 scripts/validate_contribution.py  # same checks as PR CI
python3 scripts/generate.py --no-archive  # regenerate incidents.json, badge, feed.xml
python3 scripts/prerender_timeline.py     # regenerate the in-page timeline + OG tags
python3 scripts/check_links.py            # HEAD-check source URLs
```

The pipeline lives in `scripts/` (`generate.py`, `validate_contribution.py`, `prerender_timeline.py`, `check_links.py`) and shares one parser/validator in `datamd.py`.

## GitHub Pages

The site is deployed to **https://aihackwatch.com** (replacing the default `https://agnivesh.github.io/ai-hack-watch/` URL). The `CNAME` file at the repo root declares the custom domain; DNS points the domain at GitHub Pages and HTTPS is provisioned automatically.

To deploy your own copy of the project:

1. Create a GitHub repository.
2. Upload the contents of this project.
3. Update `config.js` with your repository URL.
4. In **Settings → Pages**, choose **Deploy from a branch**.
5. Select the main branch and `/ (root)`.
6. Save.

## Actions permissions

The generation workflow commits `incidents.json`, `feed.xml`, and the pre-rendered timeline in `index.html` back to the repository.

In **Settings → Actions → General**, make sure workflow permissions allow repository contents to be written. The workflow also declares:

```yaml
permissions:
  contents: write
```

## RSS

`feed.xml` is regenerated whenever `data.md` changes.

## Search visibility

The generation workflow embeds the 20 most recent incidents directly in `index.html`. Search engines can read these stories without executing JavaScript, while visitors still receive the complete filterable timeline from `incidents.json`.

## Validation

Pull requests run `.github/workflows/validate-contribution.yml`, which checks:

- Required metadata.
- ISO date format.
- Future dates.
- Valid HTTP(S) URLs.
- Valid `AI role` values.
- Archive URL format (when provided).
- Duplicate URLs.

Pull requests and pushes also run `.github/workflows/test.yml`, which executes the regression suite in `scripts/test_pipeline.py`. The validation workflow is intentionally conservative; maintainers still review factual relevance and source quality.

## Embeddable badge

```md
![Days since last AI hack](https://aihackwatch.com/days-since-badge.svg)
```

The badge is regenerated daily (and on every data change). Opened directly in a browser, it also updates itself live from the latest tracked date.

## Machine-readable feeds

- `incidents.json` — public JSON dataset. Contains `schema_version`, `chunk_size`, `total`, and `incidents` array. See [Schema versioning](#schema-versioning).
- `feed.xml` — RSS feed.

### Schema versioning

`incidents.json` includes a `schema_version` field (currently `1`) to allow future format evolution without breaking consumers. The `chunk_size` field (currently `20`) hints at a future pagination strategy if the dataset grows large.

**Dataset size guideline:** `incidents.json` should remain under **250 KB** (~1,500 incidents) to keep initial load fast on mobile. At the current rate (~20 incidents/year), this provides decades of headroom. If the dataset approaches this limit, maintainers should implement chunked pagination using the `chunk_size` hint.

## Broken links

A weekly workflow checks source URLs and opens or updates a GitHub issue when a link appears unavailable. Automated link checks can produce false positives when publishers block bots, so the issue is for human review rather than automatic deletion.

## Permalinks and sharing

Each incident has a slug-based `#anchor` so individual stories can be shared directly. The page also updates its title and Open Graph description based on the latest incident.


## Automatic link archiving

When an incident has no `Archive` value, the GitHub Action attempts to submit its source URLs to the Wayback Machine, stopping at the first successful snapshot. Existing archive URLs are preserved. The timeline displays an **Archived copy ↗** link when a snapshot is available.

Archiving is best-effort and never blocks a valid contribution.
