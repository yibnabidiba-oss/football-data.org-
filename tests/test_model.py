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
