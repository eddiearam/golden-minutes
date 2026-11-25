"""Milestone 7: precompute every number the web app shows into web/public/data/*.json.

Everything here is read from pipeline outputs in data/clean and data/out.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import duckdb
import numpy as np
import pandas as pd
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from src.config import OUT, RAW, WEB_DATA
from src.geo import hospitals, stations, zips
from src.simulate import DEFAULT_K, apply_savings, load_calls
from src.travel import zip_borough

MIN_N_CELL = 20  # calls per zip x 3-hour window for a map cell
MIN_N_ZIP = 50  # calls per zip for the panel statistics
WINDOW = (-1, 0, 1)


def _r(v: float, d: int = 3) -> float:
    return round(float(v), d)


def dump(name: str, obj) -> None:
    WEB_DATA.mkdir(parents=True, exist_ok=True)
    (WEB_DATA / name).write_text(json.dumps(obj, separators=(",", ":"), allow_nan=False))


def stats(rt: np.ndarray, ch: np.ndarray, dp: np.ndarray, tr: np.ndarray) -> dict:
    return {
        "n": int(len(rt)),
        "median": _r(np.median(rt)),
        "p90": _r(np.quantile(rt, 0.9)),
        "ch": _r(ch.mean()),
        "dp": _r(dp.mean()),
        "tr": _r(tr.mean()),
        "mean": _r(rt.mean()),
    }


def both(df: pd.DataFrame) -> dict:
    return {
        "today": stats(df.rt.values, df.ch.values, df.dp.values, df.tr.values),
        "opt": stats(df.rt_opt.values, df.ch.values, df.dp.values, df.tr_opt.values),
    }


def calls_with_savings() -> dict[str, pd.DataFrame]:
    tm = json.loads((OUT / "travel_model.json").read_text())
    slope = np.array(tm["params"]["min_per_km_by_block"])
    served = np.load(OUT / "served_distance_default.npy")
    out = {}
    for sev, all_calls in (("lt", False), ("all", True)):
        c = load_calls(all_calls=all_calls)
        s = apply_savings(c, served, slope)
        c["tr_opt"] = c.tr - s
        c["rt_opt"] = c.rt - s
        out[sev] = c
    return out


def geometry(zb: pd.Series) -> None:
    feats = json.loads((RAW / "modzcta.geojson").read_text())["features"]
    out, by_boro = [], {}
    for f in feats:
        mz = f["properties"]["modzcta"]
        if mz == "99999":
            continue
        g = shape(f["geometry"])
        boro = zb.get(mz, "UNKNOWN")
        by_boro.setdefault(boro, []).append(g)
        gs = g.simplify(0.00012, preserve_topology=True)
        out.append({"type": "Feature", "properties": {"modzcta": mz, "borough": boro}, "geometry": _round(mapping(gs))})
    dump("zips.geojson", {"type": "FeatureCollection", "features": out})
    bfeats = []
    for b, gs in by_boro.items():
        u = unary_union([g.buffer(0.00025) for g in gs]).buffer(-0.00025).simplify(0.0002)
        bfeats.append({"type": "Feature", "properties": {"borough": b}, "geometry": _round(mapping(u))})
    dump("boroughs.geojson", {"type": "FeatureCollection", "features": bfeats})


def _round(geom: dict) -> dict:
    def rec(x):
        if isinstance(x, (list, tuple)) and x and isinstance(x[0], (int, float)):
            return [round(x[0], 5), round(x[1], 5)]
        return [rec(i) for i in x]

    return {"type": geom["type"], "coordinates": rec(geom["coordinates"])}


def map_layers(calls: dict[str, pd.DataFrame], zip_ids: list[str]) -> dict[str, list[float]]:
    con = duckdb.connect()
    scale = {}
    for sev, c in calls.items():
        con.register("c", c[["modzcta", "how", "rt", "rt_opt"]])
        offs = ", ".join(f"({o})" for o in WINDOW)
        agg = con.execute(
            f"""WITH w AS (SELECT modzcta, ((how + o.off + 168) % 168) AS how, rt, rt_opt
                           FROM c CROSS JOIN (VALUES {offs}) o(off))
                SELECT modzcta, how, count(*) AS n, median(rt) AS today, median(rt_opt) AS opt
                FROM w GROUP BY 1, 2"""
        ).df()
        con.unregister("c")
        idx = pd.MultiIndex.from_product([zip_ids, range(168)], names=["modzcta", "how"])
        agg = agg.set_index(["modzcta", "how"]).reindex(idx)
        n = agg.n.fillna(0).astype(int).values.reshape(len(zip_ids), 168)
        for view in ("today", "opt"):
            v = agg[view].values.reshape(len(zip_ids), 168)
            med = [
                [None if (n[i, h] < MIN_N_CELL or np.isnan(v[i, h])) else _r(v[i, h], 2) for h in range(168)]
                for i in range(len(zip_ids))
            ]
            dump(f"map_{view}_{sev}.json", {"zips": zip_ids, "median": med, "n": n.tolist()})
        ok = agg.today[agg.n >= MIN_N_CELL]
        scale[sev] = [_r(np.quantile(ok, 0.05), 1), _r(np.quantile(ok, 0.95), 1)]
    return scale


def demand(zip_ids: list[str]) -> None:
    f = pd.read_parquet(OUT / "forecast_test_2025.parquet")
    weeks = f[f.modzcta == f.modzcta.iloc[0]].groupby("how").size()  # number of each hour of week in 2025
    g = f.groupby(["modzcta", "how"])[["y", "pred", "baseline"]].sum()
    out = {"zips": zip_ids, "actual": {}, "forecast": {}}
    for z in zip_ids:
        if z not in g.index.get_level_values(0):
            continue
        zz = g.loc[z].reindex(range(168)).fillna(0)
        out["actual"][z] = [_r(v, 3) for v in (zz.y / weeks).values]
        out["forecast"][z] = [_r(v, 3) for v in (zz.pred / weeks).values]
    city = f.groupby("how")[["y", "pred", "baseline"]].sum().reindex(range(168))
    out["city"] = {
        "actual": [_r(v, 2) for v in (city.y / weeks).values],
        "forecast": [_r(v, 2) for v in (city.pred / weeks).values],
        "baseline": [_r(v, 2) for v in (city.baseline / weeks).values],
    }
    dump("demand.json", out)


def main() -> None:
    zb = zip_borough()
    z = zips()
    zip_ids = z.modzcta.tolist()
    geometry(zb)
    calls = calls_with_savings()
    scale = map_layers(calls, zip_ids)
    demand(zip_ids)

    detail = {}
    for zid in zip_ids:
        d = {"borough": zb.get(zid, "UNKNOWN")}
        for sev, c in calls.items():
            cz = c[c.modzcta == zid]
            d[sev] = both(cz) if len(cz) >= MIN_N_ZIP else None
        detail[zid] = d
    dump("zip_detail.json", detail)

    sim = json.loads((OUT / "simulation_results.json").read_text())
    boroughs = []
    for b in sorted(calls["lt"].borough.dropna().unique()):
        boroughs.append({"name": b, **{sev: both(c[c.borough == b]) for sev, c in calls.items()}})
    plans = json.loads((OUT / "staging_plans.json").read_text())
    zc = z.set_index("modzcta")
    dump(
        "staging.json",
        {
            k: {b: [[_r(zc.lon[m], 5), _r(zc.lat[m], 5), m] for m in ms] for b, ms in blocks.items()}
            for k, blocks in plans.items()
        },
    )

    fm = json.loads((OUT / "forecast_metrics.json").read_text())
    tm = json.loads((OUT / "travel_model.json").read_text())
    q = pd.read_csv(OUT / "quality_counts.csv").set_index("rule")
    fs = json.loads((OUT / "findings.json").read_text())
    sens = pd.read_csv(OUT / "sensitivity.csv")
    lt = calls["lt"]
    held = (
        duckdb.connect()
        .execute(
            f"""SELECT avg(f_held::INT) FROM read_parquet('{OUT.parent}/clean/incidents.parquet')
            WHERE rt_ok AND life_threatening AND year(incident_datetime) = 2025"""
        )
        .fetchone()[0]
    )
    summary = {
        "year": 2025,
        "k_default": DEFAULT_K,
        "city": {sev: both(c) for sev, c in calls.items()},
        "boroughs": boroughs,
        "k_results": [{"k": int(k), **{kk: v for kk, v in r["city"].items()}} for k, r in sim["results"].items()],
        "sensitivity": sens[["k", "factor", "value", "median_saved", "p90_saved", "mean_saving_per_call"]]
        .astype({"value": str})
        .to_dict("records"),
        "findings": [{"id": f["id"], "title": f["title"], "text": f["text"]} for f in fs],
        "forecast": {
            "model": fm["mae_zip_hour"]["model"],
            "baseline": fm["mae_zip_hour"]["baseline"],
            "improvement_pct": fm["mae_zip_hour"]["improvement_pct"],
            "block_model": fm["mae_zip_4h_block"]["model"],
            "block_baseline": fm["mae_zip_4h_block"]["baseline"],
        },
        "travel": {
            "mae_min": tm["test_2025"]["mae_min"],
            "r2": tm["test_2025"]["r2"],
            "test_cells": tm["cells_test"],
        },
        "quality": {
            "total_rows": int(q.loc["total_rows", "rows"]),
            "rt_ok": int(q.loc["rt_ok", "rows"]),
            "held_share_lt": _r(held, 4),
        },
        "scale": scale,
        "min_n": MIN_N_CELL,
        "stations": int(len(stations())),
        "hospitals": int(len(hospitals())),
        "generated": datetime.now(UTC).strftime("%Y-%m-%d"),
    }
    assert abs(summary["city"]["lt"]["today"]["n"] - len(lt)) == 0
    dump("summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("city", "scale", "forecast", "travel", "quality")}, indent=1))


if __name__ == "__main__":
    main()
