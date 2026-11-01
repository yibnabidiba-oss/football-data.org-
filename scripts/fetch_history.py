"""Télécharge l'historique des matchs depuis football-data.co.uk (gratuit, sans clé).

Pour chaque championnat et chaque saison : résultat, score à la mi-temps, tirs, tirs cadrés,
corners, fautes, cartons et cotes moyennes des bookmakers. Plus le fichier des prochains matchs
avec leurs cotes.

Les saisons terminées ne sont téléchargées qu'une fois ; la saison en cours et les prochains
matchs sont rafraîchis à chaque lancement. Fichiers : data/history/<CODE>_<année>.csv
"""
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from leagues import LEAGUES

BASE = "https://www.football-data.co.uk"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "history"
SEASONS_BACK = 10


def download(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (analyse-foot)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(5)
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5)
    return None


def season_year(now: datetime) -> int:
    return now.year if now.month >= 7 else now.year - 1


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    current = season_year(datetime.now(timezone.utc))
    ok = 0
    for code, info in LEAGUES.items():
        div = info["csv"]
        for year in range(current - SEASONS_BACK, current + 1):
            path = OUT / f"{code}_{year}.csv"
            if path.exists() and year < current:
                continue  # saison terminée déjà téléchargée
            yy = f"{year % 100:02d}{(year + 1) % 100:02d}"
            data = download(f"{BASE}/mmz4281/{yy}/{div}.csv")
            if data and b"HomeTeam" in data[:500]:
                path.write_bytes(data)
                ok += 1
                n = data.count(b"\n") - 1
                print(f"{code} {year}-{year + 1}: {n} matchs")
            else:
                print(f"{code} {year}-{year + 1}: indisponible")
            time.sleep(1)
    fx = download(f"{BASE}/fixtures.csv")
    if fx and b"HomeTeam" in fx[:500]:
        (OUT / "fixtures.csv").write_bytes(fx)
        n = fx.count(b"\n") - 1
        print(f"prochains matchs : {n} lignes")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
