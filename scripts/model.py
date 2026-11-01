"""Moteur statistique : forces attaque/défense (Poisson + Dixon-Coles), Elo, stats d'équipe.

Aucune dépendance externe. Un match normalisé est un dict :
    {"id", "date" (ISO), "matchday", "status", "home", "away", "hg", "ag"}
"home"/"away" sont des identifiants d'équipe (str). hg/ag = None si pas encore joué.
"""
from __future__ import annotations

import math
from bisect import bisect_left
from datetime import datetime, timedelta, timezone

MAX_GOALS = 10          # taille de la matrice des scores
DECAY_PER_DAY = 0.002   # pondération temporelle (demi-vie ~ 350 jours, réglé sur 2024-26)
PRIOR_MATCHES = 3.0     # régularisation vers la moyenne (en "matchs fictifs")
XG_WEIGHT = 0.7         # part des xG dans la cible quand ils sont disponibles (réglé sur 2024-26)
HISTORY_DAYS = 3 * 365  # matchs pris en compte pour estimer les forces


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


def score_matrix(lh: float, la: float, rho: float = 0.0, draw_k: float = 1.0) -> list[list[float]]:
    """Probabilité de chaque score. draw_k > 1 renforce les nuls (calibré sur l'historique,
    car le modèle de Poisson sous-estime légèrement les matchs nuls)."""
    ph = [poisson_pmf(i, lh) for i in range(MAX_GOALS + 1)]
    pa = [poisson_pmf(j, la) for j in range(MAX_GOALS + 1)]
    mat = [[ph[i] * pa[j] * dc_tau(i, j, lh, la, rho) * (draw_k if i == j else 1.0)
            for j in range(MAX_GOALS + 1)] for i in range(MAX_GOALS + 1)]
    total = sum(sum(r) for r in mat)
    return [[v / total for v in r] for r in mat]


def markets(lh: float, la: float, rho: float = 0.0, draw_k: float = 1.0) -> dict:
    """Toutes les probabilités utiles pour un match."""
    mat = score_matrix(lh, la, rho, draw_k)
    n = len(mat)
    p_home = sum(mat[i][j] for i in range(n) for j in range(n) if i > j)
    p_draw = sum(mat[i][i] for i in range(n))
    p_away = 1 - p_home - p_draw

    def over(line):
        return sum(mat[i][j] for i in range(n) for j in range(n) if i + j > line)

    btts = sum(mat[i][j] for i in range(1, n) for j in range(1, n))
    scores = sorted(((mat[i][j], f"{i}-{j}") for i in range(n) for j in range(n)), reverse=True)
    best = {}
    for p, sc in scores:  # score le plus probable pour chaque issue
        i, j = (int(x) for x in sc.split("-"))
        key = "home" if i > j else "draw" if i == j else "away"
        best.setdefault(key, {"score": sc, "p": round(p, 4)})
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
        "best_by_outcome": best,
    }


# --------------------------------------------------------------------------- Modèle de forces

