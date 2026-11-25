"""Milestone 4: forecast hourly life-threatening demand by zip.

Target: count of life-threatening incidents (initial segment 1-3) per MODZCTA per
hour, excluding duplicates, standby and transfer records.

Baseline: mean of the same hour of week over the previous 4 weeks
(lags of 168, 336, 504, 672 hours).

Model: gradient boosting (scikit-learn HistGradientBoostingRegressor, Poisson
loss) with hour, weekday, holiday, weather and lagged demand. All demand lags
are at least 168 h, so the model is a one-week-ahead forecast. Weather uses
observed hourly values (a perfect weather forecast); this is stated as a
limitation.

Train: 2022-2024 (from the fifth week of 2022, once all lags exist). Test: 2025.
"""

from __future__ import annotations

import json

import duckdb
import holidays
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from src.config import CLEAN, OUT, RAW, TEST_YEAR

LAGS = (168, 336, 504, 672)


def demand_panel() -> pd.DataFrame:
    """Complete zip x hour panel of life-threatening counts for 2022-2025."""
    con = duckdb.connect()
    counts = con.execute(
        f"""SELECT modzcta, date_trunc('hour', incident_datetime) AS ts, count(*) AS y
            FROM read_parquet('{CLEAN}/incidents.parquet')
            WHERE life_threatening AND modzcta IS NOT NULL AND NOT f_standby AND NOT f_transfer
            GROUP BY 1, 2"""
    ).df()
    zips = sorted(counts.modzcta.unique())
    hours = pd.date_range("2022-01-01", "2025-12-31 23:00", freq="h")
    idx = pd.MultiIndex.from_product([zips, hours], names=["modzcta", "ts"])
    panel = counts.set_index(["modzcta", "ts"]).reindex(idx, fill_value=0).reset_index()
    panel["y"] = panel["y"].astype("float32")
    return panel


def add_features(panel: pd.DataFrame) -> pd.DataFrame:
    p = panel.sort_values(["modzcta", "ts"]).reset_index(drop=True)
    g = p.groupby("modzcta", sort=False)["y"]
    for lag in LAGS:
        p[f"lag{lag}"] = g.shift(lag).astype("float32")
    p["baseline"] = p[[f"lag{lag}" for lag in LAGS]].mean(axis=1).astype("float32")
    # recent level: mean of the 168 hours ending one week before the target hour
    p["roll168_lag168"] = g.transform(lambda s: s.shift(168).rolling(168, min_periods=84).mean()).astype("float32")
    p["hour"] = p.ts.dt.hour.astype("int8")
    p["dow"] = p.ts.dt.day_of_week.astype("int8")
    p["how"] = (p.dow.astype(int) * 24 + p.hour).astype("int16")
    p["month"] = p.ts.dt.month.astype("int8")
    p["year"] = p.ts.dt.year.astype("int16")
    us = holidays.country_holidays("US", subdiv="NY", years=range(2022, 2026))
    p["holiday"] = p.ts.dt.date.map(lambda d: d in us).astype("int8")
    w = pd.read_parquet(RAW / "weather_hourly.parquet").rename(columns={"time": "ts"})
    w = w.drop_duplicates("ts")
    p = p.merge(w, on="ts", how="left")
    p["zip_code"] = p.modzcta.astype("category").cat.codes.astype("int16")
    return p


FEATURES = [
    "zip_code",
    "hour",
    "dow",
    "how",
    "month",
    "holiday",
    "temperature_2m",
    "precipitation",
    "snowfall",
    "relative_humidity_2m",
    "wind_speed_10m",
    *[f"lag{lag}" for lag in LAGS],
    "baseline",
    "roll168_lag168",
    "zip_rate",
]


def mae(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))


def rmse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean((a - b) ** 2)))


def poisson_deviance(y: np.ndarray, mu: np.ndarray) -> float:
    mu = np.clip(mu, 1e-6, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(y > 0, y * np.log(y / mu), 0.0)
    return float(np.mean(2 * (t - (y - mu))))


def main() -> None:
    p = add_features(demand_panel())
    p = p[p.lag672.notna() & p.roll168_lag168.notna()].copy()
    # zip mean rate from training years only (no test leakage)
    rate = p[p.year < TEST_YEAR].groupby("modzcta").y.mean().rename("zip_rate")
    p = p.join(rate, on="modzcta")
    train, test = p[p.year < TEST_YEAR], p[p.year == TEST_YEAR].copy()

    model = HistGradientBoostingRegressor(
        loss="poisson",
        max_iter=400,
        learning_rate=0.06,
        max_leaf_nodes=63,
        min_samples_leaf=200,
        categorical_features=[FEATURES.index("zip_code")],
        random_state=0,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=20,
    )
    model.fit(train[FEATURES], train.y)
    test["pred"] = model.predict(test[FEATURES]).astype("float32")

    res = {
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "zips": int(p.modzcta.nunique()),
        "train_period": [str(train.ts.min()), str(train.ts.max())],
        "test_period": [str(test.ts.min()), str(test.ts.max())],
        "test_total_calls": float(test.y.sum()),
        "n_iter": int(model.n_iter_),
    }
    levels = {
        "zip_hour": ["modzcta", "ts"],
        "zip_4h_block": ["modzcta", pd.Grouper(key="ts", freq="4h")],
        "city_hour": [pd.Grouper(key="ts", freq="h")],
    }
    for name, keys in levels.items():
        agg = test.groupby(keys)[["y", "pred", "baseline"]].sum()
        y, pr, bl = agg.y.values, agg.pred.values, agg.baseline.values
        m, b = mae(y, pr), mae(y, bl)
        res[f"mae_{name}"] = {
            "model": round(m, 5),
            "baseline": round(b, 5),
            "improvement_pct": round(100 * (b - m) / b, 2),
            "mean_actual": round(float(y.mean()), 5),
            "zero_forecast_mae": round(float(np.abs(y).mean()), 5),
        }
        res[f"rmse_{name}"] = {"model": round(rmse(y, pr), 5), "baseline": round(rmse(y, bl), 5)}
        res[f"poisson_deviance_{name}"] = {
            "model": round(poisson_deviance(y, pr), 5),
            "baseline": round(poisson_deviance(y, bl), 5),
        }
    res["model_beats_baseline"] = res["mae_zip_hour"]["model"] < res["mae_zip_hour"]["baseline"]
    (OUT / "forecast_metrics.json").write_text(json.dumps(res, indent=2))

    keep = ["modzcta", "ts", "how", "y", "pred", "baseline"]
    test[keep].to_parquet(OUT / "forecast_test_2025.parquet", index=False)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
