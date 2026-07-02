#!/usr/bin/env python3
"""
Fetches completed World Cup 2026 results from ESPN and updates:
  - Group stage MATCHES array
  - Knockout stage KNOCKOUT_MATCHES array (results + advancing team slots)
  - Bracket Challenge team inputs (m1t1…m8t2)
"""

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
    "Congo DR":                     "DR Congo",
    "DR Congo":                     "DR Congo",
    "Republic of Congo":            "DR Congo",
    "Cote d'Ivoire":                "Ivory Coast",
    "Côte d'Ivoire":                "Ivory Coast",
    "Ivory Coast":                  "Ivory Coast",
    "Cape Verde":                   "Cape Verde",
    "Cabo Verde":                   "Cape Verde",
    "UAE":                          "United Arab Emirates",
}

# When the winner of an R32 match is known, slot them into the R16 bracket.
# key = frozenset of the two teams; value = (r16_slot_id, 'home'|'away', bracket_input_id)
R32_TO_R16 = {
    frozenset(["Canada",        "South Africa"]):       ("r16-1", "home", "m2t1"),
    frozenset(["Morocco",       "Netherlands"]):        ("r16-1", "away", "m2t2"),
    frozenset(["Paraguay",      "Germany"]):            ("r16-2", "home", "m1t1"),
    frozenset(["France",        "Sweden"]):             ("r16-2", "away", "m1t2"),
    frozenset(["Brazil",        "Japan"]):              ("r16-3", "home", "m5t1"),
    frozenset(["Norway",        "Ivory Coast"]):        ("r16-3", "away", "m5t2"),
    frozenset(["Mexico",        "Ecuador"]):            ("r16-4", "home", "m6t1"),
    frozenset(["England",       "DR Congo"]):           ("r16-4", "away", "m6t2"),
    frozenset(["Spain",         "Austria"]):            ("r16-5", "home", "m3t1"),
    frozenset(["Croatia",       "Portugal"]):           ("r16-5", "away", "m3t2"),
    frozenset(["United States", "Bosnia-Herzegovina"]): ("r16-6", "home", "m4t1"),
    frozenset(["Belgium",       "Senegal"]):            ("r16-6", "away", "m4t2"),
    frozenset(["Argentina",     "Cape Verde"]):         ("r16-7", "home", "m7t1"),
    frozenset(["Egypt",         "Australia"]):          ("r16-7", "away", "m7t2"),
    frozenset(["Algeria",       "Switzerland"]):        ("r16-8", "home", "m8t1"),
    frozenset(["Colombia",      "Ghana"]):              ("r16-8", "away", "m8t2"),
}

# R16 winner → QF slot
R16_TO_QF = {
    frozenset(["Canada",        "Morocco"]):            ("qf-1", "home"),
    frozenset(["Paraguay",      "France"]):             ("qf-1", "away"),
    frozenset(["Brazil",        "Norway"]):             ("qf-2", "home"),
    frozenset(["Mexico",        "England"]):            ("qf-2", "away"),
    frozenset(["Spain",         "Croatia"]):            ("qf-3", "home"),
    frozenset(["United States", "Belgium"]):            ("qf-3", "away"),
    frozenset(["Argentina",     "Egypt"]):              ("qf-4", "home"),
    frozenset(["Algeria",       "Colombia"]):           ("qf-4", "away"),
}

# QF winner → SF slot
QF_TO_SF = {
    ("qf-1", "home"): ("sf-1", "home"),
    ("qf-1", "away"): ("sf-1", "home"),   # either winner goes to sf-1
    ("qf-2", "home"): ("sf-1", "away"),
    ("qf-2", "away"): ("sf-1", "away"),
    ("qf-3", "home"): ("sf-2", "home"),
    ("qf-3", "away"): ("sf-2", "home"),
    ("qf-4", "home"): ("sf-2", "away"),
    ("qf-4", "away"): ("sf-2", "away"),
}


def norm(name):
    return TEAM_MAP.get(name, name)


def fetch_events(date_str):
    url = (f"https://site.api.espn.com/apis/site/v2/sports/soccer"
           f"/fifa.world/scoreboard?dates={date_str}")
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json().get("events", [])
    except Exception as e:
        print(f"  Warning: could not fetch {date_str}: {e}")
        return []


def get_completed(events):
    """Return list of completed match dicts including winner for knockout matches."""
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
        hn = norm(home["team"]["displayName"])
        an = norm(away["team"]["displayName"])
        hs = int(home.get("score") or 0)
        as_ = int(away.get("score") or 0)
        # Determine winner (ESPN sets winner=True on the winning competitor)
        h_win = home.get("winner", False)
        a_win = away.get("winner", False)
        winner = hn if h_win else (an if a_win else (hn if hs > as_ else (an if as_ > hs else None)))
        results.append({"home": hn, "away": an, "hs": hs, "as_": as_, "winner": winner})
    return results


# ── GROUP STAGE PATCH ────────────────────────────────────────────────────────

