"""Transforme les données brutes (data/raw) en fichiers prêts pour le site (site/data).

Usage : python scripts/analyze.py [--demo]
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import model
from leagues import LEAGUES

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "site" / "data"
UPCOMING_STATUSES = {"SCHEDULED", "TIMED", "POSTPONED"}


def normalise(raw_matches: list[dict], teams: dict) -> list[dict]:
    out = []
    for m in raw_matches:
        h, a = m["homeTeam"], m["awayTeam"]
        if not h.get("id") or not a.get("id"):
            continue
        for t in (h, a):
            teams.setdefault(str(t["id"]), {
                "name": t.get("name") or t.get("shortName") or "?",
                "short": t.get("shortName") or t.get("name") or "?",
                "tla": t.get("tla") or (t.get("shortName") or "???")[:3].upper(),
                "crest": t.get("crest") or "",
            })
        ft = (m.get("score") or {}).get("fullTime") or {}
        finished = m.get("status") == "FINISHED"
        out.append({
            "id": m["id"], "date": m["utcDate"], "matchday": m.get("matchday"),
            "status": m.get("status"), "home": str(h["id"]), "away": str(a["id"]),
            "hg": ft.get("home") if finished else None,
            "ag": ft.get("away") if finished else None,
        })
    return sorted(out, key=lambda x: x["date"])


def season_label(year: int) -> str:
    return f"{year}-{str(year + 1)[-2:]}"


def ranks(values: dict, reverse: bool) -> dict:
    order = sorted(values, key=lambda t: values[t], reverse=reverse)
    return {t: i + 1 for i, t in enumerate(order)}


def build_league(code: str, now: datetime, demo: bool) -> dict | None:
    raw = RAW.parent / "demo_raw" if demo else RAW
    files = sorted(raw.glob(f"{code}_*.json"), key=lambda p: int(p.stem.split("_")[1]))
    if not files:
        return None
    current = json.loads(files[-1].read_text())
    teams: dict[str, dict] = {}
    season = normalise(current["matches"], teams)
    history: list[dict] = []
    hist_teams: dict[str, dict] = {}
    for f in files[-3:-1]:  # jusqu'à 2 saisons d'historique
        history += normalise(json.loads(f.read_text())["matches"], hist_teams)
    for k, v in hist_teams.items():
        teams.setdefault(k, v)

    season_teams = sorted({m["home"] for m in season} | {m["away"] for m in season})

    # Classement : celui de l'API s'il existe (règles de départage officielles), sinon calculé
    table = None
    for st in current.get("standings") or []:
        if st.get("type") == "TOTAL" and st.get("table"):
            table = [{"position": r["position"], "team": str(r["team"]["id"]),
                      "played": r["playedGames"], "won": r["won"], "draw": r["draw"],
                      "lost": r["lost"], "gf": r["goalsFor"], "ga": r["goalsAgainst"],
                      "gd": r["goalDifference"], "points": r["points"]} for r in st["table"]]
            break
    if not table:
        table = model.compute_table(season, season_teams)

    # Modèle de forces (historique + saison, pondéré dans le temps)
    params = model.fit_strengths(history + season, now, teams=season_teams)
    params["att"] = {t: params["att"][t] for t in season_teams}
    params["def"] = {t: params["def"][t] for t in season_teams}

    # Elo : saison(s) précédente(s), régression vers la moyenne, puis saison en cours
    start = {}
    if history:
        prev = model.regress_elo(model.elo_ratings(history))
        start = {t: r for t, r in prev.items() if t in season_teams}
        if prev:
            floor = sorted(prev.values())[:3]
            newcomer = sum(floor) / len(floor)
            for t in season_teams:
                start.setdefault(t, newcomer)
    elo = model.elo_ratings(season, start=start)
    elo = {t: round(elo.get(t, start.get(t, 1500.0)), 1) for t in season_teams}

    r_att = ranks(params["att"], reverse=True)
    r_def = ranks(params["def"], reverse=False)
    r_elo = ranks(elo, reverse=True)
    stats = {}
    for t in season_teams:
        s = model.team_stats(t, season)
        s.update({"att": params["att"][t], "def": params["def"][t], "elo": elo[t],
                  "rank_att": r_att[t], "rank_def": r_def[t], "rank_elo": r_elo[t]})
        stats[t] = s

    upcoming = [m for m in season if m["status"] in UPCOMING_STATUSES
                and now <= model.parse_date(m["date"]) <= now + timedelta(days=14)]
    if not upcoming:
        upcoming = [m for m in season if m["status"] in UPCOMING_STATUSES
                    and model.parse_date(m["date"]) >= now][:10]
    upcoming_out = [{"id": m["id"], "date": m["date"], "matchday": m["matchday"],
                     "status": m["status"], "home": m["home"], "away": m["away"],
                     "pred": model.predict(params, m["home"], m["away"])} for m in upcoming]

    played = [m for m in season if model.is_played(m)]
    results = [{"date": m["date"], "matchday": m["matchday"], "home": m["home"],
                "away": m["away"], "hg": m["hg"], "ag": m["ag"]} for m in played[-30:]][::-1]

    # Tous les matchs joués (compact) pour le face-à-face côté navigateur
    h2h = [[m["date"][:10], m["home"], m["away"], m["hg"], m["ag"]]
           for m in history + played if model.is_played(m)]

    info = LEAGUES[code]
    return {
        "code": code, "slug": info["slug"], "name": info["name"], "country": info["country"],
        "season": season_label(current["season"]), "demo": demo,
        "updated_at": now.isoformat(timespec="minutes"),
        "teams": {t: teams[t] for t in sorted(set(season_teams) | {x for r in h2h for x in r[1:3]})},
        "season_teams": season_teams,
        "table": table,
        "trends": model.league_trends(season),
        "model": params,
        "team_stats": stats,
        "upcoming": upcoming_out,
        "results": results,
        "h2h": h2h,
        "backtest": model.backtest(season, history),
    }


def main() -> int:
    demo = "--demo" in sys.argv
    env_now = os.environ.get("ANALYSIS_NOW")
    now = model.parse_date(env_now) if env_now else datetime.now(timezone.utc)
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"updated_at": now.isoformat(timespec="minutes"), "demo": demo, "leagues": []}
    for code in LEAGUES:
        data = build_league(code, now, demo)
        if not data:
            print(f"{code} : aucune donnée", file=sys.stderr)
            continue
        (OUT / f"{data['slug']}.json").write_text(json.dumps(data, ensure_ascii=False,
                                                              separators=(",", ":")))
        meta["leagues"].append({"code": code, "slug": data["slug"], "name": data["name"],
                                "country": data["country"], "season": data["season"]})
        bt = data["backtest"]
        print(f"{data['name']} : {len(data['season_teams'])} équipes, "
              f"{data['trends'].get('played', 0)} matchs joués, {len(data['upcoming'])} à venir, "
              f"backtest {bt.get('n', 0)} matchs / précision 1N2 {bt.get('accuracy_1x2', '-')}")
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
    return 0 if meta["leagues"] else 1


if __name__ == "__main__":
    sys.exit(main())
