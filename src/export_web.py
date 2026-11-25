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

from src.capacity import BOROUGHS, CAP, shift_of
from src.config import CLEAN, OUT, RAW, TEST_YEAR, WEB_DATA
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


Q_ZIP = np.linspace(0, 1, 41)
Q_BORO = np.linspace(0, 1, 101)


def _comps(c: pd.DataFrame, keys: list[str], qs: np.ndarray) -> list[dict]:
    """One component per group: call count, response quantiles today and with staging, mean stage minutes."""
    out = []
    for k, g in c.groupby(keys, observed=True):
        out.append(
            {
                **dict(zip(keys, k, strict=True)),
                "n": int(len(g)),
                "q": [_r(v, 2) for v in np.quantile(g.rt.values, qs)],
                "qs": [_r(v, 2) for v in np.quantile(g.rt_opt.values, qs)],
                "ch": _r(g.ch.mean()),
                "dp": _r(g.dp.mean()),
                "tr": _r(g.tr.mean()),
                "trs": _r(g.tr_opt.mean()),
            }
        )
    return out


def plan_data(c_all: pd.DataFrame, zip_ok: set[str]) -> None:
    """Inputs for the in-browser plan: response distributions by zip/borough x shift x class, and the capacity
    effects from src/capacity.py that price extra ambulances and faster hospital handover."""
    cap = json.loads((CAP / "capacity_results.json").read_text())
    inp = pd.read_csv(CAP / "plan_inputs_2025.csv")
    one = pd.read_csv(CAP / "one_ambulance_per_shift.csv")
    wl = pd.read_csv(CAP / "workload_by_year.csv")
    c = c_all.copy()
    c["shift"] = shift_of(c.how.values % 24)
    c["cls"] = np.where(c.life_threatening, "lt", "ot")
    boros = BOROUGHS
    c = c[c.borough.isin(boros)]

    inp["ot_per_week"] = inp.calls_per_week - inp.lt_per_week
    tbar = {}
    for b in boros:
        tbar[b] = []
        for s in range(3):
            g = inp[(inp.b == b) & (inp["shift"] == s)]
            tbar[b].append(
                {
                    cl: _r((g[col] * g.transports).sum() / g[col].sum())
                    for cl, col in (("lt", "lt_per_week"), ("ot", "ot_per_week"))
                }
            )
    hours = {b: inp[inp.b == b].set_index("how").reindex(range(168)) for b in boros}

    eff = cap["effects"]

    def slopes(cls: str) -> dict:
        return {
            b: {
                "s": _r(r["slope"], 5),
                "lo": _r(r["slope"] - 1.96 * r["se"], 5),
                "hi": _r(r["slope"] + 1.96 * r["se"], 5),
            }
            for b, r in eff[cls]["by_borough"].items()
        }

    def split(cls: str) -> dict:
        e = eff[cls]
        tot = e["resp"]["slope"]
        return {k: _r(e[k]["slope"] / tot, 4) for k in ("ch", "dp", "tr")}

    held = (
        duckdb.connect()
        .execute(
            f"""SELECT life_threatening, avg(f_held::INT) FROM read_parquet('{CLEAN}/incidents.parquet')
                WHERE rt_ok AND borough <> 'UNKNOWN' AND year(incident_datetime) = {TEST_YEAR} GROUP BY 1"""
        )
        .fetchall()
    )
    held = {("lt" if k else "ot"): _r(v, 4) for k, v in held}

    plan = {
        "boroughs": boros,
        "shifts": cap["shifts"],
        "slope": {"lt": slopes("lt"), "ot": slopes("other")},
        "split": {"lt": split("lt"), "ot": split("other")},
        "held_slope": {"lt": _r(eff["lt"]["held"]["slope"], 5), "ot": _r(eff["other"]["held"]["slope"], 5)},
        "held_2025": held,
        "tbar": tbar,
        "transports": {b: [_r(v, 3) for v in hours[b].transports.fillna(0)] for b in boros},
        "lt_share": {b: [_r(v, 4) for v in (hours[b].lt_per_week / hours[b].calls_per_week).fillna(0)] for b in boros},
        "busy": {r["b"]: r["busy"] for r in cap["busy_profile_2025"]},
        "max_units": 15,
        "max_cut": 15,
        "comps": _comps(c, ["borough", "shift", "cls"], Q_BORO),
        "evidence": {
            "pooled": {
                k: {"s": _r(v["slope"], 5), "se": _r(v["se"], 5)}
                for k, v in eff["lt"].items()
                if k in ("resp", "ch", "dp", "tr", "held")
            },
            "pooled_other": _r(eff["other"]["resp"]["slope"], 5),
            "placebo": {k: _r(v, 5) for k, v in eff["lt"]["placebo"].items()},
            "by_year": {y: _r(v["slope"], 5) for y, v in eff["lt"]["by_year"].items()},
            "holdout": [{k: _r(v, 4) for k, v in r.items()} for r in cap["holdout"]["bins_2025"]],
            "holdout_mae": _r(cap["holdout"]["bin_mae_min"], 4),
            "holdout_mae_null": _r(cap["holdout"]["bin_mae_null_min"], 4),
            "calls": eff["lt"]["n"],
        },
        "workload": [
            {k: (_r(v, 3) if isinstance(v, float) else v) for k, v in r.items()} for r in wl.to_dict("records")
        ],
        "rise": {k: {kk: _r(vv, 3) for kk, vv in v.items()} for k, v in cap["rise"].items()},
        "hospital": {m: {k: _r(v, 2) for k, v in r.items()} for m, r in cap["hospital"].items()},
        "one_ambulance": [
            {
                "b": r.b,
                "shift": int(r.shift),
                "lt_per_week": _r(r.lt_calls, 1),
                "sec": _r(r.lt_sec_per_call, 2),
                "min_per_week": _r(r.lt_min_per_week, 1),
            }
            for r in one.itertuples()
        ],
    }
    dump("plan.json", plan)
    cz = c[c.modzcta.isin(zip_ok)]
    dump("plan_zip.json", _comps(cz, ["modzcta", "shift", "cls"], Q_ZIP))


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
    plan_data(calls["all"], {k for k, v in detail.items() if v["all"] is not None})

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
