import numpy as np
import pandas as pd

from src.capacity import busy_series, demean, shift_of, slope_se


def test_busy_series_counts_open_jobs():
    # job A minutes 1-3, job B minutes 2-5 (end exclusive)
    b = busy_series(np.array([1, 2]), np.array([4, 6]), 8)
    assert b.tolist() == [0, 1, 2, 2, 1, 1, 0, 0]


def test_busy_series_clips_to_window():
    b = busy_series(np.array([-5]), np.array([100]), 4)
    assert b.tolist() == [1, 1, 1, 1]


def test_shift_of_boundaries():
    assert shift_of(np.array([6, 7, 14, 15, 22, 23, 0])).tolist() == [2, 0, 0, 1, 1, 2, 2]


def test_two_way_fixed_effects_recover_slope():
    # y = 0.04 * x + cell effect + day effect + noise; x is correlated with both effects
    rng = np.random.default_rng(1)
    n = 20000
    cell = rng.integers(0, 50, n)
    day = rng.integers(0, 200, n)
    ce, de = rng.normal(0, 5, 50), rng.normal(0, 3, 200)
    x = 2 * ce[cell] + de[day] + rng.normal(0, 1, n)
    y = 0.04 * x + ce[cell] + de[day] + rng.normal(0, 0.1, n)
    naive = np.polyfit(x, y, 1)[0]
    z = demean(np.c_[x, y], [cell, day])
    b, se = slope_se(z[:, 0], z[:, 1], day)
    assert abs(naive - 0.04) > 0.1  # confounded without fixed effects
    assert abs(b - 0.04) < 3 * se and se < 0.005


def test_demean_single_group_removes_means():
    g = np.array([0, 0, 1, 1])
    z = demean(np.array([1.0, 3.0, 10.0, 14.0]), [g])
    assert np.allclose(z[:, 0], [-1, 1, -2, 2])
    assert pd.Series(z[:, 0]).groupby(g).mean().abs().max() < 1e-12
