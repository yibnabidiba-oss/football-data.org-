"""Moteur statistique : forces attaque/défense (Poisson + Dixon-Coles), Elo, stats d'équipe.

Aucune dépendance externe. Un match normalisé est un dict :
    {"id", "date" (ISO), "matchday", "status", "home", "away", "hg", "ag"}
"home"/"away" sont des identifiants d'équipe (str). hg/ag = None si pas encore joué.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

MAX_GOALS = 10          # taille de la matrice des scores
DECAY_PER_DAY = 0.004   # pondération temporelle (demi-vie ~ 170 jours)
PRIOR_MATCHES = 6.0     # régularisation vers la moyenne (en "matchs fictifs")


def parse_date(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def is_played(m: dict) -> bool:
    return m.get("hg") is not None and m.get("ag") is not None


# --------------------------------------------------------------------------- Poisson

def poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def dc_tau(x: int, y: int, lh: float, la: float, rho: float) -> float:
    """Correction Dixon-Coles des petits scores (0-0, 1-0, 0-1, 1-1)."""
    if x == 0 and y == 0:
        return 1 - lh * la * rho
    if x == 0 and y == 1:
        return 1 + lh * rho
    if x == 1 and y == 0:
        return 1 + la * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def score_matrix(lh: float, la: float, rho: float = 0.0) -> list[list[float]]:
    ph = [poisson_pmf(i, lh) for i in range(MAX_GOALS + 1)]
    pa = [poisson_pmf(j, la) for j in range(MAX_GOALS + 1)]
    mat = [[ph[i] * pa[j] * dc_tau(i, j, lh, la, rho) for j in range(MAX_GOALS + 1)]
           for i in range(MAX_GOALS + 1)]
    total = sum(sum(r) for r in mat)
    return [[v / total for v in r] for r in mat]


def markets(lh: float, la: float, rho: float = 0.0) -> dict:
    """Toutes les probabilités utiles pour un match."""
    mat = score_matrix(lh, la, rho)
    n = len(mat)
    p_home = sum(mat[i][j] for i in range(n) for j in range(n) if i > j)
    p_draw = sum(mat[i][i] for i in range(n))
    p_away = 1 - p_home - p_draw

    def over(line):
        return sum(mat[i][j] for i in range(n) for j in range(n) if i + j > line)

    btts = sum(mat[i][j] for i in range(1, n) for j in range(1, n))
    scores = sorted(((mat[i][j], f"{i}-{j}") for i in range(n) for j in range(n)), reverse=True)
    return {
        "xg_home": round(lh, 2),
        "xg_away": round(la, 2),
        "p_home": round(p_home, 4),
        "p_draw": round(p_draw, 4),
        "p_away": round(p_away, 4),
        "over15": round(over(1.5), 4),
        "over25": round(over(2.5), 4),
        "over35": round(over(3.5), 4),
        "btts": round(btts, 4),
        "home_clean_sheet": round(sum(mat[i][0] for i in range(n)), 4),
        "away_clean_sheet": round(sum(mat[0][j] for j in range(n)), 4),
        "top_scores": [{"score": s, "p": round(p, 4)} for p, s in scores[:6]],
    }


# --------------------------------------------------------------------------- Modèle de forces

def fit_strengths(matches: list[dict], ref_date: datetime, teams: list[str] | None = None,
                  decay: float = DECAY_PER_DAY, prior: float = PRIOR_MATCHES,
                  iterations: int = 60, fit_rho: bool = True) -> dict:
    """Estime attaque/défense de chaque équipe (modèle de Maher pondéré dans le temps).

    lambda_dom = mu_dom * att[dom] * def[ext]
    lambda_ext = mu_ext * att[ext] * def[dom]
    att > 1 : attaque au-dessus de la moyenne. def > 1 : défense plus perméable que la moyenne.
    """
    played = [m for m in matches if is_played(m) and parse_date(m["date"]) < ref_date]
    team_set = set(teams or [])
    for m in played:
        team_set.update((m["home"], m["away"]))
    team_ids = sorted(team_set)

    rows = []
    for m in played:
        days = (ref_date - parse_date(m["date"])).total_seconds() / 86400
        rows.append((m["home"], m["away"], m["hg"], m["ag"], math.exp(-decay * days)))

    if not rows:
        return {"mu_home": 1.5, "mu_away": 1.2, "rho": 0.0, "n_matches": 0,
                "att": {t: 1.0 for t in team_ids}, "def": {t: 1.0 for t in team_ids}}

    wsum = sum(r[4] for r in rows)
    mu_home = sum(r[2] * r[4] for r in rows) / wsum
    mu_away = sum(r[3] * r[4] for r in rows) / wsum
    mu_home, mu_away = max(mu_home, 0.3), max(mu_away, 0.3)
    m_avg = (mu_home + mu_away) / 2

    att = {t: 1.0 for t in team_ids}
    dfn = {t: 1.0 for t in team_ids}
    for _ in range(iterations):
        g_for = {t: 0.0 for t in team_ids}
        e_for = {t: 0.0 for t in team_ids}
        for h, a, hg, ag, w in rows:
            g_for[h] += w * hg
            e_for[h] += w * mu_home * dfn[a]
            g_for[a] += w * ag
            e_for[a] += w * mu_away * dfn[h]
        att = {t: (g_for[t] + prior * m_avg) / (e_for[t] + prior * m_avg) for t in team_ids}
        _normalise(att)

        g_ag = {t: 0.0 for t in team_ids}
        e_ag = {t: 0.0 for t in team_ids}
        for h, a, hg, ag, w in rows:
            g_ag[h] += w * ag
            e_ag[h] += w * mu_away * att[a]
            g_ag[a] += w * hg
            e_ag[a] += w * mu_home * att[h]
        dfn = {t: (g_ag[t] + prior * m_avg) / (e_ag[t] + prior * m_avg) for t in team_ids}
        _normalise(dfn)

    rho = 0.0
    if fit_rho:
        best = None
        for k in range(-20, 11):
            r = k / 100
            ll = 0.0
            for h, a, hg, ag, w in rows:
                if hg > 1 or ag > 1:
                    continue
                lh = mu_home * att[h] * dfn[a]
                la = mu_away * att[a] * dfn[h]
                t = dc_tau(hg, ag, lh, la, r)
                if t <= 0:
                    ll = -math.inf
                    break
                ll += w * math.log(t)
            if best is None or ll > best[0]:
                best = (ll, r)
        rho = best[1]

    return {"mu_home": round(mu_home, 4), "mu_away": round(mu_away, 4), "rho": rho,
            "n_matches": len(rows),
            "att": {t: round(v, 4) for t, v in att.items()},
            "def": {t: round(v, 4) for t, v in dfn.items()}}


def _normalise(d: dict) -> None:
    if not d:
        return
    g = math.exp(sum(math.log(v) for v in d.values()) / len(d))
    for k in d:
        d[k] /= g


def expected_goals(params: dict, home: str, away: str) -> tuple[float, float]:
    att, dfn = params["att"], params["def"]
    lh = params["mu_home"] * att.get(home, 1.0) * dfn.get(away, 1.0)
    la = params["mu_away"] * att.get(away, 1.0) * dfn.get(home, 1.0)
    return lh, la


def predict(params: dict, home: str, away: str) -> dict:
    lh, la = expected_goals(params, home, away)
    return markets(lh, la, params.get("rho", 0.0))


# --------------------------------------------------------------------------- Elo

def elo_ratings(matches: list[dict], k: float = 20.0, home_adv: float = 60.0,
                start: dict | None = None) -> dict:
    ratings = dict(start or {})
    for m in sorted((m for m in matches if is_played(m)), key=lambda m: m["date"]):
        h, a = m["home"], m["away"]
        rh, ra = ratings.setdefault(h, 1500.0), ratings.setdefault(a, 1500.0)
        exp_h = 1 / (1 + 10 ** ((ra - rh - home_adv) / 400))
        res = 1.0 if m["hg"] > m["ag"] else 0.5 if m["hg"] == m["ag"] else 0.0
        gd = abs(m["hg"] - m["ag"])
        mult = 1.0 if gd <= 1 else 1.5 if gd == 2 else (11 + gd) / 8
        delta = k * mult * (res - exp_h)
        ratings[h] = rh + delta
        ratings[a] = ra - delta
    return ratings


def regress_elo(ratings: dict, factor: float = 1 / 3) -> dict:
    """Entre deux saisons : on ramène chaque note d'un tiers vers 1500."""
    return {t: r - (r - 1500) * factor for t, r in ratings.items()}


