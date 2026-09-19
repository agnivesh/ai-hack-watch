"""Check incident source URLs (weekly CI entry point).

Uses HEAD requests (falling back to GET when a server refuses HEAD) and
writes unreachable / 4xx-5xx results to /tmp/failures.txt, which the
workflow turns into a GitHub issue for human review.

Best-effort only: sites that block bots will appear unreachable, which
is why the issue is reviewed by a person rather than auto-applied.

Usage:
    python3 scripts/check_links.py
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURES_PATH = Path("/tmp/failures.txt")
USER_AGENT = "ai-hack-watch-link-checker/1.0"
TIMEOUT = 15


def check_url(url):
    """Return a failure status for url, or None when it looks reachable."""
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(
            url, method=method, headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                if response.status >= 400:
                    return response.status
                return None
        except urllib.error.HTTPError as error:
            if method == "HEAD":
                continue  # bots often get 4xx on HEAD; retry with GET
            return error.code
        except Exception:
            if method == "GET":
                return "unreachable"
    return "unreachable"


def main() -> int:
    incidents = json.loads((ROOT / "incidents.json").read_text(encoding="utf-8"))
    failures = []
    for incident in incidents:
        status = check_url(incident["url"])
        if status is not None:
            failures.append((status, incident["title"], incident["url"]))
    FAILURES_PATH.write_text(
        "\n".join(f"{status} | {title} | {url}" for status, title, url in failures),
        encoding="utf-8",
    )
    print(f"Checked {len(incidents)} links; {len(failures)} failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())