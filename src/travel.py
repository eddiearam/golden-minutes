"""Milestone 5: calibrate a travel-time model on observed travel times.

The dataset does not say where the responding ambulance came from, so the model
uses the distance from each zip's interior point to the nearest FDNY EMS station
(Facilities Database) as the distance an ambulance typically covers, plus the
zip's own size, hour of day and borough:

    travel_min = a[hour block] + b[hour block] * d_station_km + c * radius_km + borough effect

It is fitted by weighted least squares on the median travel time of
life-threatening calls in each zip x 4-hour block, 2022-2024 (weights = calls),
and validated on 2025 and by leave-one-borough-out.
"""

from __future__ import annotations

import json

import duckdb
import numpy as np
import pandas as pd

from src.config import CLEAN, OUT
from src.geo import nearest_station_km, zips

BLOCKS = 6  # 4-hour blocks of the day
BOROUGHS = ["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "RICHMOND / STATEN ISLAND"]
MIN_CELL_N = 30


def zip_borough() -> pd.Series:
    con = duckdb.connect()
    df = con.execute(
        f"""SELECT modzcta, borough FROM (
              SELECT modzcta, borough, row_number() OVER (PARTITION BY modzcta ORDER BY count(*) DESC) rk
              FROM read_parquet('{CLEAN}/incidents.parquet') WHERE modzcta IS NOT NULL AND borough IS NOT NULL
              GROUP BY 1, 2) WHERE rk = 1"""
    ).df()
    return df.set_index("modzcta").borough


def cells() -> pd.DataFrame:
    con = duckdb.connect()
    df = con.execute(
        f"""SELECT modzcta, CASE WHEN year(incident_datetime) = 2025 THEN 'test' ELSE 'train' END AS split,
                   hour(incident_datetime) // 4 AS hb, count(*) AS n,
                   quantile_cont(travel_s, 0.5) / 60 AS travel_med, avg(travel_s) / 60 AS travel_mean
            FROM read_parquet('{CLEAN}/incidents.parquet')
            WHERE rt_ok AND life_threatening AND modzcta IS NOT NULL
            GROUP BY 1, 2, 3"""
    ).df()
    z = zips().set_index("modzcta")
    df = df.join(nearest_station_km(), on="modzcta").join(z.radius_km, on="modzcta")
    df = df.join(zip_borough().rename("zborough"), on="modzcta")
    return df[df.n >= MIN_CELL_N].reset_index(drop=True)


def design(df: pd.DataFrame, boroughs: list[str] | None = BOROUGHS) -> np.ndarray:
    cols = []
    for h in range(BLOCKS):
        cols.append((df.hb == h).astype(float).values)
    for h in range(BLOCKS):
        cols.append(((df.hb == h) * df.d_station_km).astype(float).values)
    cols.append(df.radius_km.values)
    if boroughs:
        for b in boroughs[1:]:
            cols.append((df.zborough == b).astype(float).values)
    return np.column_stack(cols)


def fit(df: pd.DataFrame, boroughs: list[str] | None = BOROUGHS) -> np.ndarray:
    w = np.sqrt(df.n.values)
    beta, *_ = np.linalg.lstsq(design(df, boroughs) * w[:, None], df.travel_med.values * w, rcond=None)
    return beta


def predict(beta: np.ndarray, df: pd.DataFrame, boroughs: list[str] | None = BOROUGHS) -> np.ndarray:
    return design(df, boroughs) @ beta


def scores(y: np.ndarray, p: np.ndarray, w: np.ndarray) -> dict:
    err = y - p
    r2 = 1 - np.sum(w * err**2) / np.sum(w * (y - np.average(y, weights=w)) ** 2)
    return {
        "mae_min": round(float(np.average(np.abs(err), weights=w)), 4),
        "rmse_min": round(float(np.sqrt(np.average(err**2, weights=w))), 4),
        "bias_min": round(float(np.average(err, weights=w)), 4),
        "r2": round(float(r2), 4),
    }


def params_dict(beta: np.ndarray) -> dict:
    return {
        "intercept_by_block": [round(float(v), 5) for v in beta[:BLOCKS]],
        "min_per_km_by_block": [round(float(v), 5) for v in beta[BLOCKS : 2 * BLOCKS]],
        "min_per_km_radius": round(float(beta[2 * BLOCKS]), 5),
        "borough_effect": {b: round(float(v), 5) for b, v in zip(BOROUGHS[1:], beta[2 * BLOCKS + 1 :], strict=True)},
        "borough_reference": BOROUGHS[0],
        "blocks": [f"{4 * h:02d}:00-{4 * h + 3:02d}:59" for h in range(BLOCKS)],
    }


def main() -> None:
    df = cells()
    tr, te = df[df.split == "train"], df[df.split == "test"]
    beta = fit(tr)
    res = {
        "form": "travel_min = a[block] + b[block]*d_station_km + c*radius_km + borough effect",
        "cells_train": int(len(tr)),
        "cells_test": int(len(te)),
        "calls_train": int(tr.n.sum()),
        "calls_test": int(te.n.sum()),
        "params": params_dict(beta),
        "train": scores(tr.travel_med.values, predict(beta, tr), tr.n.values),
        "test_2025": scores(te.travel_med.values, predict(beta, te), te.n.values),
    }
    # naive reference: overall weighted median travel by block, ignoring distance
    ref = tr.groupby("hb").apply(lambda g: np.average(g.travel_med, weights=g.n), include_groups=False)
    res["test_2025_reference_block_mean"] = scores(te.travel_med.values, te.hb.map(ref).values, te.n.values)
    # spatial check: leave one borough out (no borough effects, so the held-out borough is unseen)
    lobo = {}
    for b in BOROUGHS:
        m = fit(tr[tr.zborough != b], boroughs=None)
        hold = te[te.zborough == b]
        if len(hold):
            lobo[b] = scores(hold.travel_med.values, predict(m, hold, boroughs=None), hold.n.values)
    res["leave_one_borough_out_2025"] = lobo
    (OUT / "travel_model.json").write_text(json.dumps(res, indent=2))
    te = te.assign(pred=predict(beta, te))
    te.to_csv(OUT / "travel_model_test_cells.csv", index=False)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
