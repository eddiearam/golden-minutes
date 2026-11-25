import numpy as np
import pandas as pd

from src.forecast import mae
from src.simulate import block_of, solve_pmedian
from src.travel import fit, predict, scores


def test_mae():
    assert mae(np.array([1.0, 2.0, 3.0]), np.array([1.0, 1.0, 5.0])) == 1.0


def test_block_of_hour_of_week():
    # Monday 00:00 -> 0, Monday 23:00 -> 5, Sunday 23:00 -> 41
    assert block_of(np.array([0, 23, 24, 167])).tolist() == [0, 5, 6, 41]


def test_pmedian_picks_heavy_far_zip():
    # three zips; station is at zip 0. Zip 2 is far and has heavy demand.
    xy = np.array([[0.0, 0.0], [1.0, 0.0], [10.0, 0.0]])
    dc = np.hypot(*(xy[:, None, :] - xy[None, :, :]).transpose(2, 0, 1))
    d_sta = dc[:, 0]
    w = np.array([1.0, 1.0, 5.0])
    assert solve_pmedian(w, d_sta, dc, 1) == [2]
    # with two points, both non-station zips are covered
    assert sorted(solve_pmedian(w, d_sta, dc, 2)) == [1, 2]


def test_pmedian_swap_improves_on_greedy():
    # Greedy picks the middle point first; the optimal pair is the two cluster centres.
    pts = np.array([[0.0, 0.0], [0.2, 0.0], [5.0, 0.0], [9.8, 0.0], [10.0, 0.0]])
    dc = np.hypot(*(pts[:, None, :] - pts[None, :, :]).transpose(2, 0, 1))
    d_sta = np.full(len(pts), 50.0)
    w = np.array([1.0, 1.0, 1.5, 1.0, 1.0])
    sel = solve_pmedian(w, d_sta, dc, 2)
    cost = (w * np.minimum(d_sta, dc[:, sel].min(axis=1))).sum()
    brute = min((w * dc[:, [i, j]].min(axis=1)).sum() for i in range(len(pts)) for j in range(len(pts)) if i < j)
    assert np.isclose(cost, brute)


def test_travel_fit_recovers_known_coefficients():
    rng = np.random.default_rng(0)
    n = 600
    df = pd.DataFrame(
        {
            "hb": rng.integers(0, 6, n),
            "d_station_km": rng.uniform(0, 6, n),
            "radius_km": rng.uniform(0.3, 2, n),
            "n": rng.integers(30, 300, n),
            "zborough": "BRONX",
        }
    )
    df["travel_med"] = 3 + 0.2 * df.hb + 1.5 * df.d_station_km + 0.8 * df.radius_km
    beta = fit(df, boroughs=None)
    assert np.allclose(beta[6:12], 1.5, atol=1e-6)
    assert np.isclose(beta[12], 0.8, atol=1e-6)
    s = scores(df.travel_med.values, predict(beta, df, boroughs=None), df.n.values)
    assert s["mae_min"] < 1e-6 and s["r2"] > 0.999999