def patch_group(html, home, away, hs, as_):
    """Update a group-stage MATCHES line with the final score."""
    lines = html.split("\n")
    out, changed = [], False
    for line in lines:
        if f'home:"{home}"' in line and f'away:"{away}"' in line and "group:" in line:
            if 'status:"ft"' in line:
                out.append(line); continue
            line = re.sub(r",\s*result:\{[^}]+\}", "", line)
            stripped = line.rstrip()
            if stripped.endswith("},"):
                line = stripped[:-2] + f', result:{{home:{hs},away:{as_},status:"ft"}} }},'
                changed = True
                print(f"  ✓ [group] {home} {hs}–{as_} {away}")
        out.append(line)
    return "\n".join(out), changed


# ── KNOCKOUT STAGE PATCH ─────────────────────────────────────────────────────

def patch_ko_result(html, home, away, hs, as_, winner):
    """Update a KNOCKOUT_MATCHES line with the final score."""
    lines = html.split("\n")
    out, changed = [], False
    for line in lines:
        if f'home:"{home}"' in line and f'away:"{away}"' in line and 'round:' in line:
            if 'status:"ft"' in line:
                out.append(line); continue
            line = re.sub(r",\s*result:\{[^}]+\}", "", line)
            stripped = line.rstrip()
            if stripped.endswith("},"):
                if winner and winner != (home if hs > as_ else away):
                    # decided on pens — store 90min score + winner flag
                    res = f'result:{{home:{hs},away:{as_},status:"ft",winner:"{winner}"}}'
                else:
                    res = f'result:{{home:{hs},away:{as_},status:"ft"}}'
                line = stripped[:-2] + f', {res} }},'
                changed = True
                print(f"  ✓ [KO]    {home} {hs}–{as_} {away}" +
                      (f" ({winner} on pens)" if winner and hs == as_ else ""))
        out.append(line)
    return "\n".join(out), changed


def set_ko_team(html, slot_id, side, team):
    """Fill a null team slot in KNOCKOUT_MATCHES with a confirmed team name."""
    pattern = rf'(\{{ id:"{slot_id}",[^}}]+?{side}:)null'
    new, count = re.subn(pattern, rf'\g<1>"{team}"', html)
    if count:
        print(f"  → [{slot_id}] {side} = {team}")
    return new, count > 0


def set_bracket_input(html, input_id, team):
    """Update a bracket challenge <input value="..."> with the confirmed team."""
    pattern = rf'(id="{input_id}"\s+value=")[^"]*(")'
    new, count = re.subn(pattern, rf'\g<1>{team}\g<2>', html)
    return new, count > 0


def advance_to_next_round(html, home, away, winner, mapping, changed_flag):
    """Given a winner, slot them into the next round using the provided mapping."""
    key = frozenset([home, away])
    if key not in mapping:
        return html, changed_flag
    entry = mapping[key]
    slot_id, side = entry[0], entry[1]
    bracket_input = entry[2] if len(entry) > 2 else None
    # Update KNOCKOUT_MATCHES slot
    html, c = set_ko_team(html, slot_id, side, winner)
    if c: changed_flag = True
    # Update bracket challenge input
    if bracket_input:
        html, c2 = set_bracket_input(html, bracket_input, winner)
        if c2: changed_flag = True
    return html, changed_flag


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    with open("index.html", encoding="utf-8") as f:
        html = f.read()

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
        home, away, hs, as_, winner = r["home"], r["away"], r["hs"], r["as_"], r["winner"]

        # 1. Group stage patch
        html, c = patch_group(html, home, away, hs, as_)
        if c: any_changed = True

        # 2. Knockout stage result patch
        html, c = patch_ko_result(html, home, away, hs, as_, winner)
        if c: any_changed = True

        if not winner:
            continue

        # 3. Advance winner to the next round slot
        # R32 → R16
        html, any_changed = advance_to_next_round(html, home, away, winner, R32_TO_R16, any_changed)
        # R16 → QF
        html, any_changed = advance_to_next_round(html, home, away, winner, R16_TO_QF, any_changed)
        # QF → SF (simple: winner of qf-1 or qf-2 → sf-1; qf-3 or qf-4 → sf-2)
        for (qf_slot, qf_side), (sf_slot, sf_side) in QF_TO_SF.items():
            # Check if this match is the QF in question
            # We do this by looking at the HTML for qf slot teams
            qf_pattern = rf'id:"{qf_slot}"[^}}]+?home:"([^"]+)"[^}}]+?away:"([^"]+)"'
            m = re.search(qf_pattern, html)
            if m:
                qt1, qt2 = m.group(1), m.group(2)
                if frozenset([home, away]) == frozenset([qt1, qt2]) and winner in (qt1, qt2):
                    html, c = set_ko_team(html, sf_slot, sf_side, winner)
                    if c: any_changed = True
                    break

    if any_changed:
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("index.html updated.")
        sys.exit(0)
    else:
        print("No new results to add.")
        sys.exit(1)


if __name__ == "__main__":
    main()
