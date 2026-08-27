#!/usr/bin/env python3
"""
Daily refresh script for the Adobe Experience Cloud Release Tracker dashboard.
Fetches release notes for 12 Adobe products via HTTP, passes them to Claude,
and updates RELEASE_DATA + DASHBOARD_DATE in adobe_release_dashboard.html.

Runs via macOS launchd (daily, weekdays) or GitHub Actions.
Requires: ANTHROPIC_API_KEY environment variable.
"""

import os
import re
import subprocess
import sys
from datetime import date

import anthropic
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

PRODUCTS = [
    ("analytics",           "https://experienceleague.adobe.com/en/docs/analytics/release-notes/latest",                                                                                   ""),
    ("experience-platform", "https://experienceleague.adobe.com/en/docs/experience-platform/release-notes/latest",                                                                         ""),
    ("target",              "https://experienceleague.adobe.com/en/docs/target/using/release-notes/release-notes",                                                                         ""),
    ("journey-analytics",   "https://experienceleague.adobe.com/en/docs/analytics-platform/using/releases/latest",                                                                         ""),
    ("marketo",             "https://experienceleague.adobe.com/en/docs/marketo/using/release-notes/current",                                                                              ""),
    ("campaign",            "https://experienceleague.adobe.com/en/docs/campaign/campaign-v8/releases/release-notes",                                                                      ""),
    ("journey-optimizer",   "https://experienceleague.adobe.com/en/docs/journey-optimizer/using/whats-new/release-notes",                                                                  ""),
    ("aem",                 "https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/content/release-notes/release-notes/release-notes-current",                       ""),
    ("workfront",           "https://experienceleague.adobe.com/en/docs/workfront/using/product-announcements/product-releases/product-releases",                                          ""),
    ("ajo-b2b",             "https://experienceleague.adobe.com/en/docs/journey-optimizer-b2b/user/release-notes",                                                                         ""),
    ("rtcdp",               "https://experienceleague.adobe.com/en/docs/experience-platform/release-notes/latest",                                                                         " (focus only on Real-Time CDP section)"),
    ("data-distiller",      "https://experienceleague.adobe.com/en/docs/experience-platform/query/home",                                                                                   " (focus only on Data Distiller/Query Service sections; check last 6 months if current month has no content)"),
]

HTML_FILE = "adobe_release_dashboard.html"
MAX_PAGE_CHARS = 20_000  # chars per product page sent to Claude
REPO_DIR = os.path.dirname(os.path.abspath(__file__))


def fetch_page(product_id: str, url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.text[:MAX_PAGE_CHARS]
    except Exception as exc:
        print(f"  WARN: failed to fetch {product_id}: {exc}")
        return None


def main() -> int:
    today = date.today().isoformat()
    print(f"Dashboard refresh — {today}")

    # Read current HTML
    with open(HTML_FILE, encoding="utf-8") as fh:
        html = fh.read()

    data_match = re.search(r"(const RELEASE_DATA = \[.*?\];)", html, re.DOTALL)
    current_block = data_match.group(1) if data_match else "(not found)"

    # Fetch all release note pages
    print("Fetching release note pages...")
    pages_section = ""
    for product_id, url, focus in PRODUCTS:
        print(f"  {product_id}...")
        content = fetch_page(product_id, url)
        pages_section += f"\n\n=== {product_id}{focus} ===\nURL: {url}\n"
        pages_section += content if content else "[FETCH FAILED — keep existing entry unchanged]"

    # Call Claude to produce the updated RELEASE_DATA
    prompt = f"""You are updating an Adobe Experience Cloud Release Tracker dashboard.

Today: {today}

EXISTING RELEASE_DATA (currently in the file):
{current_block}

FRESHLY FETCHED RELEASE NOTES (raw HTML, truncated to {MAX_PAGE_CHARS} chars each):
{pages_section}

TASK:
Compare each freshly fetched page against the existing entry for that product.
- If the page shows a newer release or features not yet listed, update that product's entry fully.
- If a page shows "[FETCH FAILED]", keep the existing entry for that product exactly as-is.
- If the fetched page content matches the release already in RELEASE_DATA, keep the existing entry (it may already be more complete than what was fetched).

For each product entry include:
  id           : (product id string, unchanged)
  title        : Short headline, max 12 words
  version      : Version string or null
  date         : "Month YYYY" e.g. "August 2026"
  rawDate      : "YYYY-MM-01"
  summary      : 2-3 sentence plain-English summary of most impactful changes
  features     : Array of EVERY feature/fix/enhancement listed — no maximum limit.
                 Each item: {{ name: "...", description: "One sentence.", status: "GA" | "Beta" | "Limited Availability" }}
  category_tags: Subset of ["AI", "Performance", "UI", "Data", "Integration", "Security", "Deprecation"]

OUTPUT: Return ONLY the raw JavaScript block — no markdown fences, no explanation, nothing else:
const RELEASE_DATA = [
  {{ ... }},
  ...
];

Rules:
- status must be exactly "GA", "Beta", or "Limited Availability"
- category_tags must only use values from the allowed list
- rawDate must always be "YYYY-MM-01" format
- Sort all entries by rawDate descending (newest first)
- All 12 products must be present — do not omit any
"""

    print("Calling Claude API to generate updated RELEASE_DATA...")
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=32768,
        messages=[{"role": "user", "content": prompt}],
    )
    new_block = response.content[0].text.strip()

    # Strip accidental markdown fences if Claude added them
    new_block = re.sub(r"^```(?:javascript|js)?\n?", "", new_block)
    new_block = re.sub(r"\n?```$", "", new_block).strip()

    if not new_block.startswith("const RELEASE_DATA = ["):
        print("ERROR: Claude response does not start with expected token. Aborting.")
        print(new_block[:500])
        return 1

    # Patch the HTML file
    new_html = re.sub(
        r"const RELEASE_DATA = \[.*?\];",
        new_block,
        html,
        flags=re.DOTALL,
    )
    new_html = re.sub(
        r"const DASHBOARD_DATE = '[^']*';",
        f"const DASHBOARD_DATE = '{today}';",
        new_html,
    )

    with open(HTML_FILE, "w", encoding="utf-8") as fh:
        fh.write(new_html)

    print(f"Done — dashboard date set to {today}")

    # Commit and push
    print("Committing and pushing to GitHub...")
    subprocess.run(["git", "add", HTML_FILE], cwd=REPO_DIR, check=True)
    staged = subprocess.run(
        ["git", "diff", "--staged", "--quiet"], cwd=REPO_DIR
    )
    if staged.returncode == 0:
        print("No changes to commit — dashboard already up to date.")
    else:
        subprocess.run(
            ["git", "commit", "-m", f"chore: refresh release notes {today}"],
            cwd=REPO_DIR,
            check=True,
        )
        subprocess.run(["git", "push", "origin", "main"], cwd=REPO_DIR, check=True)
        print("Pushed to GitHub.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
