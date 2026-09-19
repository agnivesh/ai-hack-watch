# AI Hack Watch

A static single-page site tracking notable AI hacking and AI-enabled cyber incidents.

## Features

- Large "days since" counter.
- Chronological public timeline.
- Structured metadata for AI role and incident category.
- Filters by AI role/category.
- Incident counts and longest observed streak.
- Historical gaps-between-incidents chart.
- RSS feed generated automatically.
- GitHub Issue Form for non-technical story submissions.
- Pull request template and contribution guide.
- Automated PR validation.
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

The site links visitors to the issue form. Set the repository URL in `config.js` after creating your repository:

```js
window.SITE_CONFIG = {
  repositoryUrl: "https://github.com/YOUR-USERNAME/ai-hack-watch"
};
```

## Methodology

Read [`METHODOLOGY.md`](METHODOLOGY.md) for what qualifies, AI-role definitions, source preferences, date rules, corrections, and calculation details.

## GitHub Pages

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
- Duplicate URLs.

The validation workflow is intentionally conservative; maintainers still review factual relevance and source quality.

## Embeddable badge

```md
![Days since last AI hack](https://YOUR-USERNAME.github.io/ai-hack-watch/days-since-badge.svg)
```

## Machine-readable feeds

- `incidents.json` — public JSON dataset.
- `feed.xml` — RSS feed.

## Broken links

A weekly workflow checks source URLs and opens or updates a GitHub issue when a link appears unavailable. Automated link checks can produce false positives when publishers block bots, so the issue is for human review rather than automatic deletion.

## Permalinks and sharing

Each incident has a slug-based `#anchor` so individual stories can be shared directly. The page also updates its title and Open Graph description based on the latest incident.


## Automatic link archiving

When an incident has no `Archive` value, the GitHub Action attempts to submit its source URL to the Wayback Machine. Existing archive URLs are preserved. The timeline displays an **Archived copy ↗** link when a snapshot is available.

Archiving is best-effort and never blocks a valid contribution.
