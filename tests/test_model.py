import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import model  # noqa: E402


def test_markets_sum_to_one():
    p = model.markets(1.6, 1.1, -0.05)
    assert abs(p["p_home"] + p["p_draw"] + p["p_away"] - 1) < 1e-9
    assert 0 < p["over25"] < 1 and 0 < p["btts"] < 1
    assert p["p_home"] > p["p_away"]


def test_symmetry():
    p = model.markets(1.3, 1.3)
    assert abs(p["p_home"] - p["p_away"]) < 1e-9


def test_fit_recovers_strengths():
    rng = random.Random(1)
    teams = [str(i) for i in range(10)]
    att = {t: math.exp(rng.gauss(0, 0.3)) for t in teams}
    dfn = {t: math.exp(rng.gauss(0, 0.2)) for t in teams}
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    matches, k = [], 0
    for rep in range(12):
        for h in teams:
            for a in teams:
                if h == a:
                    continue
                lh, la = 1.5 * att[h] * dfn[a], 1.1 * att[a] * dfn[h]
                matches.append({"date": (start + timedelta(hours=k)).isoformat(), "home": h,
                                "away": a, "hg": _pois(lh, rng), "ag": _pois(la, rng)})
                k += 1
    p = model.fit_strengths(matches, start + timedelta(days=60), decay=0, prior=0)
    # corrélation entre forces réelles et estimées
    assert _corr([att[t] for t in teams], [p["att"][t] for t in teams]) > 0.9
    assert _corr([dfn[t] for t in teams], [p["def"][t] for t in teams]) > 0.8
    assert abs(p["mu_home"] - 1.5 * _gm(att) * _gm(dfn)) < 0.2


def test_backtest_uses_only_past_data():
    m = [{"date": "2026-08-20T15:00:00Z", "matchday": 6, "home": "a", "away": "b", "hg": 9, "ag": 0}]
    bt = model.backtest(m, [])
    # aucun match antérieur : le modèle ne peut pas "connaître" le 9-0
    assert bt["n"] == 1 and bt["recent"][0]["p_home"] < 0.6


def _pois(lam, rng):
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p < l:
            return k
        k += 1


def _gm(d):
    return math.exp(sum(math.log(v) for v in d.values()) / len(d))


def _corr(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return cov / math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))


def test_implied_odds_remove_margin():
    import history
    o = history.implied(2.0, 3.4, 4.0, 1.9, 1.9)
    assert abs(o["p_home"] + o["p_draw"] + o["p_away"] - 1) < 1e-3
    assert o["p_home"] > o["p_away"] and abs(o["over25"] - 0.5) < 1e-3


def test_name_mapping_from_common_matches():
    import history
    fd = [{"date": f"2026-09-{d:02d}T15:00:00Z", "home": h, "away": a, "hg": hg, "ag": ag}
          for d, h, a, hg, ag in [(1, "1", "2", 2, 0), (8, "2", "3", 1, 1), (15, "3", "1", 0, 3), (22, "1", "3", 4, 2), (29, "2", "1", 0, 1)]]
    co = [{"date": f"2026-09-{d:02d}T15:00:00Z", "home_name": h, "away_name": a, "hg": hg, "ag": ag}
          for d, h, a, hg, ag in [(1, "Paris SG", "Lyon", 2, 0), (8, "Lyon", "Nice", 1, 1), (15, "Nice", "Paris SG", 0, 3), (22, "Paris SG", "Nice", 4, 2), (29, "Lyon", "Paris SG", 0, 1)]]
    assert history.build_mapping(co, fd) == {"Paris SG": "1", "Lyon": "2", "Nice": "3"}


def test_elo_seasons_promoted_team_starts_low():
    # saison 1 : a > b > c > d > e (le plus fort gagne toujours)
    order = ["a", "b", "c", "d", "e"]
    s1, k = [], 0
    for i, h in enumerate(order):
        for j, a in enumerate(order):
            if h != a:
                k += 1
                s1.append({"date": f"2025-01-01T00:00:00Z".replace("01T00", f"{1 + k % 28:02d}T{k % 24:02d}"),
                           "home": h, "away": a, "hg": 2 if i < j else 0, "ag": 0 if i < j else 2})
    s2 = [{"date": "2026-08-01T15:00:00Z", "home": "x", "away": "a", "hg": 0, "ag": 1}]
    r = model.elo_seasons([s1, s2])
    assert r["x"] < 1500 < r["a"]
