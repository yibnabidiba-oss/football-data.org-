"""Transforme les données brutes en fichiers prêts pour le site (site/data).

Sources :
  data/raw/      football-data.org (saison en cours : calendrier, résultats, classement officiel)
  data/history/  football-data.co.uk (10 saisons : résultats, mi-temps, tirs, corners, cartons,
                 xG, cotes des bookmakers, prochains matchs avec cotes)
  data/understat understat.com (4 saisons : xG par match, PPDA, deep, points attendus,
                 stats des joueurs, compositions des derniers matchs)

Usage : python scripts/analyze.py [--demo]
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import history
import model
import understat
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
        score = m.get("score") or {}
        ft, ht = score.get("fullTime") or {}, score.get("halfTime") or {}
        finished = m.get("status") == "FINISHED"
        out.append({
            "id": m["id"], "date": m["utcDate"], "matchday": m.get("matchday"),
            "status": m.get("status"), "home": str(h["id"]), "away": str(a["id"]),
            "hg": ft.get("home") if finished else None,
            "ag": ft.get("away") if finished else None,
            "hthg": ht.get("home") if finished else None,
            "htag": ht.get("away") if finished else None,
        })
    return sorted(out, key=lambda x: x["date"])


def season_label(year: int) -> str:
    return f"{year}-{str(year + 1)[-2:]}"


def ranks(values: dict, reverse: bool) -> dict:
    order = sorted(values, key=lambda t: values[t], reverse=reverse)
    return {t: i + 1 for i, t in enumerate(order)}


def near(d1: str, d2: str, days: int) -> bool:
    return abs((model.parse_date(d1) - model.parse_date(d2)).total_seconds()) <= days * 86400


def csv_season(rows: list[dict], fixtures: list[dict], year: int) -> list[dict]:
    """Saison au format commun à partir de football-data.co.uk seul (matchs joués +
    prochains matchs du fichier fixtures)."""
    out = []
    for r in rows:
        if r["hg"] is None:
            continue
        out.append({"id": f"{r['date'][:10]}-{r['home']}-{r['away']}", "date": r["date"],
                    "matchday": None, "status": "FINISHED", "home": r["home"], "away": r["away"],
                    "hg": r["hg"], "ag": r["ag"], "hthg": r.get("hthg"), "htag": r.get("htag"),
                    "hxg": r.get("hxg"), "axg": r.get("axg"), "odds": r.get("odds"), "season": year})
    played = {(m["home"], m["away"]) for m in out}
    for f in fixtures:
        if (f["home"], f["away"]) in played:
            continue
        out.append({"id": f"{f['date'][:10]}-{f['home']}-{f['away']}", "date": f["date"],
                    "matchday": None, "status": "TIMED", "home": f["home"], "away": f["away"],
                    "hg": None, "ag": None, "season": year})
    return sorted(out, key=lambda m: m["date"])


def build_league(code: str, now: datetime, demo: bool) -> dict | None:
    info = LEAGUES[code]
    teams: dict[str, dict] = {}
    fd_hist: list[dict] = []
    seasons_h = {} if demo else history.load(code)
    all_rows = [r for y in seasons_h for r in seasons_h[y]]
    fixtures = history.load_fixtures(info["csv"]) if seasons_h else []

    if info.get("fd"):
        # ---- football-data.org : calendrier complet et classement officiel
        raw = RAW.parent / "demo_raw" if demo else RAW
        files = sorted(raw.glob(f"{code}_*.json"), key=lambda p: int(p.stem.split("_")[1]))
        if not files:
            return None
        current = json.loads(files[-1].read_text())
        cur_year = current["season"]
        season = normalise(current["matches"], teams)
        hist_teams: dict[str, dict] = {}
        for f in files[:-1]:
            fd_hist += normalise(json.loads(f.read_text())["matches"], hist_teams)
        for k, v in hist_teams.items():
            teams.setdefault(k, v)
        mapping = history.build_mapping(all_rows, season + fd_hist) if all_rows else {}
    else:
        # ---- football-data.co.uk seul : les noms d'équipes servent d'identifiants
        if not seasons_h:
            return None
        current = {"standings": []}
        cur_year = max(seasons_h)
        mapping = {r[k]: r[k] for r in all_rows + fixtures for k in ("home_name", "away_name")}
        season = []

    # ---- historique football-data.co.uk relié aux identifiants
    if all_rows:
        history.attach_ids(all_rows, mapping)
        history.attach_ids(fixtures, mapping)
        for r in all_rows + fixtures:
            for side in ("home", "away"):
                tid = r[side]
                if tid not in teams:
                    nm = r[side + "_name"]
                    teams[tid] = {"name": nm, "short": nm, "tla": nm[:3].upper(), "crest": ""}
    if not info.get("fd"):
        season = csv_season(seasons_h.get(cur_year, []), fixtures, cur_year)
    season_teams = sorted({m["home"] for m in season} | {m["away"] for m in season})
    if not season_teams:
        return None
    # ---- understat : xG des saisons passées, indicateurs avancés, joueurs
    us = understat.load(code) if info.get("understat") and not demo else {}
    us_map = understat.build_mapping(us, all_rows + season) if us else {}
    if us:
        for m in season:
            m["season"] = cur_year
        understat.attach_xg(all_rows, us, us_map)

    past_years = sorted(y for y in seasons_h if y < cur_year)
    co_past = [r for y in past_years for r in seasons_h[y] if r["hg"] is not None]
    co_cur = [r for r in seasons_h.get(cur_year, []) if r["hg"] is not None]
    hist_matches = co_past or fd_hist

    # xG, stats et cotes du co.uk rattachés aux matchs football-data.org de la saison
    co_index = {(r["home"], r["away"]): r for r in co_cur}
    for m in season:
        r = co_index.get((m["home"], m["away"]))
        if r and model.is_played(m) and (r["hg"], r["ag"]) == (m["hg"], m["ag"]):
            m["hxg"], m["axg"], m["odds"] = r["hxg"], r["axg"], r["odds"]

    if us:
        understat.attach_xg(season, us, us_map)  # si football-data.co.uk n'a pas encore les xG
    us_cur = us.get(cur_year) or {}
    adv = understat.team_indicators(us_cur, us_map, season_teams) if us_cur else {}
    rosters = understat.load_rosters(code) if us_cur else {}
    squad = understat.players(us_cur, us_map, season_teams, rosters) if us_cur else {}
    absent = understat.absences(rosters, us_map, us_cur, squad) if rosters else {}
    leaders = understat.league_leaders(squad) if squad else []

    # ---- classement officiel (règles de départage) ou calculé
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

    # ---- modèle de forces (historique + saison, pondéré dans le temps, xG inclus)
    params = model.fit_strengths(hist_matches + season, now, teams=season_teams)
    params["att"] = {t: params["att"][t] for t in season_teams}
    params["def"] = {t: params["def"][t] for t in season_teams}

    # ---- Elo sur toutes les saisons disponibles
    if past_years:
        elo_input = [[r for r in seasons_h[y] if r["hg"] is not None] for y in past_years]
    else:
        elo_input = [fd_hist] if fd_hist else []
    elo_all = model.elo_seasons(elo_input + [season])
    elo = {t: round(elo_all.get(t, 1500.0), 1) for t in season_teams}

    # ---- stats par équipe
    r_att, r_def, r_elo = (ranks(params["att"], True), ranks(params["def"], False), ranks(elo, True))
    past = history.past_seasons(seasons_h, season_teams, cur_year) if seasons_h else {}
    stats = {}
    for t in season_teams:
        s = model.team_stats(t, season)
        s.update({"att": params["att"][t], "def": params["def"][t], "elo": elo[t],
                  "rank_att": r_att[t], "rank_def": r_def[t], "rank_elo": r_elo[t],
                  "game": history.game_stats(t, co_cur) if co_cur else None,
                  "past": past.get(t, []),
                  "adv": adv.get(t),
                  "players": squad.get(t, [])[:14],
                  "absent": absent.get(t)})
        stats[t] = s

    # ---- prochains matchs + cotes des bookmakers
    # Tous les matchs restants de la saison (le site calcule lui-même les pronostics lointains ;
    # ceux des 14 prochains jours sont pré-calculés ici).
    upcoming = [m for m in season if m["status"] in UPCOMING_STATUSES
                and model.parse_date(m["date"]) >= now - timedelta(hours=3)]
    upcoming_out = []
    for m in upcoming:
        market = next((f["odds"] for f in fixtures if f["home"] == m["home"] and f["away"] == m["away"]
                       and near(f["date"], m["date"], 3)), None)
        u = {"id": m["id"], "date": m["date"], "matchday": m["matchday"], "status": m["status"],
             "home": m["home"], "away": m["away"], "market": market}
        if model.parse_date(m["date"]) <= now + timedelta(days=14):
            u["pred"] = model.predict(params, m["home"], m["away"])
        upcoming_out.append(u)

    played = [m for m in season if model.is_played(m)]

    # ---- face-à-face : 10 saisons + saison en cours, entre équipes actuelles
    cur_set = set(season_teams)
    h2h = [[r["date"][:10], r["home"], r["away"], r["hg"], r["ag"], r.get("hthg"), r.get("htag")]
           for r in (co_past or fd_hist) + played
           if model.is_played(r) and r["home"] in cur_set and r["away"] in cur_set]
    h2h.sort(key=lambda x: x[0])

    # ---- fiabilité : saison en cours + saison précédente complète
    bt = model.backtest(season, hist_matches, min_matchday=0, keep_recent=100000)
    pre = {(r["date"], r["home"], r["away"]): r for r in bt.get("recent", [])}
    bt["recent"] = bt.get("recent", [])[:30]

    # Tous les résultats de la saison, avec le pronostic fait AVANT chaque match
    # (calculé uniquement avec les matchs déjà joués à cette date)
    results = []
    for m in played:
        r = {"date": m["date"], "matchday": m["matchday"], "home": m["home"], "away": m["away"],
             "hg": m["hg"], "ag": m["ag"], "hthg": m.get("hthg"), "htag": m.get("htag")}
        b = pre.get((m["date"][:10], m["home"], m["away"]))
        if b:
            r["pre"] = [b["p_home"], b["p_draw"], b["p_away"]]
        if m.get("odds"):
            o = m["odds"]
            r["book"] = [o["p_home"], o["p_draw"], o["p_away"]]
        results.append(r)
    if len(past_years) >= 2:
        last = [r for r in seasons_h[past_years[-1]] if r["hg"] is not None]
        earlier = [r for y in past_years[-4:-1] for r in seasons_h[y] if r["hg"] is not None]
        prev_bt = model.backtest(last, earlier, min_matchday=0, keep_recent=0)
        prev_bt.pop("calibration", None)
        prev_bt["season"] = season_label(past_years[-1])
        bt["previous"] = prev_bt

    trends = model.league_trends(season)
    if co_cur:
        trends["game"] = history.league_game_avgs(co_cur)

    return {
        "code": code, "slug": info["slug"], "name": info["name"], "country": info["country"],
        "tier": info["tier"], "has_players": bool(squad), "official_table": bool(info.get("fd")),
        "season": season_label(cur_year), "demo": demo,
        "updated_at": now.isoformat(timespec="minutes"),
        "history_seasons": [season_label(y) for y in past_years],
        "teams": {t: teams[t] for t in season_teams},
        "season_teams": season_teams,
        "table": table,
        "trends": trends,
        "model": params,
        "team_stats": stats,
        "upcoming": upcoming_out,
        "results": results,
        "h2h": h2h,
        "leaders": leaders,
        "backtest": bt,
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
                                "country": data["country"], "tier": data["tier"], "season": data["season"]})
        bt = data["backtest"]
        prev = bt.get("previous", {})
        print(f"{data['name']} : {len(data['season_teams'])} équipes, "
              f"{len(data['history_seasons'])} saisons d'historique, {len(data['h2h'])} face-à-face, "
              f"{sum(len(s['players']) for s in data['team_stats'].values())} joueurs, "
              f"{sum(len((s.get('absent') or {}).get('missing', [])) for s in data['team_stats'].values())} absences, "
              f"{len(data['upcoming'])} à venir ({sum(1 for u in data['upcoming'] if u['market'])} avec cotes) | "
              f"fiabilité saison {bt.get('accuracy_1x2', '-')} (n={bt.get('n', 0)}), "
              f"saison passée {prev.get('accuracy_1x2', '-')} vs bookmakers "
              f"{prev.get('bookmakers', {}).get('accuracy_1x2', '-')}")
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))
    return 0 if meta["leagues"] else 1


if __name__ == "__main__":
    sys.exit(main())
