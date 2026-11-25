"""Capacity: how long ambulances are tied up, how many are busy at once, and what one more free ambulance is worth.

Method
- A job runs from first unit assigned to incident closed in the dispatch system. Every assigned incident
  with a plausible close (after assignment, under 6 h) counts, whatever its severity, because it ties up a unit.
  Only the first unit is recorded, so busy counts are first-unit jobs, not every vehicle on the road.
- Busy ambulances in a borough at minute t = jobs in that borough open at t (difference array, minute steps).
- Effect of load: for each 2025 life-threatening call (and separately other calls) take the number of busy
  ambulances in its borough at the minute it was created. Compare calls in the same borough, year and hour of
  week (removes staffing patterns and the weekly cycle) and on the same day (removes weather, traffic and events
  that hit a whole day). The slope of response on busy count, within those cells, is the minutes added by one
  more busy ambulance. Standard errors are clustered by borough-day.
- Checks: busy count in a different borough as a placebo; slope by year; holdout (fit 2022-2024, check the
  2025 binned relationship).
- Plan levers, priced with that slope (one more ambulance on duty is taken as one fewer busy ambulance):
  extra ambulances per borough and shift; shorter time at hospital, which frees transports/hour x minutes/60
  ambulances (Little's law); job lengths back to 2022.
"""

from __future__ import annotations

import json

import duckdb
import numpy as np
import pandas as pd

from src.config import CLEAN, DOCS, OUT, RAW_EMS, TEST_YEAR, TRAIN_YEARS

