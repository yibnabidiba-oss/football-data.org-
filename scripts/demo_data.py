"""Génère des données SIMULÉES (clubs fictifs) au format football-data.org,
pour tester l'application sans clé API.

Usage : python scripts/demo_data.py && python scripts/analyze.py --demo
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "demo_raw"  # séparé des vraies données

CLUBS = {
    "PL": ["Ashford Rovers", "Brackley Town", "Castleford United", "Dunmore City", "Elmbridge FC",
           "Fairhaven Athletic", "Grantham Albion", "Harlow Wanderers", "Ilkley Rangers",
           "Kingsbury United", "Lydney Town", "Marlow City", "Northam Athletic", "Oakham Rovers",
           "Penrith Albion", "Redcar United", "Selsey Town", "Thornbury FC", "Uxbridge City",
           "Wexcombe Athletic", "Yarmouth Rovers", "Bexley Town", "Corby United"],
    "PD": ["Real Almadén", "Atlético Brenes", "CD Cazorla", "UD Dénia", "SD Écija", "Racing Ferrol",
           "CF Gandía", "Deportivo Haro", "Real Íscar", "CD Jaca", "UD Lorca", "Atlético Mérida",
           "CF Nerja", "SD Olot", "Real Plasencia", "CD Quintanar", "UD Ronda", "CF Sagunto",
           "Deportivo Tarifa", "Real Utiel", "CD Vélez", "UD Zafra", "CF Alcoy"],
    "FL1": ["AS Arcachon", "FC Beaune", "Olympique Cholet", "Stade Dinan", "US Épinal",
            "RC Figeac", "AS Granville", "FC Honfleur", "Olympique Istres", "Stade Joigny",
            "US Lisieux", "RC Menton", "AS Nogent", "FC Oyonnax", "Olympique Pau", "Stade Quimper",
            "US Royan", "RC Saumur", "AS Tulle", "FC Vannes", "Olympique Vichy"],
}
SIZES = {"PL": 20, "PD": 20, "FL1": 18}


def tla(name: str) -> str:
    words = [w for w in name.replace("-", " ").split() if w[0].isupper() and len(w) > 2]
    return (words[-1][:3] if words else name[:3]).upper()


def round_robin(teams: list[int], rng: random.Random) -> list[list[tuple[int, int]]]:
    t = teams[:]
    rng.shuffle(t)
    n = len(t)
    rounds = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = t[i], t[n - 1 - i]
            pairs.append((a, b) if r % 2 == 0 else (b, a))
        rounds.append(pairs)
        t = [t[0]] + [t[-1]] + t[1:-1]  # rotation (méthode du cercle)
    return rounds + [[(b, a) for a, b in rd] for rd in rounds]


def poisson(lam: float, rng: random.Random) -> int:
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p < l:
            return k
        k += 1


def season(code: str, year: int, team_ids: list[int], strength: dict, now: datetime,
           rng: random.Random, id_base: int) -> list[dict]:
    names = CLUBS[code]
    start = datetime(year, 8, 15, tzinfo=timezone.utc)
    matches = []
    for md, pairs in enumerate(round_robin(team_ids, rng), 1):
        day = start + timedelta(weeks=md - 1)
        for k, (h, a) in enumerate(pairs):
            kickoff = day + timedelta(days=k % 3, hours=13 + 2 * (k % 4))
            finished = kickoff < now
            lh = 1.45 * strength[h][0] * strength[a][1]
            la = 1.15 * strength[a][0] * strength[h][1]
            hg, ag = (poisson(lh, rng), poisson(la, rng)) if finished else (None, None)
            team = lambda i: {"id": id_base + i, "name": names[i], "shortName": names[i],
                              "tla": tla(names[i]), "crest": ""}
            matches.append({
                "id": id_base * 1000 + year * 10 + len(matches), "utcDate": kickoff.isoformat()
                .replace("+00:00", "Z"), "status": "FINISHED" if finished else "TIMED",
                "matchday": md, "homeTeam": team(h), "awayTeam": team(a),
                "score": {"fullTime": {"home": hg, "away": ag}}})
    return matches


def main() -> None:
    rng = random.Random(2026)
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    RAW.mkdir(parents=True, exist_ok=True)
    for f in RAW.glob("*.json"):
        f.unlink()
    for n, code in enumerate(SIZES):
        size, pool = SIZES[code], list(range(len(CLUBS[code])))
        strength = {i: (math.exp(rng.gauss(0, 0.25)), math.exp(rng.gauss(0, 0.2))) for i in pool}
        prev_teams = pool[:size]
        # 3 relégués (les plus faibles) remplacés par 3 promus
        weakest = sorted(prev_teams, key=lambda i: strength[i][0] / strength[i][1])[:3]
        cur_teams = [t for t in prev_teams if t not in weakest] + pool[size:size + 3]
        for year, teams in ((2025, prev_teams), (2026, cur_teams)):
            ms = season(code, year, teams, strength, now, rng, (n + 1) * 100)
            (RAW / f"{code}_{year}.json").write_text(json.dumps(
                {"code": code, "season": year, "fetched_at": now.isoformat(),
                 "matches": ms, "standings": []}, ensure_ascii=False))
            # les forces évoluent un peu d'une saison à l'autre
            strength = {i: (s[0] * math.exp(rng.gauss(0, 0.08)), s[1] * math.exp(rng.gauss(0, 0.08)))
                        for i, s in strength.items()}
        print(f"{code} : données simulées générées")


if __name__ == "__main__":
    main()
