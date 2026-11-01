"""Récupère matchs et classements depuis football-data.org (API v4, offre gratuite).

Usage : FOOTBALL_DATA_API_KEY=xxxx python scripts/fetch_data.py
Écrit les réponses brutes dans data/raw/<CODE>_<saison>.json (conservées dans le dépôt,
ce qui constitue l'historique d'une saison à l'autre).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from leagues import LEAGUES

API = "https://api.football-data.org/v4"
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PAUSE = 7  # l'offre gratuite autorise 10 appels/minute


def get(path: str, key: str):
    req = urllib.request.Request(API + path, headers={"X-Auth-Token": key})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:  # trop d'appels : on attend puis on réessaie
                time.sleep(65)
                continue
            if e.code in (403, 404):  # saison non couverte par l'offre gratuite
                return None
            raise
        except urllib.error.URLError:
            time.sleep(10)
    raise RuntimeError(f"Échec de l'appel {path}")


def current_season_year(now: datetime) -> int:
    """Les championnats européens démarrent en août : saison 2026 = 2026-27."""
    return now.year if now.month >= 7 else now.year - 1


def main() -> int:
    key = os.environ.get("FOOTBALL_DATA_API_KEY", "").strip()
    if not key:
        print("FOOTBALL_DATA_API_KEY manquant", file=sys.stderr)
        return 1
    RAW.mkdir(parents=True, exist_ok=True)
    season = current_season_year(datetime.now(timezone.utc))

    for code in LEAGUES:
        # Saison en cours : toujours rafraîchie
        matches = get(f"/competitions/{code}/matches?season={season}", key)
        time.sleep(PAUSE)
        standings = get(f"/competitions/{code}/standings?season={season}", key)
        time.sleep(PAUSE)
        if matches is None:
            print(f"{code} {season} : non disponible", file=sys.stderr)
            continue
        out = {"code": code, "season": season,
               "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "matches": matches.get("matches", []),
               "standings": (standings or {}).get("standings", [])}
        (RAW / f"{code}_{season}.json").write_text(json.dumps(out, ensure_ascii=False))
        print(f"{code} {season} : {len(out['matches'])} matchs")

        # Saison précédente : récupérée une seule fois si l'offre le permet
        prev = RAW / f"{code}_{season - 1}.json"
        if not prev.exists():
            pm = get(f"/competitions/{code}/matches?season={season - 1}", key)
            time.sleep(PAUSE)
            if pm:
                prev.write_text(json.dumps({"code": code, "season": season - 1,
                                            "matches": pm.get("matches", []),
                                            "standings": []}, ensure_ascii=False))
                print(f"{code} {season - 1} : {len(pm.get('matches', []))} matchs (historique)")
            else:
                print(f"{code} {season - 1} : historique non disponible sur cette offre")
    return 0


if __name__ == "__main__":
    sys.exit(main())
