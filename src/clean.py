"""Milestone 2: clean EMS incidents and write a data quality report.

Every rule is a boolean flag column so counts can be reported per rule. A row
is eligible for response-time analysis (``rt_ok``) only if it passes all of the
response-time rules. Nothing is deleted from the raw cache.

Response-time components (all from the dataset's own timestamps):
- call_handling_s : incident_datetime          -> first_assignment_datetime
                    (equals DISPATCH_RESPONSE_SECONDS_QY; creation to unit assigned)
- dispatch_s      : first_assignment_datetime  -> first_activation_datetime
                    (unit assigned to unit signals en route)
- travel_s        : first_activation_datetime  -> first_on_scene_datetime
- response_s      : incident_datetime          -> first_on_scene_datetime
                    (equals INCIDENT_RESPONSE_SECONDS_QY)
"""

from __future__ import annotations

import json

import duckdb
import pandas as pd

from src.config import (
    CLEAN,
    DOCS,
    LIFE_THREATENING_SEGMENTS,
    MAX_COMPONENT_SECONDS,
    MAX_RESPONSE_SECONDS,
    OUT,
    RAW,
    RAW_EMS,
)

TS_COLS = [
    "incident_datetime",
    "first_assignment_datetime",
    "first_activation_datetime",
    "first_on_scene_datetime",
    "first_to_hosp_datetime",
    "first_hosp_arrival_datetime",
    "incident_close_datetime",
]

# (flag, description, excludes from response-time analysis?)
RULES = [
    ("f_bad_incident_ts", "incident_datetime missing or unparseable (row dropped)", True),
    ("f_duplicate", "duplicate incident_id (later copies dropped)", True),
    ("f_standby", "standby_indicator = Y (units standing by, not an emergency response)", True),
    ("f_transfer", "transfer_indicator = Y (inter-facility transfer, not a 911 emergency)", True),
    ("f_no_assignment", "no unit ever assigned (first_assignment_datetime missing)", True),
    ("f_no_activation", "no en-route signal (first_activation_datetime missing)", True),
    ("f_no_on_scene", "no unit arrived on scene (first_on_scene_datetime missing)", True),
    ("f_order_assign_before_create", "first unit assigned before incident created", True),
    ("f_order_activation_before_assign", "unit en route before it was assigned", True),
    ("f_order_arrival_before_dispatch", "unit on scene before it was assigned or en route", True),
    ("f_extreme_component", f"a component exceeds {MAX_COMPONENT_SECONDS // 3600} h", True),
    ("f_extreme_response", f"total response exceeds {MAX_RESPONSE_SECONDS // 3600} h", True),
    ("f_zero_travel", "travel time of 0 s (unit on scene at the instant it went en route)", True),
    ("f_dataset_invalid", "dataset's own VALID_INCIDENT_RSPNS_TIME_INDC = N", True),
    ("f_held", "held_indicator = Y (no unit could be assigned immediately); kept, flagged", False),
    ("f_reopen", "reopen_indicator = Y; kept, flagged", False),
    ("f_special_event", "special_event_indicator = Y; kept, flagged", False),
    ("f_qy_mismatch", "computed response differs from INCIDENT_RESPONSE_SECONDS_QY by > 60 s; kept, flagged", False),
    ("f_no_zip", "zip missing or not in MODZCTA (excluded from zip-level results only)", False),
]


def _ts(c: str) -> str:
    return f"TRY_CAST({c} AS TIMESTAMP) AS {c}"