CAP = OUT / "capacity"
START = pd.Timestamp("2022-01-01")
MAX_JOB_S = 6 * 3600
BOROUGHS = ["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "RICHMOND / STATEN ISLAND"]
SHIFTS = [("Day", 7, 15), ("Evening", 15, 23), ("Night", 23, 7)]
HOSPITAL_CUTS = (5, 10, 15)


def shift_of(hour: np.ndarray) -> np.ndarray:
    """0 = Day 07-15, 1 = Evening 15-23, 2 = Night 23-07."""
    hour = np.asarray(hour)
    return np.where((hour >= 7) & (hour < 15), 0, np.where((hour >= 15) & (hour < 23), 1, 2))


def busy_series(start_min: np.ndarray, end_min: np.ndarray, n_minutes: int) -> np.ndarray:
    """Number of jobs open at each minute: a job counts from its start minute up to, not including, its end minute."""
    s = np.clip(np.asarray(start_min, dtype=np.int64), 0, n_minutes)
    e = np.clip(np.asarray(end_min, dtype=np.int64), 0, n_minutes)
    d = np.zeros(n_minutes + 1)
    np.add.at(d, s, 1)
    np.add.at(d, e, -1)
    return np.cumsum(d)[:n_minutes]


def demean(values: np.ndarray, groups: list[np.ndarray], iters: int = 10) -> np.ndarray:
    """Remove group means for several sets of fixed effects by alternating projections. values: (n, k)."""
    x = np.array(values, dtype=float, copy=True)
    if x.ndim == 1:
        x = x[:, None]
    codes = [pd.factorize(g)[0] for g in groups]
    for _ in range(iters if len(groups) > 1 else 1):
        for c in codes:
            n = np.bincount(c)
            for j in range(x.shape[1]):
                x[:, j] -= (np.bincount(c, weights=x[:, j]) / n)[c]
    return x


def slope_se(x: np.ndarray, y: np.ndarray, cluster: np.ndarray) -> tuple[float, float]:
    """No-intercept OLS slope of demeaned y on demeaned x, with cluster-robust standard error."""
    sxx = float((x * x).sum())
    b = float((x * y).sum()) / sxx
    e = y - b * x
    c = pd.factorize(cluster)[0]
    score = np.bincount(c, weights=x * e)
    g = len(score)
    se = float(np.sqrt((score**2).sum() * g / max(g - 1, 1)) / sxx)
    return b, se


# ---------------------------------------------------------------- data


def load_jobs(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        f"""
        WITH r AS (
          SELECT incident_id,
                 try_cast(first_assignment_datetime AS TIMESTAMP) ta,
                 try_cast(first_on_scene_datetime AS TIMESTAMP) ts,
                 try_cast(first_to_hosp_datetime AS TIMESTAMP) th,
                 try_cast(first_hosp_arrival_datetime AS TIMESTAMP) thh,
                 try_cast(incident_close_datetime AS TIMESTAMP) tc
          FROM read_parquet('{RAW_EMS}/*.parquet'))
        SELECT k.borough AS b, k.life_threatening AS lt, year(k.incident_datetime) AS y,
               hour(k.incident_datetime) AS hr,
               (isodow(k.incident_datetime) - 1) * 24 + hour(k.incident_datetime) AS how,
               epoch(r.ta) AS ta, epoch(r.tc) AS tc,
               epoch(r.tc - r.ta) / 60 AS job_min,
               CASE WHEN r.ts BETWEEN r.ta AND r.tc THEN epoch(r.ts - r.ta) / 60 END AS to_scene,
               CASE WHEN r.ts BETWEEN r.ta AND r.tc AND r.th BETWEEN r.ts AND r.tc THEN epoch(r.th - r.ts) / 60 END
                 AS on_scene_t,
               CASE WHEN r.th BETWEEN r.ts AND r.tc AND r.thh BETWEEN r.th AND r.tc THEN epoch(r.thh - r.th) / 60 END
                 AS transport,
               CASE WHEN r.thh BETWEEN r.th AND r.tc THEN epoch(r.tc - r.thh) / 60 END AS at_hosp,
               r.thh IS NOT NULL AS transported
        FROM r JOIN read_parquet('{CLEAN}/incidents.parquet') k USING (incident_id)
        WHERE r.ta IS NOT NULL AND r.tc > r.ta AND epoch(r.tc - r.ta) < {MAX_JOB_S} AND k.borough <> 'UNKNOWN'
        """
    ).df()


def load_calls(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        f"""
        SELECT borough AS b, life_threatening AS lt, epoch(incident_datetime) AS t0, year(incident_datetime) AS y,
               (isodow(incident_datetime) - 1) * 24 + hour(incident_datetime) AS how,
               CAST(incident_datetime AS DATE) AS date,
               response_s / 60.0 AS resp, call_handling_s / 60.0 AS ch, dispatch_s / 60.0 AS dp,
               travel_s / 60.0 AS tr, f_held::INT AS held
        FROM read_parquet('{CLEAN}/incidents.parquet')
        WHERE rt_ok AND borough <> 'UNKNOWN'
        """
    ).df()


def busy_by_borough(jobs: pd.DataFrame) -> tuple[dict[str, np.ndarray], int]:
    n_min = int((pd.Timestamp("2026-01-01") - START).total_seconds() // 60)
    t0 = START.timestamp()
    out = {}
    for b, g in jobs.groupby("b"):
        out[b] = busy_series(((g.ta - t0) // 60).values, ((g.tc - t0) // 60).values, n_min)
    return out, n_min


def attach_busy(calls: pd.DataFrame, busy: dict[str, np.ndarray], n_min: int, col: str = "busy", shift_b=None) -> None:
    t0 = START.timestamp()
    idx = ((calls.t0 - t0) // 60).astype(np.int64).clip(0, n_min - 1).values
    vals = np.full(len(calls), np.nan)
    for b in BOROUGHS:
        m = (calls.b == b).values
        src = shift_b[b] if shift_b else b
        vals[m] = busy[src][idx[m]]
    calls[col] = vals


# ---------------------------------------------------------------- analysis


def workload(jobs: pd.DataFrame) -> pd.DataFrame:
    """Per year: jobs, mean job minutes split into stages that add up, unit-hours, ambulances busy on average."""
    rows = []
    for y, g in jobs.groupby("y"):
        complete = g.to_scene.notna()
        tr = g.transported & g.on_scene_t.notna() & g.transport.notna() & g.at_hosp.notna()
        nt = complete & ~g.transported
        # stages that add up to the job: to scene, on scene, transport, at hospital (zero when not transported);
        # non-transports spend on-scene time until close; jobs with no on-scene time count all of it as "to scene"
        to_scene = np.where(complete, g.to_scene, g.job_min)
        on_scene = np.where(tr, g.on_scene_t, np.where(nt, g.job_min - g.to_scene, 0))
        transport = np.where(tr, g.transport, 0)
        at_hosp = np.where(tr, g.at_hosp, 0)
        other = g.job_min - to_scene - on_scene - transport - at_hosp  # transports with a missing stage timestamp
        hours = (pd.Timestamp(f"{y + 1}-01-01") - pd.Timestamp(f"{y}-01-01")).total_seconds() / 3600
        rows.append(
            {
                "year": int(y),
                "jobs": len(g),
                "transported_share": float(g.transported.mean()),
                "job_mean_min": float(g.job_min.mean()),
                "to_scene": float(to_scene.mean()),
                "on_scene": float(on_scene.mean()),
                "transport": float(transport.mean()),
                "at_hospital": float(at_hosp.mean()),
                "other": float(other.mean()),
                "at_hospital_median_transported": float(g.at_hosp[tr].median()),
                "unit_hours": float(g.job_min.sum() / 60),
                "ambulances_busy_avg": float(g.job_min.sum() / 60 / hours),
            }
        )
    return pd.DataFrame(rows)


def effects(calls: pd.DataFrame) -> dict:
    """Within borough x year x hour-of-week and borough x day: minutes per extra busy ambulance."""
    out: dict = {}
    cl = calls.b.astype(str) + "|" + calls.date.astype(str)

    def fe(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
        return demean(
            df[cols].values,
            [
                (df.b.astype(str) + "|" + df.y.astype(str) + "|" + df.how.astype(str)).values,
                (df.b.astype(str) + "|" + df.date.astype(str)).values,
            ],
        )

    for name, m in (("lt", calls["lt"].values), ("other", ~calls["lt"].values)):
        d = calls[m]
        z = fe(d, ["busy", "resp", "ch", "dp", "tr", "held", "busy_other"])
        x = z[:, 0]
        res = {"n": int(len(d)), "busy_sd_within": float(x.std())}
        for j, v in enumerate(["resp", "ch", "dp", "tr", "held"], start=1):
            b, se = slope_se(x, z[:, j], cl[m].values)
            res[v] = {"slope": b, "se": se}
        # placebo: own-borough and other-borough busy together
        X = np.c_[z[:, 0], z[:, 6]]
        beta = np.linalg.lstsq(X, z[:, 1], rcond=None)[0]
        res["placebo"] = {"own": float(beta[0]), "other_borough": float(beta[1])}
        by_b = {}
        for b in BOROUGHS:
            mb = (d.b == b).values
            s, se = slope_se(z[mb, 0], z[mb, 1], cl[m].values[mb])
            by_b[b] = {"slope": s, "se": se, "n": int(mb.sum())}
        res["by_borough"] = by_b
        by_y = {}
        for y in sorted(d.y.unique()):
            my = (d.y == y).values
            s, se = slope_se(z[my, 0], z[my, 1], cl[m].values[my])
            by_y[int(y)] = {"slope": s, "se": se}
        res["by_year"] = by_y
        if name == "lt":
            res["bins"] = binned(z[:, 0], z[:, 1])
        out[name] = res
    return out


BIN_EDGES = [-99, -20, -12, -6, -2, 2, 6, 12, 20, 99]


def binned(x: np.ndarray, y: np.ndarray) -> list[dict]:
    cut = pd.cut(x, BIN_EDGES)
    g = pd.DataFrame({"x": x, "y": y, "c": cut}).groupby("c", observed=True)
    return [
        {"busy_dev": float(r.x), "resp_dev": float(r.y), "n": int(n)}
        for (_, r), n in zip(g[["x", "y"]].mean().iterrows(), g.size(), strict=True)
    ]


def holdout(calls: pd.DataFrame) -> dict:
    """Fit borough slopes on 2022-2024, check them against 2025 within-cell variation."""
    lt = calls[calls["lt"].values]
    groups = lambda d: [  # noqa: E731
        (d.b.astype(str) + "|" + d.y.astype(str) + "|" + d.how.astype(str)).values,
        (d.b.astype(str) + "|" + d.date.astype(str)).values,
    ]
    tr = lt[lt.y.isin(TRAIN_YEARS)]
    te = lt[lt.y == TEST_YEAR]
    ztr = demean(tr[["busy", "resp"]].values, groups(tr))
    zte = demean(te[["busy", "resp"]].values, groups(te))
    slopes = {}
    for b in BOROUGHS:
        m = (tr.b == b).values
        slopes[b] = float((ztr[m, 0] * ztr[m, 1]).sum() / (ztr[m, 0] ** 2).sum())
    pred = np.array([slopes[b] for b in te.b]) * zte[:, 0]
    bins = binned(zte[:, 0], zte[:, 1])
    pb = pd.DataFrame({"p": pred, "c": pd.cut(zte[:, 0], BIN_EDGES)}).groupby("c", observed=True).p.mean().values
    for r, p in zip(bins, pb, strict=True):
        r["predicted"] = float(p)
    obs = np.array([r["resp_dev"] for r in bins])
    w = np.array([r["n"] for r in bins])
    return {
        "train_slopes": slopes,
        "bins_2025": bins,
        "bin_mae_min": float(np.average(np.abs(obs - pb), weights=w)),
        "bin_mae_null_min": float(np.average(np.abs(obs), weights=w)),
        "corr_call_level": float(np.corrcoef(pred, zte[:, 1])[0, 1]),
    }


def plan_inputs(calls: pd.DataFrame, jobs: pd.DataFrame) -> pd.DataFrame:
    """2025, per borough x hour of week: calls per week by class, transports per hour, average busy."""
    c = calls[calls.y == TEST_YEAR]
    weeks = 365 / 7
    a = c.groupby(["b", "how"]).agg(lt_per_week=("lt", "sum"), calls_per_week=("lt", "size"))
    a = a / weeks
    j = jobs[jobs.y == TEST_YEAR]
    t = j.groupby(["b", "how"]).agg(transports=("transported", "sum"), jobs=("transported", "size"))
    t = t / weeks  # per hour slot per week = per hour on that weekday-hour
    busy = c[c["lt"]].groupby(["b", "how"]).busy.mean().rename("busy_at_lt_calls")
    out = a.join(t).join(busy).reset_index()
    out["shift"] = shift_of(out.how.values % 24)
    return out


def levers(eff: dict, inp: pd.DataFrame, wl_b: pd.DataFrame) -> dict:
    """Price each lever in minutes saved per call, using borough slopes."""
    s_lt = {b: eff["lt"]["by_borough"][b]["slope"] for b in BOROUGHS}
    s_ot = {b: eff["other"]["by_borough"][b]["slope"] for b in BOROUGHS}
    inp = inp.copy()
    inp["s_lt"] = inp.b.map(s_lt)
    inp["s_ot"] = inp.b.map(s_ot)
    inp["ot_per_week"] = inp.calls_per_week - inp.lt_per_week

    # one extra ambulance on one shift, every day: minutes saved per week
    g = inp.groupby(["b", "shift"]).agg(
        lt_calls=("lt_per_week", "sum"), ot_calls=("ot_per_week", "sum"), s_lt=("s_lt", "first"), s_ot=("s_ot", "first")
    )
    g["lt_min_per_week"] = g.lt_calls * g.s_lt
    g["ot_min_per_week"] = g.ot_calls * g.s_ot
    g["lt_sec_per_call"] = g.s_lt * 60
    one = g.reset_index().sort_values("lt_min_per_week", ascending=False)
    one["shift_name"] = [SHIFTS[s][0] for s in one["shift"]]

    # hospital turnaround: cut of m minutes frees transports/hour x m/60 ambulances in that hour
    hosp = {}
    lt_tot = inp.lt_per_week.sum()
    for m in HOSPITAL_CUTS:
        freed = inp.transports * m / 60
        sav = freed * inp.s_lt
        peak = inp[(inp.how % 24 >= 15) & (inp.how % 24 < 19) & (inp.how < 120)]
        hosp[m] = {
            "lt_sec_per_call": float((sav * inp.lt_per_week).sum() / lt_tot * 60),
            "ambulances_freed_avg": float(freed.groupby(inp.how).sum().mean()),
            "ambulances_freed_weekday_15_19": float((peak.transports * m / 60).groupby(peak.how).sum().mean()),
        }

    # job lengths back to 2022: Little's law per borough
    d_job = (
        wl_b.set_index(["b", "year"]).job_mean_min.unstack()[TEST_YEAR]
        - wl_b.set_index(["b", "year"]).job_mean_min.unstack()[2022]
    )
    freed = inp.jobs * inp.b.map(d_job) / 60
    back2022 = {
        "job_minutes_longer_by_borough": {b: float(v) for b, v in d_job.items()},
        "ambulances_freed_avg": float(freed.groupby(inp.how).sum().mean()),
        "ambulances_freed_weekday_15_19": float(
            freed[(inp.how % 24 >= 15) & (inp.how % 24 < 19) & (inp.how < 120)].groupby(inp.how).sum().mean()
        ),
        "lt_sec_per_call": float((freed * inp.s_lt * inp.lt_per_week).sum() / lt_tot * 60),
    }
    return {"one_ambulance": one, "hospital": hosp, "back_to_2022": back2022}


def explain_rise(calls: pd.DataFrame, eff: dict) -> dict:
    """How much of the 2022 -> 2025 life-threatening slowdown the rise in busy ambulances accounts for."""
    lt = calls[calls["lt"].values]
    out = {}
    for b in BOROUGHS:
        g = lt[lt.b == b]
        y22, y25 = g[g.y == 2022], g[g.y == TEST_YEAR]
        db = y25.busy.mean() - y22.busy.mean()
        out[b] = {
            "busy_2022": float(y22.busy.mean()),
            "busy_2025": float(y25.busy.mean()),
            "resp_mean_change": float(y25.resp.mean() - y22.resp.mean()),
            "predicted_from_busy": float(db * eff["lt"]["by_borough"][b]["slope"]),
        }
    w22 = lt[lt.y == 2022].b.value_counts()
    w25 = lt[lt.y == TEST_YEAR].b.value_counts()
    w = (w22 + w25) / (w22 + w25).sum()
    out["CITY"] = {
        "resp_mean_change": float(lt[lt.y == TEST_YEAR].resp.mean() - lt[lt.y == 2022].resp.mean()),
        "predicted_from_busy": float(sum(w[b] * out[b]["predicted_from_busy"] for b in BOROUGHS)),
    }
    return out


def main() -> None:
    CAP.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    jobs = load_jobs(con)
    calls = load_calls(con)
    busy, n_min = busy_by_borough(jobs)
    attach_busy(calls, busy, n_min)
    other = {
        "BRONX": "RICHMOND / STATEN ISLAND",
        "RICHMOND / STATEN ISLAND": "BRONX",
        "MANHATTAN": "QUEENS",
        "QUEENS": "MANHATTAN",
        "BROOKLYN": "BRONX",
    }
    attach_busy(calls, busy, n_min, col="busy_other", shift_b=other)

    wl = workload(jobs)
    wl_b = pd.concat([workload(g).assign(b=b) for b, g in jobs.groupby("b")])
    eff = effects(calls)
    hold = holdout(calls)
    inp = plan_inputs(calls, jobs)
    lev = levers(eff, inp, wl_b)
    rise = explain_rise(calls, eff)

    # hourly busy profile 2025 (average weekday / weekend) per borough for the app
    hb = []
    t0 = START.timestamp()
    idx = pd.date_range(START, periods=n_min // 60, freq="h")
    m25 = idx.year == TEST_YEAR
    for b in BOROUGHS:
        hourly = busy[b][: (n_min // 60) * 60].reshape(-1, 60).mean(1)
        s = pd.Series(hourly[m25], index=idx[m25])
        how = (s.index.day_of_week * 24 + s.index.hour).values
        prof = s.groupby(how).mean()
        hb.append({"b": b, "busy": [round(float(v), 2) for v in prof.reindex(range(168)).values]})
    del t0

    wl.to_csv(CAP / "workload_by_year.csv", index=False)
    wl_b.to_csv(CAP / "workload_by_borough_year.csv", index=False)
    inp.to_csv(CAP / "plan_inputs_2025.csv", index=False)
    lev["one_ambulance"].to_csv(CAP / "one_ambulance_per_shift.csv", index=False)
    result = {
        "effects": eff,
        "holdout": hold,
        "hospital": lev["hospital"],
        "back_to_2022": lev["back_to_2022"],
        "rise": rise,
        "busy_profile_2025": hb,
        "shifts": [{"name": n, "start": s, "end": e} for n, s, e in SHIFTS],
    }
    (CAP / "capacity_results.json").write_text(json.dumps(result, indent=1, default=float))
    write_doc(wl, wl_b, eff, hold, lev, rise)
    print(
        json.dumps(
            {
                "lt_slope": eff["lt"]["resp"],
                "placebo": eff["lt"]["placebo"],
                "holdout_mae": [hold["bin_mae_min"], hold["bin_mae_null_min"]],
                "hospital": lev["hospital"],
                "back_to_2022": lev["back_to_2022"],
                "rise": rise["CITY"],
            },
            indent=1,
            default=float,
        )
    )


def write_doc(wl, wl_b, eff, hold, lev, rise) -> None:
    f1 = lambda v: f"{v:.1f}"  # noqa: E731
    lines = ["# Capacity: job length, busy ambulances and what one more free ambulance is worth", ""]
    lines += ["Generated by `src/capacity.py`. Jobs run from first unit assigned to incident closed.", ""]
    lines += ["## Job length and workload by year", ""]
    lines += [
        "| Year | Jobs | Transported | Mean job (min) | To scene | On scene | Transport | At hospital | Other |"
        " Median at hospital (transports) | Ambulances busy on average |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in wl.itertuples():
        lines.append(
            f"| {r.year} | {r.jobs:,} | {r.transported_share:.1%} | {f1(r.job_mean_min)} | {f1(r.to_scene)} |"
            f" {f1(r.on_scene)} | {f1(r.transport)} | {f1(r.at_hospital)} | {f1(r.other)} |"
            f" {f1(r.at_hospital_median_transported)} | {f1(r.ambulances_busy_avg)} |"
        )
    lines += ["", "## Effect of one more busy ambulance (within borough x year x hour of week and borough x day)", ""]
    for k, lab in (("lt", "Life-threatening"), ("other", "Other calls")):
        e = eff[k]
        lines.append(f"**{lab}** ({e['n']:,} calls; within-cell SD of busy ambulances {e['busy_sd_within']:.1f}):")
        lines.append("")
        lines.append("| Outcome | Minutes per extra busy ambulance | 95% CI |")
        lines.append("|---|---|---|")
        for v, name in (
            ("resp", "Response"),
            ("ch", "Call handling"),
            ("dp", "Dispatch"),
            ("tr", "Travel"),
            ("held", "Held (share)"),
        ):
            s, se = e[v]["slope"], e[v]["se"]
            lines.append(f"| {name} | {s:.4f} | {s - 1.96 * se:.4f} to {s + 1.96 * se:.4f} |")
        lines.append("")
        lines.append(
            f"Placebo: own-borough busy {e['placebo']['own']:.4f}, other-borough busy "
            f"{e['placebo']['other_borough']:.4f} min per ambulance."
        )
        lines.append("")
        lines.append("| Borough | Slope | 95% CI |")
        lines.append("|---|---|---|")
        for b, r in e["by_borough"].items():
            lines.append(
                f"| {b.title()} | {r['slope']:.4f} | {r['slope'] - 1.96 * r['se']:.4f} to "
                f"{r['slope'] + 1.96 * r['se']:.4f} |"
            )
        lines.append("")
        lines.append("By year: " + ", ".join(f"{y} {r['slope']:.4f}" for y, r in e["by_year"].items()))
        lines.append("")
    lines += ["## Holdout: slopes fitted on 2022-2024, checked on 2025", ""]
    lines += [
        "| Busy ambulances vs usual | Calls | Observed change in response (min) | Predicted |",
        "|---|---|---|---|",
    ]
    for r in hold["bins_2025"]:
        lines.append(f"| {r['busy_dev']:+.1f} | {r['n']:,} | {r['resp_dev']:+.3f} | {r['predicted']:+.3f} |")
    lines += [
        "",
        f"Weighted error across bins {hold['bin_mae_min']:.3f} min, against {hold['bin_mae_null_min']:.3f} for"
        " assuming no effect.",
        "",
    ]
    lines += ["## Levers (life-threatening seconds saved per call, 2025)", ""]
    lines += [
        "| Hospital time cut | Ambulances freed on average | Weekday 15:00-19:00 | Seconds per life-threatening call |",
        "|---|---|---|---|",
    ]
    for m, r in lev["hospital"].items():
        lines.append(
            f"| {m} min | {r['ambulances_freed_avg']:.1f} | {r['ambulances_freed_weekday_15_19']:.1f} |"
            f" {r['lt_sec_per_call']:.1f} |"
        )
    b2 = lev["back_to_2022"]
    lines += [
        "",
        f"Job lengths back to 2022: {b2['ambulances_freed_avg']:.1f} ambulances freed on average,"
        f" {b2['lt_sec_per_call']:.1f} s per life-threatening call.",
        "",
    ]
    lines += [
        "One extra ambulance on one shift every day, ranked by life-threatening minutes saved per week:",
        "",
        "| Borough | Shift | Life-threatening calls per week | Seconds per call | Minutes saved per week |",
        "|---|---|---|---|---|",
    ]
    for r in lev["one_ambulance"].itertuples():
        lines.append(
            f"| {r.b.title()} | {r.shift_name} | {r.lt_calls:.0f} | {r.lt_sec_per_call:.1f} | {r.lt_min_per_week:.0f} |"
        )
    lines += [
        "",
        "## How much of the 2022-2025 slowdown more busy ambulances account for",
        "",
        "| Borough | Busy 2022 | Busy 2025 | Mean response change (min) | Predicted from busy |",
        "|---|---|---|---|---|",
    ]
    for b in BOROUGHS:
        r = rise[b]
        lines.append(
            f"| {b.title()} | {f1(r['busy_2022'])} | {f1(r['busy_2025'])} | {r['resp_mean_change']:+.2f} |"
            f" {r['predicted_from_busy']:+.2f} |"
        )
    c = rise["CITY"]
    lines.append(f"| City | | | {c['resp_mean_change']:+.2f} | {c['predicted_from_busy']:+.2f} |")
    (DOCS / "capacity.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