# --------------------------------------------------------------------------- Stats d'équipe

def team_stats(team: str, matches: list[dict]) -> dict:
    games = sorted((m for m in matches if is_played(m) and team in (m["home"], m["away"])),
                   key=lambda m: m["date"])

    def block(subset):
        n = len(subset)
        w = d = l = gf = ga = cs = fts = btts = o25 = 0
        for m in subset:
            home = m["home"] == team
            f, a = (m["hg"], m["ag"]) if home else (m["ag"], m["hg"])
            gf += f
            ga += a
            w += f > a
            d += f == a
            l += f < a
            cs += a == 0
            fts += f == 0
            btts += f > 0 and a > 0
            o25 += f + a > 2
        pct = (lambda x: round(x / n, 3)) if n else (lambda x: 0)
        return {"played": n, "won": w, "draw": d, "lost": l, "gf": gf, "ga": ga,
                "points": 3 * w + d, "ppg": round((3 * w + d) / n, 2) if n else 0,
                "gf_avg": round(gf / n, 2) if n else 0, "ga_avg": round(ga / n, 2) if n else 0,
                "clean_sheets": pct(cs), "failed_to_score": pct(fts),
                "btts": pct(btts), "over25": pct(o25)}

    form = []
    for m in games[-5:]:
        home = m["home"] == team
        f, a = (m["hg"], m["ag"]) if home else (m["ag"], m["hg"])
        form.append({"r": "W" if f > a else "D" if f == a else "L",
                     "opp": m["away"] if home else m["home"], "venue": "D" if home else "E",
                     "score": f"{f}-{a}", "date": m["date"][:10]})

    return {"all": block(games),
            "home": block([m for m in games if m["home"] == team]),
            "away": block([m for m in games if m["away"] == team]),
            "last5": block(games[-5:]),
            "form": form}