def clean_sql(src: str) -> str:
    """SQL that turns a raw string-typed table/scan ``src`` into a flagged table.

    Expects a table ``zipmap(zip VARCHAR, modzcta VARCHAR)`` to exist.
    """
    ts = ",\n  ".join(_ts(c) for c in TS_COLS)
    sec = lambda a, b: f"date_diff('second', {a}, {b})"  # noqa: E731
    lt = ", ".join(f"'{s}'" for s in LIFE_THREATENING_SEGMENTS)
    return f"""
WITH typed AS (
  SELECT
    incident_id,
  {ts},
    initial_call_type, final_call_type,
    initial_severity_level_code AS init_sev,
    final_severity_level_code  AS final_sev,
    TRY_CAST(incident_response_seconds_qy AS DOUBLE) AS response_qy,
    valid_incident_rspns_time_indc AS valid_rt,
    held_indicator, incident_disposition_code AS disposition,
    upper(trim(borough)) AS borough, incident_dispatch_area AS dispatch_area,
    trim(zipcode) AS zipcode, reopen_indicator, special_event_indicator,
    standby_indicator, transfer_indicator,
    row_number() OVER (PARTITION BY incident_id ORDER BY incident_datetime) AS dup_rank
  FROM {src}
),
comp AS (
  SELECT *,
    {sec("incident_datetime", "first_assignment_datetime")} AS call_handling_s,
    {sec("first_assignment_datetime", "first_activation_datetime")} AS dispatch_s,
    {sec("first_activation_datetime", "first_on_scene_datetime")} AS travel_s,
    {sec("incident_datetime", "first_on_scene_datetime")} AS response_s
  FROM typed
),
flags AS (
  SELECT c.*, z.modzcta,
    incident_datetime IS NULL AS f_bad_incident_ts,
    dup_rank > 1 AS f_duplicate,
    coalesce(standby_indicator = 'Y', false) AS f_standby,
    coalesce(transfer_indicator = 'Y', false) AS f_transfer,
    first_assignment_datetime IS NULL AS f_no_assignment,
    first_activation_datetime IS NULL AS f_no_activation,
    first_on_scene_datetime IS NULL AS f_no_on_scene,
    coalesce(call_handling_s < 0, false) AS f_order_assign_before_create,
    coalesce(dispatch_s < 0, false) AS f_order_activation_before_assign,
    coalesce(first_on_scene_datetime < first_assignment_datetime
             OR first_on_scene_datetime < first_activation_datetime, false) AS f_order_arrival_before_dispatch,
    coalesce(greatest(call_handling_s, dispatch_s, travel_s) > {MAX_COMPONENT_SECONDS}, false) AS f_extreme_component,
    coalesce(response_s > {MAX_RESPONSE_SECONDS}, false) AS f_extreme_response,
    coalesce(travel_s = 0, false) AS f_zero_travel,
    coalesce(valid_rt = 'N', false) AS f_dataset_invalid,
    coalesce(held_indicator = 'Y', false) AS f_held,
    coalesce(reopen_indicator = 'Y', false) AS f_reopen,
    coalesce(special_event_indicator = 'Y', false) AS f_special_event,
    coalesce(abs(response_s - response_qy) > 60, false) AS f_qy_mismatch,
    z.modzcta IS NULL AS f_no_zip,
    init_sev IN ({lt}) AS life_threatening,
    final_sev IN ({lt}) AS life_threatening_final
  FROM comp c LEFT JOIN zipmap z ON c.zipcode = z.zip
)
SELECT *,
  NOT ({" OR ".join(r for r, _, ex in RULES if ex)}) AS rt_ok
FROM flags
"""


def load_zipmap(con: duckdb.DuckDBPyConnection) -> None:
    """Map 5-digit ZCTAs to MODZCTA using the MODZCTA 'zcta' lists."""
    feats = json.loads((RAW / "modzcta.geojson").read_text())["features"]
    rows = []
    for f in feats:
        p = f["properties"]
        mz = p["modzcta"]
        if mz == "99999":
            continue
        for z in (p.get("zcta") or mz).split(","):
            rows.append((z.strip(), mz))
        rows.append((mz, mz))
    zm = pd.DataFrame(rows, columns=["zip", "modzcta"]).drop_duplicates("zip")
    con.register("zipmap_df", zm)
    con.execute("CREATE OR REPLACE TABLE zipmap AS SELECT * FROM zipmap_df")


def quality_counts(con: duckdb.DuckDBPyConnection, table: str) -> pd.DataFrame:
    cols = ", ".join(f"sum({r}::INT) AS {r}" for r, _, _ in RULES)
    row = con.execute(f"SELECT count(*) AS total, {cols}, sum(rt_ok::INT) AS rt_ok FROM {table}").df().iloc[0]
    total = int(row["total"])
    out = [
        {
            "rule": "total_rows",
            "description": "rows downloaded for 2022-2025",
            "rows": total,
            "pct": 100.0,
            "excludes_from_rt": "",
        }
    ]
    for r, d, ex in RULES:
        n = int(row[r])
        out.append(
            {
                "rule": r,
                "description": d,
                "rows": n,
                "pct": round(100 * n / total, 3),
                "excludes_from_rt": "yes" if ex else "no",
            }
        )
    n = int(row["rt_ok"])
    out.append(
        {
            "rule": "rt_ok",
            "description": "eligible for response-time analysis",
            "rows": n,
            "pct": round(100 * n / total, 3),
            "excludes_from_rt": "",
        }
    )
    return pd.DataFrame(out)


