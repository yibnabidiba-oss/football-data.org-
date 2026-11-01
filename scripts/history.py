"""Historique football-data.co.uk : lecture des CSV, correspondance des noms d'équipes
avec football-data.org, statistiques de jeu, cotes et classements des saisons passées."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import model

HIST = Path(__file__).resolve().parent.parent / "data" / "history"


# --------------------------------------------------------------------------- lecture

def _num(v, cast=float):
    try:
        return cast(v) if v not in (None, "") else None
    except ValueError:
        try:
            return cast(float(v))
        except ValueError:
            return None


def _date(d: str, t: str | None) -> str | None:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            day = datetime.strptime(d.strip(), fmt)
            break
        except ValueError:
            continue
    else:
        return None
    hh, mm = 15, 0
    if t and ":" in t:
        hh, mm = (int(x) for x in t.split(":")[:2])
    # heure locale (Royaume-Uni / Europe) : approximation suffisante pour l'ordre des matchs
    return day.replace(hour=hh, minute=mm, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _odds(r: dict, *keys):
    for k in keys:
        v = _num(r.get(k))
        if v and v > 1:
            return v
    return None


def read_csv(path: Path) -> list[dict]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        if not r.get("HomeTeam") or not r.get("Date"):
            continue
        date = _date(r["Date"], r.get("Time"))
        if not date:
            continue
        hg, ag = _num(r.get("FTHG"), int), _num(r.get("FTAG"), int)
        oh, od, oa = (_odds(r, "AvgH", "BbAvH", "B365H"), _odds(r, "AvgD", "BbAvD", "B365D"),
                      _odds(r, "AvgA", "BbAvA", "B365A"))
        o_ov, o_un = _odds(r, "Avg>2.5", "BbAv>2.5", "B365>2.5"), _odds(r, "Avg<2.5", "BbAv<2.5", "B365<2.5")
        rows.append({
            "date": date, "home_name": r["HomeTeam"].strip(), "away_name": r["AwayTeam"].strip(),
            "hg": hg, "ag": ag,
            "hthg": _num(r.get("HTHG"), int), "htag": _num(r.get("HTAG"), int),
            "hs": _num(r.get("HS"), int), "as": _num(r.get("AS"), int),
            "hst": _num(r.get("HST"), int), "ast": _num(r.get("AST"), int),
            "hc": _num(r.get("HC"), int), "ac": _num(r.get("AC"), int),
            "hf": _num(r.get("HF"), int), "af": _num(r.get("AF"), int),
            "hy": _num(r.get("HY"), int), "ay": _num(r.get("AY"), int),
            "hr": _num(r.get("HR"), int), "ar": _num(r.get("AR"), int),
            "hxg": _num(r.get("HxG")), "axg": _num(r.get("AxG")),
            "odds": implied(oh, od, oa, o_ov, o_un),
            "odds_raw": [oh, od, oa, o_ov, o_un] if oh and od and oa else None,
        })
    return rows


def implied(oh, od, oa, o_ov=None, o_un=None) -> dict | None:
    """Cotes -> probabilités (marge du bookmaker retirée)."""
    if not (oh and od and oa):
        return None
    s = 1 / oh + 1 / od + 1 / oa
    out = {"p_home": round(1 / oh / s, 4), "p_draw": round(1 / od / s, 4), "p_away": round(1 / oa / s, 4)}
    if o_ov and o_un:
        t = 1 / o_ov + 1 / o_un
        out["over25"] = round(1 / o_ov / t, 4)
    return out


def load(code: str) -> dict[int, list[dict]]:
    """{année de début de saison: [matchs]}"""
    out = {}
    for p in sorted(HIST.glob(f"{code}_*.csv")):
        try:
            year = int(p.stem.split("_")[1])
        except (IndexError, ValueError):
            continue
        rows = read_csv(p)
        for r in rows:
            r["season"] = year
        out[year] = rows
    return out


def load_fixtures(div: str) -> list[dict]:
    p = HIST / "fixtures.csv"
    if not p.exists():
        return []
    raw = p.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("Div") != div:
            continue
        date = _date(r.get("Date", ""), r.get("Time"))
        odds = implied(_odds(r, "AvgH", "B365H"), _odds(r, "AvgD", "B365D"), _odds(r, "AvgA", "B365A"),
                       _odds(r, "Avg>2.5", "B365>2.5"), _odds(r, "Avg<2.5", "B365<2.5"))
        if date and odds:
            out.append({"date": date, "home_name": r["HomeTeam"].strip(),
                        "away_name": r["AwayTeam"].strip(), "odds": odds})
    return out


# --------------------------------------------------------------------------- correspondance des noms

def build_mapping(hist_rows: list[dict], fd_matches: list[dict]) -> dict[str, str]:
    """Associe chaque nom football-data.co.uk à un identifiant football-data.org, en
    comparant les matchs communs aux deux sources (même jour, même score)."""
    index = defaultdict(list)
    for m in fd_matches:
        if model.is_played(m):
            index[(m["date"][:10], m["hg"], m["ag"])].append(m)
    votes: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in hist_rows:
        if r["hg"] is None:
            continue
        d = datetime.fromisoformat(r["date"][:10])
        cands = []
        for delta in (0, -1, 1):
            key = ((d + timedelta(days=delta)).date().isoformat(), r["hg"], r["ag"])
            cands += index.get(key, [])
        if not cands:
            continue
        w = 1 / len(cands)
        for m in cands:
            votes[r["home_name"]][m["home"]] += w
            votes[r["away_name"]][m["away"]] += w
    # attribution gloutonne, une équipe par nom
    pairs = sorted(((v, name, tid) for name, d in votes.items() for tid, v in d.items()), reverse=True)
    mapping, used = {}, set()
    for v, name, tid in pairs:
        if v < 2 or name in mapping or tid in used:
            continue
        mapping[name] = tid
        used.add(tid)
    return mapping


def attach_ids(rows: list[dict], mapping: dict[str, str]) -> None:
    for r in rows:
        r["home"] = mapping.get(r["home_name"], "h:" + r["home_name"])
        r["away"] = mapping.get(r["away_name"], "h:" + r["away_name"])


# --------------------------------------------------------------------------- stats de jeu

def game_stats(team: str, rows: list[dict]) -> dict | None:
    games = [r for r in rows if team in (r["home"], r["away"]) and r["hg"] is not None]
    if not games:
        return None
    acc = defaultdict(float)
    cnt = defaultdict(int)
    ht = {"lead": 0, "lead_won": 0, "behind": 0, "behind_pts": 0, "ht_known": 0, "g1": 0, "g2": 0}
    for r in games:
        home = r["home"] == team
        s = (lambda k_h, k_a: (r[k_h], r[k_a]) if home else (r[k_a], r[k_h]))
        for key, (kh, ka) in {"shots": ("hs", "as"), "sot": ("hst", "ast"), "corners": ("hc", "ac"),
                              "fouls": ("hf", "af"), "yellow": ("hy", "ay"), "red": ("hr", "ar"),
                              "xg": ("hxg", "axg")}.items():
            f, a = s(kh, ka)
            if f is not None and a is not None:
                acc[key + "_for"] += f
                acc[key + "_against"] += a
                cnt[key] += 1
        hf, ha = s("hthg", "htag")
        ff, fa = s("hg", "ag")
        if hf is not None and ha is not None:
            ht["ht_known"] += 1
            ht["g1"] += hf
            ht["g2"] += ff - hf
            if hf > ha:
                ht["lead"] += 1
                ht["lead_won"] += ff > fa
            elif hf < ha:
                ht["behind"] += 1
                ht["behind_pts"] += ff >= fa
    out = {"matches": len(games)}
    for key in ("shots", "sot", "corners", "fouls", "yellow", "red", "xg"):
        if cnt[key]:
            out[key + "_for"] = round(acc[key + "_for"] / cnt[key], 2)
            out[key + "_against"] = round(acc[key + "_against"] / cnt[key], 2)
    goals = sum((r["hg"] if r["home"] == team else r["ag"]) for r in games)
    if out.get("shots_for"):
        out["conversion"] = round(goals / (out["shots_for"] * len(games)), 3)
    if ht["ht_known"]:
        n = ht["ht_known"]
        out["ht_lead"] = round(ht["lead"] / n, 3)
        out["ht_lead_won"] = round(ht["lead_won"] / ht["lead"], 3) if ht["lead"] else None
        out["ht_behind"] = round(ht["behind"] / n, 3)
        out["ht_comeback"] = round(ht["behind_pts"] / ht["behind"], 3) if ht["behind"] else None
        tot = ht["g1"] + ht["g2"]
        out["goals_2nd_half"] = round(ht["g2"] / tot, 3) if tot else None
    return out


def league_game_avgs(rows: list[dict]) -> dict:
    played = [r for r in rows if r["hg"] is not None]
    out = {}
    for key, (kh, ka) in {"shots": ("hs", "as"), "corners": ("hc", "ac"), "cards": ("hy", "ay"),
                          "xg": ("hxg", "axg")}.items():
        vals = [r[kh] + r[ka] for r in played if r[kh] is not None and r[ka] is not None]
        if vals:
            out[key] = round(sum(vals) / len(vals), 2)
    return out


# --------------------------------------------------------------------------- saisons passées

def past_seasons(seasons: dict[int, list[dict]], teams: list[str], before: int) -> dict:
    """Position finale de chaque équipe actuelle lors des saisons précédentes."""
    out = {t: [] for t in teams}
    for year in sorted(y for y in seasons if y < before):
        rows = [r for r in seasons[year] if r["hg"] is not None]
        if not rows:
            continue
        ids = sorted({r["home"] for r in rows} | {r["away"] for r in rows})
        table = {r["team"]: r for r in model.compute_table(rows, ids)}
        label = f"{year}-{str(year + 1)[-2:]}"
        for t in teams:
            r = table.get(t)
            out[t].append({"season": label, "pos": r["position"] if r else None,
                           "pts": r["points"] if r else None, "n": len(ids),
                           "gf": r["gf"] if r else None, "ga": r["ga"] if r else None})
    return out