def fit_strengths(matches: list[dict], ref_date: datetime, teams: list[str] | None = None,
                  decay: float = DECAY_PER_DAY, prior: float = PRIOR_MATCHES,
                  iterations: int = 60, fit_rho: bool = True, xg_weight: float | None = None,
                  fit_draw: bool = True) -> dict:
    """Estime attaque/défense de chaque équipe (modèle de Maher pondéré dans le temps).

    lambda_dom = mu_dom * att[dom] * def[ext]
    lambda_ext = mu_ext * att[ext] * def[dom]
    att > 1 : attaque au-dessus de la moyenne. def > 1 : défense plus perméable que la moyenne.
    """
    xw = XG_WEIGHT if xg_weight is None else xg_weight
    oldest = ref_date - timedelta(days=HISTORY_DAYS)
    played = [m for m in matches if is_played(m) and oldest <= parse_date(m["date"]) < ref_date]
    team_set = set(teams or [])
    for m in played:
        team_set.update((m["home"], m["away"]))
    team_ids = sorted(team_set)

    rows = []
    for m in played:
        days = (ref_date - parse_date(m["date"])).total_seconds() / 86400
        th, ta = m["hg"], m["ag"]
        if xw and m.get("hxg") is not None and m.get("axg") is not None:
            th = (1 - xw) * th + xw * m["hxg"]
            ta = (1 - xw) * ta + xw * m["axg"]
        rows.append((m["home"], m["away"], th, ta, math.exp(-decay * days), m["hg"], m["ag"]))

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
        for h, a, hg, ag, w, _, _ in rows:
            g_for[h] += w * hg
            e_for[h] += w * mu_home * dfn[a]
            g_for[a] += w * ag
            e_for[a] += w * mu_away * dfn[h]
        att = {t: (g_for[t] + prior * m_avg) / (e_for[t] + prior * m_avg) for t in team_ids}
        _normalise(att)

        g_ag = {t: 0.0 for t in team_ids}
        e_ag = {t: 0.0 for t in team_ids}
        for h, a, hg, ag, w, _, _ in rows:
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
            for h, a, _, _, w, hg, ag in rows:
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

    draw_k = fit_draw_k(rows, mu_home, mu_away, att, dfn, rho, ref_date) if fit_draw else 1.0

    return {"mu_home": round(mu_home, 4), "mu_away": round(mu_away, 4), "rho": rho,
            "draw_k": draw_k,
            "n_matches": len(rows),
            "att": {t: round(v, 4) for t, v in att.items()},
            "def": {t: round(v, 4) for t, v in dfn.items()}}


def fit_draw_k(rows, mu_home, mu_away, att, dfn, rho, ref_date, window_days: int = 400) -> float:
    """Coefficient des nuls qui maximise la vraisemblance des résultats 1N2 récents."""
    base = []
    for h, a, _, _, w, hg, ag in rows:
        if w < math.exp(-DECAY_PER_DAY * window_days):
            continue
        mat = score_matrix(mu_home * att[h] * dfn[a], mu_away * att[a] * dfn[h], rho)
        n = len(mat)
        ph = sum(mat[i][j] for i in range(n) for j in range(i))
        pd = sum(mat[i][i] for i in range(n))
        out = 0 if hg > ag else 1 if hg == ag else 2
        base.append((ph, pd, 1 - ph - pd, out, w))
    if len(base) < 100:
        return 1.0
    best = (-math.inf, 1.0)
    for step in range(0, 41):
        k = 0.8 + step * 0.02
        ll = 0.0
        for ph, pd, pa, out, w in base:
            z = ph + k * pd + pa
            ll += w * math.log(max((ph, k * pd, pa)[out] / z, 1e-12))
        if ll > best[0]:
            best = (ll, k)
    return round(best[1], 2)


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
    return markets(lh, la, params.get("rho", 0.0), params.get("draw_k", 1.0))


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


def elo_seasons(seasons: list[list[dict]]) -> dict:
    """Elo sur plusieurs saisons (dans l'ordre). Entre deux saisons, les notes sont ramenées
    vers la moyenne ; un promu démarre à la moyenne des 3 plus faibles de la saison passée."""
    ratings: dict = {}
    prev_teams: set = set()
    for matches in seasons:
        teams = {m["home"] for m in matches} | {m["away"] for m in matches}
        if ratings:
            prev = regress_elo(ratings)
            floor = sorted(prev[t] for t in prev_teams if t in prev)[:3] or [1500.0]
            newcomer = sum(floor) / len(floor)
            ratings = {t: prev[t] if t in prev_teams and t in prev else newcomer for t in teams}
        ratings = elo_ratings(matches, start=ratings)
        prev_teams = teams
    return ratings


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

