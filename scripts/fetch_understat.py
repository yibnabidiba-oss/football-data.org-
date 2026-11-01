"""Télécharge les statistiques avancées depuis understat.com (gratuit, sans clé).

Pour chaque championnat et saison :
  - équipes : historique match par match (xG, xGA, npxG, PPDA, passes dans les 20 derniers mètres)
  - joueurs : stats de la saison (minutes, buts, xG, passes décisives, xA, tirs, passes clés,
    xGChain, xGBuildup, cartons, poste)
  - matchs : identifiants, dates, scores, xG
Pour la saison en cours, on récupère aussi la composition des derniers matchs de chaque équipe,
ce qui permet de repérer les joueurs importants absents.

Fichiers : data/understat/<CODE>_<année>.json et data/understat/<CODE>_rosters.json
"""
from __future__ import annotations

import codecs
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from leagues import LEAGUES

BASE = "https://understat.com"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "understat"
SEASONS_BACK = 3
ROSTER_MATCHES = 6  # derniers matchs de chaque équipe dont on lit la composition
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip",
}


def get(url: str, xhr: bool = False, referer: str | None = None) -> bytes | None:
    h = dict(HEADERS)
    if xhr:
        h["X-Requested-With"] = "XMLHttpRequest"
    if referer:
        h["Referer"] = referer
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or data[:2] == b"\x1f\x8b":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as e:
            print(f"  {url} -> HTTP {e.code}")
            if e.code in (403, 404):
                return None
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  {url} -> {e}")
        time.sleep(3 * (attempt + 1))
    return None


def parse_embedded(html: str) -> dict:
    """Ancien format : données dans la page, sous forme var x = JSON.parse('...')."""
    out = {}
    for name, raw in re.findall(r"var\s+(\w+)\s*=\s*JSON\.parse\('(.*?)'\)", html, re.S):
        try:
            out[name] = json.loads(codecs.decode(raw, "unicode_escape"))
        except (ValueError, UnicodeDecodeError):
            pass
    return out


def league_data(league: str, year: int) -> dict | None:
    page = f"{BASE}/league/{league}/{year}"
    data = get(f"{BASE}/getLeagueData/{league}/{year}", xhr=True, referer=page)
    if data:
        try:
            js = json.loads(data)
            if isinstance(js, dict) and js:
                return {"teams": js.get("teams"), "players": js.get("players"),
                        "dates": js.get("dates"), "source": "api"}
        except ValueError:
            pass
    html = get(page)
    if html:
        emb = parse_embedded(html.decode("utf-8", "replace"))
        if emb:
            return {"teams": emb.get("teamsData"), "players": emb.get("playersData"),
                    "dates": emb.get("datesData"), "source": "page"}
    return None


def match_rosters(match_id: str) -> dict | None:
    page = f"{BASE}/match/{match_id}"
    data = get(f"{BASE}/getMatchData/{match_id}", xhr=True, referer=page)
    if data:
        try:
            js = json.loads(data)
            if js.get("rosters"):
                return js["rosters"]
        except ValueError:
            pass
    html = get(page)
    if html:
        emb = parse_embedded(html.decode("utf-8", "replace"))
        return emb.get("rostersData")
    return None


def season_year(now: datetime) -> int:
    return now.year if now.month >= 7 else now.year - 1


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    current = season_year(datetime.now(timezone.utc))
    ok = 0
    for code, info in LEAGUES.items():
        league = info["understat"]
        cur_data = None
        for year in range(current - SEASONS_BACK, current + 1):
            path = OUT / f"{code}_{year}.json"
            if path.exists() and year < current:
                continue
            d = league_data(league, year)
            time.sleep(2)
            if not d or not d.get("teams"):
                print(f"{code} {year}: indisponible")
                continue
            path.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
            ok += 1
            n_players = len(d.get("players") or [])
            print(f"{code} {year}: {len(d['teams'])} équipes, {n_players} joueurs ({d['source']})")
            if year == current:
                cur_data = d
        if not cur_data:
            continue
        # compositions des derniers matchs de chaque équipe (saison en cours)
        dates = [m for m in (cur_data.get("dates") or []) if m.get("isResult")]
        dates.sort(key=lambda m: m.get("datetime", ""))
        wanted, per_team = [], {}
        for m in reversed(dates):
            tids = (m["h"]["id"], m["a"]["id"])
            if any(per_team.get(t, 0) < ROSTER_MATCHES for t in tids):
                wanted.append(m)
                for t in tids:
                    per_team[t] = per_team.get(t, 0) + 1
        rpath = OUT / f"{code}_rosters.json"
        try:
            rosters = json.loads(rpath.read_text())
        except (OSError, ValueError):
            rosters = {}
        fetched = 0
        for m in wanted:
            mid = str(m["id"])
            if mid in rosters:
                continue
            r = match_rosters(mid)
            time.sleep(1.5)
            if r:
                rosters[mid] = {"date": m.get("datetime"), "h": m["h"]["id"], "a": m["a"]["id"], "rosters": r}
                fetched += 1
        keep = {str(m["id"]) for m in wanted}
        rosters = {k: v for k, v in rosters.items() if k in keep}
        rpath.write_text(json.dumps(rosters, ensure_ascii=False, separators=(",", ":")))
        print(f"{code} compositions : {len(rosters)} matchs ({fetched} nouveaux)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
