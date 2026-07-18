#!/usr/bin/env python3
"""
Fetches latest WC 2026 injury news via ESPN and uses Claude to update
the INJURIES array in index.html.
Requires: ANTHROPIC_API_KEY environment variable.
"""

import os
import re
import sys
import requests
import anthropic
from datetime import date

# ── helpers ──────────────────────────────────────────────────────────────────

def fetch_espn_news():
    """Pull the latest FIFA World Cup news headlines from ESPN."""
    url = ("https://site.api.espn.com/apis/site/v2/sports/soccer"
           "/fifa.world/news?limit=60")
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        articles = r.json().get("articles", [])
        # Keep only injury/fitness-related articles
        keywords = ("injur", "ruled out", "doubt", "fitness", "miss",
                    "absent", "return", "surgery", "recovery", "unavailable",
                    "squad", "withdrawn", "replace")
        relevant = [
            f"• {a.get('headline','')}: {a.get('description','')}"
            for a in articles
            if any(kw in (a.get("headline","") + a.get("description","")).lower()
                   for kw in keywords)
        ]
        return "\n".join(relevant[:25])
    except Exception as e:
        print(f"ESPN news fetch failed: {e}")
        return ""


def extract_current_injuries(html):
    """Pull the existing INJURIES JS array out of index.html."""
    m = re.search(r"(const INJURIES\s*=\s*\[[\s\S]*?\];)", html)
    return m.group(1) if m else ""


def ask_claude(current_injuries, news, today_str):
    """Call Claude Haiku to produce an updated INJURIES array."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    system = (
        "You are a football data assistant updating a FIFA World Cup 2026 "
        "fan page. Output only valid JavaScript — no markdown, no explanation."
    )

    user = f"""Today is {today_str}.

CURRENT INJURIES ARRAY (in the page right now):
{current_injuries}

LATEST ESPN NEWS (injury/fitness related):
{news if news else "(no new articles available)"}

Task: Return an updated version of the INJURIES array that reflects the latest news.
- Keep existing players unless news confirms they have recovered and are fully fit
- Add newly injured or ruled-out players mentioned in the news
- Update status from "race"/"doubt" to "out" if news confirms absence
- Update status from "out"/"race" to appropriate level if news shows recovery
- Keep the array to the 12–16 most significant players
- Use the exact same JavaScript object format as the current array
- Update details text to reflect the latest known information

Output ONLY the replacement JavaScript block, starting with:
const INJURIES = [
and ending with
];"""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2500,
        messages=[{"role": "user", "content": user}],
        system=system,
    )
    return msg.content[0].text.strip()


def patch_html(html, new_injuries_js, today_label):
    """Replace the INJURIES array and update the date badge."""
    # Replace INJURIES array
    html = re.sub(
        r"const INJURIES\s*=\s*\[[\s\S]*?\];",
        new_injuries_js,
        html,
    )
    # Update "Updated MMM DD" badge on the injuries page
    html = re.sub(
        r'(Updated )\w+ \d+(?=</span>)',
        f"\\g<1>{today_label}",
        html,
    )
    return html


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("Error: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    today      = date.today()
    today_str  = today.strftime("%B %d, %Y")   # "June 22, 2026"
    today_lbl  = today.strftime("%b %d")        # "Jun 22"

    print(f"Updating injuries for {today_str}…")

    with open("index.html", encoding="utf-8") as f:
        html = f.read()

    # World Cup is over once the Final has a result — no more injury updates
    if re.search(r'id:"final"[^}]*status:"ft"', html):
        print("Tournament complete — skipping injury update.")
        sys.exit(1)

    current = extract_current_injuries(html)
    if not current:
        print("Could not find INJURIES array in index.html. Aborting.")
        sys.exit(1)

    news = fetch_espn_news()
    print(f"Fetched {len(news.splitlines())} relevant news items.")

    updated_js = ask_claude(current, news, today_str)

    if not updated_js.startswith("const INJURIES"):
        print("Claude output did not start with 'const INJURIES'. Aborting.")
        print("Output was:", updated_js[:200])
        sys.exit(1)

    new_html = patch_html(html, updated_js, today_lbl)

    if new_html == html:
        print("No changes detected.")
        sys.exit(1)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(new_html)

    print("index.html injuries section updated.")
    sys.exit(0)


if __name__ == "__main__":
    main()
