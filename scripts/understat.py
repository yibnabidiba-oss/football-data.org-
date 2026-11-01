"""Stats avancées understat.com : correspondance des équipes, indicateurs d'équipe
(xG, PPDA, deep, points attendus…), statistiques des joueurs et absences récentes."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import history

DIR = Path(__file__).resolve().parent.parent / "data" / "understat"
POS_FR = {"GK": "Gardien", "D": "Défenseur", "M": "Milieu", "F": "Attaquant", "S": "Remplaçant"}


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load(code: str) -> dict[int, dict]:
    out = {}
    for p in sorted(DIR.glob(f"{code}_*.json")):
        tail = p.stem.split("_")[1]
        if not tail.isdigit():
            continue
        try:
            d = json.loads(p.read_text())
        except ValueError:
            continue
        if d.get("teams"):
            out[int(tail)] = d
    return out


def load_rosters(code: str) -> dict:
    try:
        return json.loads((DIR / f"{code}_rosters.json").read_text())
    except (OSError, ValueError):
        return {}


def match_rows(season: dict) -> list[dict]:
    """Matchs joués au format commun (pour la correspondance et le modèle)."""
    rows = []
    for m in season.get("dates") or []:
        if not m.get("isResult"):
            continue
        rows.append({
            "date": m["datetime"].replace(" ", "T") + "Z",
            "home_name": m["h"]["title"], "away_name": m["a"]["title"],
            "uid_h": m["h"]["id"], "uid_a": m["a"]["id"],
            "hg": int(m["goals"]["h"]), "ag": int(m["goals"]["a"]),
            "hxg": round(_f(m["xG"]["h"]), 3), "axg": round(_f(m["xG"]["a"]), 3),
        })
    return rows


def build_mapping(seasons: dict[int, dict], fd_matches: list[dict]) -> dict[str, str]:
    """Nom understat -> identifiant football-data.org (via les matchs communs)."""
    rows = [r for y in seasons for r in match_rows(seasons[y])]
    return history.build_mapping(rows, fd_matches)


def attach_xg(rows: list[dict], seasons: dict[int, dict], mapping: dict[str, str]) -> int:
    """Ajoute les xG understat aux matchs (football-data.co.uk) qui n'en ont pas."""
    idx = {}
    for y, s in seasons.items():
        for r in match_rows(s):
            h, a = mapping.get(r["home_name"]), mapping.get(r["away_name"])
            if h and a:
                idx[(y, h, a)] = r
    n = 0
    for r in rows:
        if r.get("hxg") is not None or r["hg"] is None:
            continue
        u = idx.get((r.get("season"), r["home"], r["away"]))
        if u and (u["hg"], u["ag"]) == (r["hg"], r["ag"]):
            r["hxg"], r["axg"] = u["hxg"], u["axg"]
            n += 1
    return n


# --------------------------------------------------------------------------- équipes

def team_indicators(season: dict, mapping: dict[str, str], teams: list[str]) -> dict[str, dict]:
    out = {}
    for t in (season.get("teams") or {}).values():
        tid = mapping.get(t["title"])
        if tid not in teams:
            continue
        hist = sorted(t.get("history") or [], key=lambda h: h["date"])
        n = len(hist)
        if not n:
            continue
        s = lambda k: sum(_f(h.get(k)) for h in hist)  # noqa: E731
        ppda_att = sum(_f(h["ppda"]["att"]) for h in hist)
        ppda_def = sum(_f(h["ppda"]["def"]) for h in hist)
        ppda_a_att = sum(_f(h["ppda_allowed"]["att"]) for h in hist)
        ppda_a_def = sum(_f(h["ppda_allowed"]["def"]) for h in hist)
        last5 = hist[-5:]
        pts = s("pts")
        out[tid] = {
            "games": n,
            "xg": round(s("xG") / n, 2), "xga": round(s("xGA") / n, 2),
            "npxg": round(s("npxG") / n, 2), "npxga": round(s("npxGA") / n, 2),
            "ppda": round(ppda_att / ppda_def, 1) if ppda_def else None,
            "ppda_allowed": round(ppda_a_att / ppda_a_def, 1) if ppda_a_def else None,
            "deep": round(s("deep") / n, 1), "deep_allowed": round(s("deep_allowed") / n, 1),
            "xpts": round(s("xpts"), 1), "pts": int(pts),
            "goals_minus_xg": round(s("scored") - s("xG"), 1),
            "conceded_minus_xga": round(s("missed") - s("xGA"), 1),
            "xgd_last5": round(sum(_f(h["xG"]) - _f(h["xGA"]) for h in last5) / len(last5), 2),
            "xgd_season": round((s("xG") - s("xGA")) / n, 2),
            "xg_trend": [round(_f(h["xG"]) - _f(h["xGA"]), 2) for h in hist[-10:]],
        }
    # rangs dans le championnat
    keys = {"xg": True, "xga": False, "npxg": True, "ppda": False, "deep": True, "xpts": True}
    for k, high_is_good in keys.items():
        vals = {t: v[k] for t, v in out.items() if v.get(k) is not None}
        order = sorted(vals, key=lambda t: vals[t], reverse=high_is_good)
        for i, t in enumerate(order):
            out[t]["rank_" + k] = i + 1
    return out


# --------------------------------------------------------------------------- joueurs

