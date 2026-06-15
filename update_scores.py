#!/usr/bin/env python3
"""Fetches completed World Cup 2026 results from ESPN and updates index.html."""

import re
import sys
import requests
from datetime import date, timedelta

TEAM_MAP = {
    "South Korea":                  "Korea Republic",
    "Czech Republic":               "Czechia",
    "Bosnia and Herzegovina":       "Bosnia-Herzegovina",
    "Bosnia-Herzegowina":           "Bosnia-Herzegovina",
    "Turkey":                       "Türkiye",
    "Curacao":                      "Curaçao",
    "Congo":                        "DR Congo",
    "Democratic Republic of Congo": "DR Congo",
    "Cote d'Ivoire":                "Ivory Coast",
    "Côte d'Ivoire":                "Ivory Coast",
    "UAE":                          "United Arab Emirates",
}

def norm(name):
    return TEAM_MAP.get(name, name)

def fetch_events(date_str):
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date_str}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json().get("events", [])
    except Exception as e:
        print(f"  Warning: could not fetch {date_str}: {e}")
        return []

def get_completed(events):
    results = []
    for ev in events:
        state = ev.get("status", {}).get("type", {}).get("state")
        if state != "post":
            continue
        comp = (ev.get("competitions") or [{}])[0]
        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        results.append({
            "home": norm(home["team"]["displayName"]),
            "away": norm(away["team"]["displayName"]),
            "hs":   int(home.get("score") or 0),
            "as_":  int(away.get("score") or 0),
        })
    return results

def patch_html(html, home, away, hs, as_):
    lines = html.split("\n")
    out = []
    changed = False
    for line in lines:
        is_match = (
            f'home:"{home}"' in line and f'away:"{away}"' in line and "group:" in line
        )
        if is_match:
            if 'status:"ft"' in line:
                out.append(line)
                continue
            # Strip any existing non-final result
            line = re.sub(r",\s*result:\{[^}]+\}", "", line)
            stripped = line.rstrip()
            if stripped.endswith("},"):
                line = stripped[:-2] + f', result:{{home:{hs},away:{as_},status:"ft"}} }},'
                changed = True
                print(f"  ✓ {home} {hs}–{as_} {away}")
        out.append(line)
    return "\n".join(out), changed

def main():
    with open("index.html", encoding="utf-8") as f:
        html = f.read()

    # Fetch all dates from WC start through today
    start = date(2026, 6, 11)
    today = date.today()
    all_results = []
    d = start
    while d <= today:
        ds = d.strftime("%Y%m%d")
        print(f"Fetching {ds}...")
        all_results.extend(get_completed(fetch_events(ds)))
        d += timedelta(days=1)

    print(f"Found {len(all_results)} completed match(es).")

    any_changed = False
    for r in all_results:
        html, changed = patch_html(html, r["home"], r["away"], r["hs"], r["as_"])
        if changed:
            any_changed = True

    if any_changed:
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("index.html updated.")
        sys.exit(0)
    else:
        print("No new results to add.")
        sys.exit(1)  # exit 1 = no changes (used by git to skip empty commit)

if __name__ == "__main__":
    main()
