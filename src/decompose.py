"""Milestone 3: break response time into call handling, dispatch and travel.

Outputs (data/out/):
- breakdown_borough.csv, breakdown_zip.csv, breakdown_how.csv (hour of week),
  breakdown_severity.csv, breakdown_year.csv, breakdown_zip_how.parquet
- findings.json and docs/findings.md (headline findings with numbers)
"""

from __future__ import annotations

import json

import duckdb
import pandas as pd

from src.config import CLEAN, DOCS, OUT

MIN_N = 20  # minimum calls for a cell to be reported
COMPONENTS = ("call_handling_s", "dispatch_s", "travel_s", "response_s")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET memory_limit='8GB'")
    con.execute(
        f"""CREATE VIEW rt AS SELECT *,
              year(incident_datetime) AS yr,
              (isodow(incident_datetime) - 1) * 24 + hour(incident_datetime) AS how,
              hour(incident_datetime) AS hr,
              isodow(incident_datetime) - 1 AS dow,
              CASE WHEN life_threatening THEN 'life_threatening' ELSE 'other' END AS severity
            FROM read_parquet('{CLEAN}/incidents.parquet') WHERE rt_ok"""
    )
    return con


def agg_sql(group: str, where: str = "TRUE") -> str:
    """Median and p90 (minutes) of each component plus counts, grouped by ``group``."""
    parts = []
    for c in COMPONENTS:
        n = c.removesuffix("_s")
        parts.append(f"round(quantile_cont({c}, 0.5) / 60, 3) AS {n}_med")
        parts.append(f"round(quantile_cont({c}, 0.9) / 60, 3) AS {n}_p90")
        parts.append(f"round(avg({c}) / 60, 3) AS {n}_mean")
    return (
        f"SELECT {group}, count(*) AS n, round(avg(f_held::INT), 4) AS held_share, {', '.join(parts)} "
        f"FROM rt WHERE {where} GROUP BY {group} ORDER BY {group}"
    )


def tables(con: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]:
    sev = "severity"
    out = {
        "breakdown_severity": con.execute(agg_sql("init_sev")).df(),
        "breakdown_year": con.execute(agg_sql(f"yr, {sev}")).df(),
        "breakdown_borough": con.execute(agg_sql(f"yr, borough, {sev}")).df(),
        "breakdown_zip": con.execute(agg_sql(f"yr, modzcta, {sev}", "modzcta IS NOT NULL")).df(),
        "breakdown_how": con.execute(agg_sql(f"yr, how, {sev}")).df(),
        "breakdown_held": con.execute(agg_sql(f"yr, f_held, {sev}")).df(),
    }
    out["breakdown_zip_how"] = con.execute(agg_sql(f"modzcta, how, {sev}", "modzcta IS NOT NULL AND yr = 2025")).df()
    return out