def compute_table(matches: list[dict], teams: list[str]) -> list[dict]:
    tab = {t: {"team": t, "played": 0, "won": 0, "draw": 0, "lost": 0, "gf": 0, "ga": 0, "points": 0}
           for t in teams}
    for m in matches:
        if not is_played(m):
            continue
        for t, f, a in ((m["home"], m["hg"], m["ag"]), (m["away"], m["ag"], m["hg"])):
            r = tab.setdefault(t, {"team": t, "played": 0, "won": 0, "draw": 0, "lost": 0,
                                   "gf": 0, "ga": 0, "points": 0})
            r["played"] += 1
            r["gf"] += f
            r["ga"] += a
            if f > a:
                r["won"] += 1
                r["points"] += 3
            elif f == a:
                r["draw"] += 1
                r["points"] += 1
            else:
                r["lost"] += 1
    rows = list(tab.values())
    for r in rows:
        r["gd"] = r["gf"] - r["ga"]
    rows.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["team"]))
    for i, r in enumerate(rows, 1):
        r["position"] = i
    return rows


def league_trends(matches: list[dict]) -> dict:
    played = [m for m in matches if is_played(m)]
    n = len(played)
    if not n:
        return {"played": 0}
    return {
        "played": n,
        "goals_avg": round(sum(m["hg"] + m["ag"] for m in played) / n, 2),
        "home_win": round(sum(m["hg"] > m["ag"] for m in played) / n, 3),
        "draw": round(sum(m["hg"] == m["ag"] for m in played) / n, 3),
        "away_win": round(sum(m["hg"] < m["ag"] for m in played) / n, 3),
        "btts": round(sum(m["hg"] > 0 and m["ag"] > 0 for m in played) / n, 3),
        "over25": round(sum(m["hg"] + m["ag"] > 2 for m in played) / n, 3),
    }