def roster_teams(rosters: dict, mapping: dict[str, str], season: dict) -> dict[str, str]:
    """Joueur -> équipe, d'après sa dernière apparition dans une composition."""
    uid_to_fd = {str(t["id"]): mapping[t["title"]] for t in (season.get("teams") or {}).values()
                 if t["title"] in mapping}
    seen = {}
    for m in sorted(rosters.values(), key=lambda m: m["date"]):
        for side in ("h", "a"):
            tid = uid_to_fd.get(str(m[side]))
            for p in (m["rosters"].get(side) or {}).values():
                if tid:
                    seen[str(p["player_id"])] = tid
    return seen


def players(season: dict, mapping: dict[str, str], teams: list[str],
            rosters: dict | None = None) -> dict[str, list[dict]]:
    """Joueurs de chaque équipe, triés par implication offensive."""
    by_team = defaultdict(list)
    from_rosters = roster_teams(rosters or {}, mapping, season)
    for p in season.get("players") or []:
        clubs = [c.strip() for c in (p.get("team_title") or "").split(",") if c.strip()]
        if len(clubs) == 1:
            tid = mapping.get(clubs[0])
        else:
            # plusieurs clubs (transfert, ou donnée ambiguë) : on se fie aux compositions récentes
            tid = from_rosters.get(str(p["id"]))
            if tid not in {mapping.get(c) for c in clubs}:
                continue
        if tid not in teams:
            continue
        mins = _f(p.get("time"))
        g, xg, npxg, a, xa = (_f(p.get(k)) for k in ("goals", "xG", "npxG", "assists", "xA"))
        per90 = (lambda v: round(v * 90 / mins, 2)) if mins >= 90 else (lambda v: None)
        by_team[tid].append({
            "id": p["id"], "name": p["player_name"], "pos": (p.get("position") or "").split(" ")[0],
            "games": int(_f(p.get("games"))), "min": int(mins),
            "goals": int(g), "xg": round(xg, 2), "npxg": round(npxg, 2),
            "assists": int(a), "xa": round(xa, 2),
            "shots": int(_f(p.get("shots"))), "kp": int(_f(p.get("key_passes"))),
            "xgchain": round(_f(p.get("xGChain")), 2), "xgbuildup": round(_f(p.get("xGBuildup")), 2),
            "yellow": int(_f(p.get("yellow_cards"))), "red": int(_f(p.get("red_cards"))),
            "xg90": per90(xg), "xa90": per90(xa), "g_minus_xg": round(g - xg, 2),
        })
    out = {}
    for tid, lst in by_team.items():
        tot_inv = sum(p["npxg"] + p["xa"] for p in lst) or 1
        tot_min = max((p["min"] for p in lst), default=0) or 1
        for p in lst:
            p["share"] = round((p["npxg"] + p["xa"]) / tot_inv, 3)  # part des occasions de l'équipe
            p["min_share"] = round(p["min"] / tot_min, 3)          # part du temps de jeu possible
        lst.sort(key=lambda p: (p["npxg"] + p["xa"], p["min"]), reverse=True)
        out[tid] = lst
    return out


def absences(rosters: dict, mapping: dict[str, str], season: dict,
             team_players: dict[str, list[dict]]) -> dict[str, dict]:
    """Joueurs importants absents du dernier match de championnat de leur équipe.

    "Important" : au moins 15 % des occasions de l'équipe (xG + xA), ou titulaire
    régulier (au moins 70 % du temps de jeu). On ne connaît pas la raison (blessure,
    suspension, repos) : c'est un signal à vérifier, pas une certitude."""
    uid_to_fd = {}
    for t in (season.get("teams") or {}).values():
        if t["title"] in mapping:
            uid_to_fd[str(t["id"])] = mapping[t["title"]]
    last = {}  # équipe -> (date, ids des joueurs ayant joué)
    for m in rosters.values():
        for side in ("h", "a"):
            tid = uid_to_fd.get(str(m[side]))
            if not tid:
                continue
            played = {str(p["player_id"]) for p in (m["rosters"].get(side) or {}).values()
                      if _f(p.get("time")) > 0}
            if tid not in last or m["date"] > last[tid][0]:
                last[tid] = (m["date"], played)
    out = {}
    for tid, (date, played) in last.items():
        missing = []
        for p in team_players.get(tid, []):
            key = p["share"] >= 0.15 or (p["min_share"] >= 0.7 and p["games"] >= 4)
            if key and str(p["id"]) not in played:
                missing.append({"name": p["name"], "pos": p["pos"], "share": p["share"],
                                "min_share": p["min_share"]})
        out[tid] = {"last_match": date[:10], "missing": missing}
    return out


def league_leaders(team_players: dict[str, list[dict]], n: int = 60) -> list[dict]:
    allp = [dict(p, team=t) for t, lst in team_players.items() for p in lst if p["min"] >= 90]
    allp.sort(key=lambda p: (p["goals"] + p["assists"], p["xg"] + p["xa"]), reverse=True)
    keep = {p["id"] for p in allp[:n]}
    for k in ("goals", "xg", "assists", "xa", "g_minus_xg"):
        keep |= {p["id"] for p in sorted(allp, key=lambda p: p[k], reverse=True)[:15]}
    return [p for p in allp if p["id"] in keep]