def main() -> None:
    con = duckdb.connect()
    con.execute("SET memory_limit='8GB'")
    load_zipmap(con)
    src = f"read_parquet('{RAW_EMS}/*.parquet')"
    con.execute(f"CREATE TABLE flagged AS {clean_sql(src)}")
    q = quality_counts(con, "flagged")
    q.to_csv(OUT / "quality_counts.csv", index=False)

    # first-failing-rule waterfall for the exclusion rules
    excl = [r for r, _, ex in RULES if ex]
    case = " ".join(f"WHEN {r} THEN '{r}'" for r in excl)
    wf = con.execute(
        f"SELECT CASE {case} ELSE 'rt_ok' END AS first_rule, count(*) AS rows FROM flagged GROUP BY 1"
    ).df()
    order = {r: i for i, r in enumerate(excl + ["rt_ok"])}
    wf = wf.sort_values("first_rule", key=lambda s: s.map(order))
    wf.to_csv(OUT / "quality_waterfall.csv", index=False)

    sev = con.execute(
        "SELECT init_sev, count(*) n, sum(rt_ok::INT) n_rt_ok FROM flagged WHERE NOT f_duplicate GROUP BY 1 ORDER BY 1"
    ).df()
    sev.to_csv(OUT / "severity_counts.csv", index=False)

    con.execute(
        f"""COPY (SELECT incident_id, incident_datetime, first_assignment_datetime, first_activation_datetime,
                 first_on_scene_datetime, initial_call_type, final_call_type, init_sev, final_sev,
                 life_threatening, life_threatening_final, borough, dispatch_area, zipcode, modzcta,
                 disposition, call_handling_s, dispatch_s, travel_s, response_s, response_qy,
                 {", ".join(r for r, _, _ in RULES)}, rt_ok
          FROM flagged WHERE NOT f_bad_incident_ts AND NOT f_duplicate ORDER BY incident_datetime)
          TO '{CLEAN}/incidents.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)"""
    )
    write_report(q, wf, sev)
    print(q.to_string(index=False))


def write_report(q: pd.DataFrame, wf: pd.DataFrame, sev: pd.DataFrame) -> None:
    total = int(q.loc[q.rule == "total_rows", "rows"].iloc[0])
    lines = [
        "# Data quality report",
        "",
        "Generated by `src/clean.py` from `data/out/quality_counts.csv` and `data/out/quality_waterfall.csv`.",
        f"Source: EMS Incident Dispatch Data (76xm-jjuj), incidents created 2022-01-01 to 2025-12-31. "
        f"Total rows: {total:,}.",
        "",
        "## Rule counts",
        "",
        "Rules overlap, so counts do not sum. `Excludes` = whether the rule removes the row from "
        "response-time analysis.",
        "",
        "| Rule | Description | Rows | % | Excludes |",
        "|---|---|---:|---:|---|",
    ]
    for _, r in q.iterrows():
        lines.append(f"| `{r.rule}` | {r.description} | {int(r.rows):,} | {r.pct:.2f} | {r.excludes_from_rt} |")
    lines += [
        "",
        "## Exclusion waterfall",
        "",
        "Each row is counted once, under the first exclusion rule it fails (in the order above).",
        "",
        "| First failing rule | Rows | % |",
        "|---|---:|---:|",
    ]
    for _, r in wf.iterrows():
        lines.append(f"| `{r.first_rule}` | {int(r.rows):,} | {100 * r.rows / total:.2f} |")
    lines += [
        "",
        "## Rows by initial severity segment (after de-duplication)",
        "",
        "| Initial segment | Rows | Eligible for response time |",
        "|---|---:|---:|",
    ]
    for _, r in sev.iterrows():
        lines.append(f"| {r.init_sev} | {int(r.n):,} | {int(r.n_rt_ok):,} |")
    (DOCS / "data_quality.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
