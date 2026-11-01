"""Test temporaire (2) : événements de match ESPN et recherche du Maroc."""
import json
import urllib.request

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        return str(e)[:150]


def note(msg):
    print("::notice::" + msg.replace("\n", " ")[:950])


js = get("https://site.api.espn.com/apis/site/v2/leagues/dropdown?sport=soccer&limit=1000")
if isinstance(js, dict):
    lg = [(l.get("slug"), l.get("name")) for l in js.get("leagues", [])]
    note(f"ligues ESPN: {len(lg)} ; Maroc: {[x for x in lg if 'oroc' in (x[1] or '') or 'mar.' in (x[0] or '') or 'otola' in (x[1] or '')]}")
else:
    note(f"dropdown: {js}")

done = 0
for slug in ["ita.1", "esp.1", "fra.1", "bel.1", "esp.2", "ger.1"]:
    sb = get(f"{ESPN}/{slug}/scoreboard")
    if not isinstance(sb, dict):
        continue
    for ev in sb.get("events", []):
        c = ev["competitions"][0]
        if c["status"]["type"].get("state") == "pre":
            continue
        det = [(d.get("type", {}).get("text"), d.get("clock", {}).get("displayValue"), d.get("redCard"), d.get("scoringPlay"), (d.get("team") or {}).get("id")) for d in c.get("details", [])]
        note(f"{slug} {ev['name']} {c['status']['type'].get('state')} {c['status'].get('displayClock')} period={c['status'].get('period')} details={det[:8]}")
        sm = get(f"{ESPN}/{slug}/summary?event={ev['id']}")
        if isinstance(sm, dict):
            bs = (sm.get("boxscore", {}).get("teams") or [{}])[0]
            note(f"summary clés={list(sm.keys())[:22]}")
            note(f"summary stats={[(s.get('name'), s.get('displayValue')) for s in (bs.get('statistics') or [])][:22]}")
            ke = sm.get("keyEvents") or []
            note(f"keyEvents={len(ke)} {[(k.get('type', {}).get('text'), k.get('clock', {}).get('displayValue')) for k in ke[:8]]} odds={str(sm.get('odds'))[:200]}")
        done += 1
        break
    if done >= 2:
        break
