"""Validate data.md on pull requests (CI entry point).

Runs the same checks as scripts/generate.py, so a contribution that
passes review can never break the site build. Exits 1 on any error.

Usage:
    python3 scripts/validate_contribution.py
"""

import sys
from pathlib import Path

import datamd

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data.md"


def main() -> int:
    if not DATA_PATH.is_file():
        print(f"ERROR: {DATA_PATH} not found")
        return 1
    entries = datamd.parse_blocks(DATA_PATH.read_text(encoding="utf-8"))
    errors, warnings = datamd.validate_entries(entries)
    for warning in warnings:
        print("WARNING: " + warning)
    for error in errors:
        print("ERROR: " + error)
    complete = [
        entry
        for entry in entries
        if all(entry.get(field) for field in datamd.REQUIRED_FIELDS)
    ]
    if errors:
        print(f"Validated {len(complete)} incident(s); {len(errors)} error(s).")
        return 1
    print(f"Validated {len(complete)} incident(s); {len(warnings)} warning(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())