def findings(t: dict[str, pd.DataFrame]) -> list[dict]:
    """Derive headline findings from the breakdown tables. All numbers come from the tables."""
    yr = t["breakdown_year"].set_index(["yr", "severity"])
    a, b = yr.loc[(2022, "life_threatening")], yr.loc[(2025, "life_threatening")]
    deltas = {c: b[f"{c}_med"] - a[f"{c}_med"] for c in ("call_handling", "dispatch", "travel", "response")}
    f1 = {
        "id": "trend",
        "title": "Life-threatening response times, 2022 vs 2025",
        "numbers": {
            "median_2022_min": a.response_med,
            "median_2025_min": b.response_med,
            "p90_2022_min": a.response_p90,
            "p90_2025_min": b.response_p90,
            "median_change_by_component_min": {k: round(v, 3) for k, v in deltas.items()},
            "calls_2022": int(a.n),
            "calls_2025": int(b.n),
        },
    }
    f1["text"] = (
        f"Median response to life-threatening calls was {b.response_med:.1f} min in 2025 "
        f"(90th percentile {b.response_p90:.1f} min) versus {a.response_med:.1f} min "
        f"(p90 {a.response_p90:.1f}) in 2022. Change in the median by component: call handling "
        f"{deltas['call_handling']:+.1f}, dispatch {deltas['dispatch']:+.1f}, travel {deltas['travel']:+.1f} min."
    )

    h = t["breakdown_held"]
    h = h[(h.yr == 2025) & (h.severity == "life_threatening")].set_index("f_held")
    held, notheld = h.loc[True], h.loc[False]
    share = held.n / (held.n + notheld.n)
    # stage means add up to the mean response, so the gap splits exactly by stage
    gaps = {c: float(held[f"{c}_mean"] - notheld[f"{c}_mean"]) for c in ("call_handling", "dispatch", "travel")}
    total_gap = sum(gaps.values())
    top = max(gaps, key=gaps.get)
    names = {"call_handling": "call handling", "dispatch": "dispatch", "travel": "travel"}
    f2 = {
        "id": "held",
        "title": "Held calls and the long tail",
        "numbers": {
            "held_share_2025": round(float(share), 4),
            "held_median_min": held.response_med,
            "held_p90_min": held.response_p90,
            "not_held_median_min": notheld.response_med,
            "not_held_p90_min": notheld.response_p90,
            "mean_gap_min": round(total_gap, 3),
            "mean_gap_by_stage_min": {k: round(v, 3) for k, v in gaps.items()},
            "largest_stage": top,
        },
        "text": (
            f"In 2025, {100 * share:.1f}% of life-threatening calls were held (no unit could be assigned "
            f"immediately). Held calls had a median response of {held.response_med:.1f} min and p90 "
            f"{held.response_p90:.1f} min, against {notheld.response_med:.1f} and {notheld.response_p90:.1f} "
            f"min for calls not held. Of the {total_gap:.1f} min gap in mean response, {gaps[top]:.1f} min "
            f"({100 * gaps[top] / total_gap:.0f}%) is {names[top]}."
        ),
    }

    z = t["breakdown_zip"]
    z = z[(z.yr == 2025) & (z.severity == "life_threatening") & (z.n >= 200)].copy()
    z = z.sort_values("response_med", ascending=False)
    worst, best = z.head(10), z.tail(10)
    hw = t["breakdown_how"]
    hw = hw[(hw.yr == 2025) & (hw.severity == "life_threatening")]
    peak, trough = hw.loc[hw.response_med.idxmax()], hw.loc[hw.response_med.idxmin()]

    def how_label(x: int) -> str:
        return f"{DAYS[int(x) // 24]} {int(x) % 24:02d}:00"

    f3 = {
        "id": "where_when",
        "title": "Where and when it breaks down",
        "numbers": {
            "zips_ranked": int(len(z)),
            "worst10": worst[
                ["modzcta", "n", "response_med", "response_p90", "travel_med", "call_handling_med"]
            ].to_dict("records"),
            "best10_median_of_medians": round(float(best.response_med.median()), 3),
            "worst10_median_of_medians": round(float(worst.response_med.median()), 3),
            "worst10_travel_share": round(float((worst.travel_med / worst.response_med).median()), 3),
            "peak_how": how_label(peak.how),
            "peak_median_min": peak.response_med,
            "peak_p90_min": peak.response_p90,
            "trough_how": how_label(trough.how),
            "trough_median_min": trough.response_med,
        },
        "text": (
            f"Across {len(z)} zips with at least 200 life-threatening calls in 2025, the 10 slowest had a median "
            f"response of {worst.response_med.median():.1f} min versus {best.response_med.median():.1f} min for "
            f"the 10 fastest (slowest: {worst.iloc[0].modzcta}, {worst.iloc[0].response_med:.1f} min). By hour of "
            f"week the slowest hour was {how_label(peak.how)} (median {peak.response_med:.1f} min, p90 "
            f"{peak.response_p90:.1f}) and the fastest {how_label(trough.how)} ({trough.response_med:.1f} min)."
        ),
    }
    return [f1, f2, f3]


def main() -> None:
    con = connect()
    t = tables(con)
    tables_dir = DOCS / "tables"
    tables_dir.mkdir(exist_ok=True)
    for name, df in t.items():
        if name == "breakdown_zip_how":
            df.to_parquet(OUT / f"{name}.parquet", index=False)
        else:
            df.to_csv(OUT / f"{name}.csv", index=False)
            df.to_csv(tables_dir / f"{name}.csv", index=False)
    fs = findings(t)
    (OUT / "findings.json").write_text(json.dumps(fs, indent=2, default=float))
    md = ["# Headline findings (milestone 3)", "", "Generated by `src/decompose.py`; numbers from data/out/*.csv.", ""]
    for i, f in enumerate(fs, 1):
        md += [f"## {i}. {f['title']}", "", f["text"], ""]
    b = t["breakdown_borough"]
    b = b[(b.yr == 2025)]
    md += [
        "## 2025 by borough",
        "",
        "| Borough | Severity | Calls | Median | p90 | Call handling | Dispatch | Travel |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in b.iterrows():
        md.append(
            f"| {r.borough} | {r.severity} | {int(r.n):,} | {r.response_med:.1f} | {r.response_p90:.1f} | "
            f"{r.call_handling_med:.1f} | {r.dispatch_med:.1f} | {r.travel_med:.1f} |"
        )
    md += [
        "",
        "## By initial severity segment (2022-2025)",
        "",
        "| Segment | Calls | Median | p90 | Call handling | Dispatch | Travel |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in t["breakdown_severity"].iterrows():
        md.append(
            f"| {r.init_sev} | {int(r.n):,} | {r.response_med:.1f} | {r.response_p90:.1f} | "
            f"{r.call_handling_med:.1f} | {r.dispatch_med:.1f} | {r.travel_med:.1f} |"
        )
    (DOCS / "findings.md").write_text("\n".join(md) + "\n")
    for f in fs:
        print(f["text"])


if __name__ == "__main__":
    main()