# --------------------------------------------------------------------------- Backtest

def backtest(season_matches: list[dict], history: list[dict], min_matchday: int = 5) -> dict:
    """Pour chaque match joué de la saison (après la journée min_matchday), le modèle est
    ré-estimé avec UNIQUEMENT les matchs antérieurs, puis on compare prédiction et résultat."""
    played = sorted((m for m in season_matches if is_played(m)
                     and (m.get("matchday") or 99) > min_matchday), key=lambda m: m["date"])
    if not played:
        return {"n": 0}
    pool = history + season_matches
    cache: dict[str, dict] = {}
    n = hits = o25_hits = btts_hits = 0
    brier = logloss = brier_base = 0.0
    calib = {b: [0, 0.0, 0] for b in range(10)}  # tranche -> [n, somme proba, nb réalisés]
    recent = []
    # baseline : fréquences 1/N/2 observées avant le match
    for m in played:
        day = m["date"][:10]
        if day not in cache:
            cache[day] = fit_strengths(pool, parse_date(day + "T00:00:00Z"),
                                       iterations=30, fit_rho=False)
        p = predict(cache[day], m["home"], m["away"])
        probs = [p["p_home"], p["p_draw"], p["p_away"]]
        outcome = 0 if m["hg"] > m["ag"] else 1 if m["hg"] == m["ag"] else 2
        n += 1
        hits += probs.index(max(probs)) == outcome
        brier += sum((probs[i] - (i == outcome)) ** 2 for i in range(3))
        logloss += -math.log(max(probs[outcome], 1e-9))
        prev = [x for x in pool if is_played(x) and x["date"] < m["date"]]
        if prev:
            f = [sum(x["hg"] > x["ag"] for x in prev), sum(x["hg"] == x["ag"] for x in prev),
                 sum(x["hg"] < x["ag"] for x in prev)]
            base = [v / len(prev) for v in f]
        else:
            base = [0.45, 0.27, 0.28]
        brier_base += sum((base[i] - (i == outcome)) ** 2 for i in range(3))
        o25_hits += (p["over25"] >= 0.5) == (m["hg"] + m["ag"] > 2)
        btts_hits += (p["btts"] >= 0.5) == (m["hg"] > 0 and m["ag"] > 0)
        for i in range(3):
            b = min(int(probs[i] * 10), 9)
            calib[b][0] += 1
            calib[b][1] += probs[i]
            calib[b][2] += i == outcome
        recent.append({"date": m["date"][:10], "home": m["home"], "away": m["away"],
                       "score": f"{m['hg']}-{m['ag']}", "p_home": p["p_home"],
                       "p_draw": p["p_draw"], "p_away": p["p_away"],
                       "hit": probs.index(max(probs)) == outcome})
    return {
        "n": n,
        "accuracy_1x2": round(hits / n, 3),
        "brier": round(brier / n, 4),
        "brier_baseline": round(brier_base / n, 4),
        "logloss": round(logloss / n, 4),
        "accuracy_over25": round(o25_hits / n, 3),
        "accuracy_btts": round(btts_hits / n, 3),
        "calibration": [{"bin": f"{b * 10}-{b * 10 + 10}%", "n": v[0],
                         "predicted": round(v[1] / v[0], 3) if v[0] else None,
                         "observed": round(v[2] / v[0], 3) if v[0] else None}
                        for b, v in calib.items()],
        "recent": recent[-30:][::-1],
    }
