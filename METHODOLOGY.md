# Methodology

## Purpose

**AI Hack Watch** is a community-maintained record of publicly reported events where AI materially participated in hacking, cyber operations, exploitation, or meaningful security research.

The project is intended as a transparent historical dataset, not a prediction engine.

## What counts?

An entry should involve a material role for AI. Examples include:

- An AI model or agent autonomously performing cyber actions.
- Humans using AI materially to conduct an attack or exploitation.
- AI-assisted vulnerability discovery or exploitation research with concrete results.
- AI being used for reconnaissance, credential access, malware development, lateral movement, or related cyber activity.
- Security research that demonstrates a meaningful AI-enabled hacking capability.

## What does not count?

Generally exclude:

- Purely hypothetical future scenarios.
- Marketing claims without evidence.
- Generic AI security news where no hacking/cyber operation is demonstrated.
- Ordinary software vulnerabilities in an AI product where AI did not materially participate in the activity.
- Stories that only speculate that AI *could* be used for hacking.

## AI role

Use one of these values:

- **Autonomous** — the AI performed substantial cyber actions with limited human intervention.
- **AI-assisted** — a human materially directed the activity while using AI.
- **AI-targeted** — the incident primarily involved attacking or compromising an AI system.
- **AI security research** — controlled research demonstrating an AI-related cyber capability.
- **Unclear** — the source establishes AI involvement but the precise role cannot be confidently classified.

These labels describe the reported role; they are not severity ratings.

## Categories

Categories are descriptive and may include:

- Security research
- Vulnerability research
- Cyber operations
- Malware
- Credential theft
- Cloud infrastructure
- AI model compromise
- Other

## Dates

Dates use ISO 8601 calendar format:

`YYYY-MM-DD`

Use the publication date of the cited source/report where possible.

The website sorts entries by date automatically. Contributors do not need to manually position an entry between other dates.

## Sources

Prefer sources that are free to read without a subscription or login.

Priority should generally be given to:

1. Original security research or incident reports.
2. Government, academic, or company threat-intelligence reports.
3. Reputable free-to-read journalism.

A paywalled source may be used when it is the most authoritative available source, but contributors should look for a credible free-to-read source covering the same event.

## Corrections

If a source is later corrected or a material fact changes, submit a pull request updating the existing entry.

The project should preserve a clear factual distinction between what a source reports, what researchers demonstrated, and what remains uncertain.

## Frequency and streak calculations

The main counter is the number of whole calendar days since the newest tracked article date.

All day counts use **UTC calendar dates**, so the displayed number is the same for every visitor regardless of local time zone.

The longest streak is simply the largest observed gap in the dataset. It is not a prediction about future activity.