def backtest(season_matches: list[dict], history: list[dict], min_matchday: int = 5,
             keep_recent: int = 30) -> dict:
    """Pour chaque match joué (après la journée min_matchday), le modèle est ré-estimé avec
    UNIQUEMENT les matchs antérieurs, puis on compare prédiction et résultat. Si le match
    porte des cotes ("odds"), on mesure aussi les bookmakers sur les mêmes matchs."""
    played = sorted((m for m in season_matches if is_played(m)
                     and (m.get("matchday") or 99) > min_matchday), key=lambda m: m["date"])
    if not played:
        return {"n": 0}
    pool = sorted((m for m in history + season_matches if is_played(m)), key=lambda m: m["date"])
    pool_dates = [m["date"] for m in pool]
    # fréquences 1/N/2 cumulées (référence naïve)
    cum = [(0, 0, 0)]
    for m in pool:
        h, d, a = cum[-1]
        cum.append((h + (m["hg"] > m["ag"]), d + (m["hg"] == m["ag"]), a + (m["hg"] < m["ag"])))

    cache: dict[str, dict] = {}
    acc = {"n": 0, "hits": 0, "brier": 0.0, "logloss": 0.0, "brier_base": 0.0, "o25": 0, "btts": 0,
           "bn": 0, "bhits": 0, "bbrier": 0.0, "mbrier_on_b": 0.0, "mhits_on_b": 0}
    calib = {b: [0, 0.0, 0] for b in range(10)}
    recent = []
    for m in played:
        day = m["date"][:10]
        if day not in cache:
            cache[day] = fit_strengths(pool, parse_date(day + "T00:00:00Z"), iterations=30, fit_rho=False)
        p = predict(cache[day], m["home"], m["away"])
        probs = [p["p_home"], p["p_draw"], p["p_away"]]
        outcome = 0 if m["hg"] > m["ag"] else 1 if m["hg"] == m["ag"] else 2
        brier = sum((probs[i] - (i == outcome)) ** 2 for i in range(3))
        hit = probs.index(max(probs)) == outcome
        acc["n"] += 1
        acc["hits"] += hit
        acc["brier"] += brier
        acc["logloss"] += -math.log(max(probs[outcome], 1e-9))
        k = bisect_left(pool_dates, m["date"])
        h, d, a = cum[k]
        base = [h / k, d / k, a / k] if k else [0.45, 0.27, 0.28]
        acc["brier_base"] += sum((base[i] - (i == outcome)) ** 2 for i in range(3))
        acc["o25"] += (p["over25"] >= 0.5) == (m["hg"] + m["ag"] > 2)
        acc["btts"] += (p["btts"] >= 0.5) == (m["hg"] > 0 and m["ag"] > 0)
        o = m.get("odds")
        if o:
            bp = [o["p_home"], o["p_draw"], o["p_away"]]
            acc["bn"] += 1
            acc["bhits"] += bp.index(max(bp)) == outcome
            acc["bbrier"] += sum((bp[i] - (i == outcome)) ** 2 for i in range(3))
            acc["mbrier_on_b"] += brier
            acc["mhits_on_b"] += hit
        for i in range(3):
            b = min(int(probs[i] * 10), 9)
            calib[b][0] += 1
            calib[b][1] += probs[i]
            calib[b][2] += i == outcome
        recent.append({"date": day, "home": m["home"], "away": m["away"],
                       "score": f"{m['hg']}-{m['ag']}", "p_home": p["p_home"],
                       "p_draw": p["p_draw"], "p_away": p["p_away"], "hit": hit,
                       "over25": p["over25"], "btts": p["btts"], "hg": m["hg"], "ag": m["ag"],
                       "odds_raw": m.get("odds_raw")})
    n = acc["n"]
    out = {
        "n": n,
        "accuracy_1x2": round(acc["hits"] / n, 3),
        "brier": round(acc["brier"] / n, 4),
        "brier_baseline": round(acc["brier_base"] / n, 4),
        "logloss": round(acc["logloss"] / n, 4),
        "accuracy_over25": round(acc["o25"] / n, 3),
        "accuracy_btts": round(acc["btts"] / n, 3),
        "calibration": [{"bin": f"{b * 10}-{b * 10 + 10}%", "n": v[0],
                         "predicted": round(v[1] / v[0], 3) if v[0] else None,
                         "observed": round(v[2] / v[0], 3) if v[0] else None}
                        for b, v in calib.items()],
        "recent": recent[-keep_recent:][::-1] if keep_recent else [],
    }
    if acc["bn"]:
        bn = acc["bn"]
        out["bookmakers"] = {"n": bn, "accuracy_1x2": round(acc["bhits"] / bn, 3),
                             "brier": round(acc["bbrier"] / bn, 4),
                             "model_accuracy_1x2": round(acc["mhits_on_b"] / bn, 3),
                             "model_brier": round(acc["mbrier_on_b"] / bn, 4)}
    return out
