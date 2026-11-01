"""Test temporaire : vérifie la source de scores en direct (ESPN) et l'accès navigateur (CORS).
Les résultats sortent en annotations GitHub (::notice::)."""
import json
import os
import urllib.request

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
ORIGIN = "https://yibnabidiba-oss.github.io"


def get(url, headers=None):
    h = {"User-Agent": "Mozilla/5.0", "Origin": ORIGIN}
    h.update(headers or {})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
            return r.status, dict(r.headers), json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        return getattr(e, "code", "ERR"), dict(getattr(e, "headers", {}) or {}), str(e)[:200]


def note(msg):
    print("::notice::" + msg.replace("\n", " ")[:950])


sample = None
for slug in ["eng.1", "esp.1", "fra.1", "ger.1", "ita.1", "bel.1", "mar.1", "eng.2", "esp.2", "fra.2", "ita.2", "ger.2", "eng.3", "eng.4", "eng.5"]:
    st, hd, js = get(f"{ESPN}/{slug}/scoreboard")
    if not isinstance(js, dict):
        note(f"{slug}: HTTP {st} {js}")
        continue
    ev = js.get("events") or []
    acao = hd.get("Access-Control-Allow-Origin") or hd.get("access-control-allow-origin")
    lg = (js.get("leagues") or [{}])[0].get("name")
    first = ""
    if ev:
        c = ev[0]["competitions"][0]
        names = [s.get("name") for s in (c["competitors"][0].get("statistics") or [])]
        first = f"{ev[0].get('name')} {c['status']['type'].get('state')} {c['status'].get('displayClock')} stats={names[:12]}"
        if sample is None or c["status"]["type"].get("state") in ("in", "post"):
            sample = (slug, ev[0]["id"])
    note(f"{slug} ({lg}): HTTP {st}, CORS={acao}, {len(ev)} matchs. {first}")

if sample:
    slug, eid = sample
    st, hd, js = get(f"{ESPN}/{slug}/summary?event={eid}")
    if isinstance(js, dict):
        bs = js.get("boxscore", {}).get("teams") or [{}]
        stats = [s.get("name") for s in bs[0].get("statistics") or []]
        ke = js.get("keyEvents") or []
        note(f"summary {slug}/{eid}: clés={list(js.keys())[:20]}")
        note(f"summary stats={stats[:25]} keyEvents={len(ke)} ex={[(k.get('type', {}).get('text'), k.get('clock', {}).get('displayValue')) for k in ke[:4]]}")
        note(f"summary odds={str(js.get('odds') or js.get('pickcenter'))[:300]}")
        note(f"summary rosters={len(js.get('rosters') or [])} commentary={len(js.get('commentary') or [])} winprob={len(js.get('winprobability') or [])}")

key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
if key:
    st, hd, js = get("https://api.football-data.org/v4/matches", {"X-Auth-Token": key})
    acao = hd.get("Access-Control-Allow-Origin") or hd.get("access-control-allow-origin")
    n = len(js.get("matches", [])) if isinstance(js, dict) else js
    note(f"football-data.org /matches: HTTP {st}, CORS={acao}, {n}")
