"""Milestone 1: download raw data and log row counts.

Sources
- EMS Incident Dispatch Data (76xm-jjuj), 2022-2025, Socrata API paged by month.
- MODZCTA polygons (pri4-ifjk).
- FDNY EMS stations from the DCP Facilities Database (ji82-xba5).
- Hourly weather for NYC from the Open-Meteo historical archive.

Each EMS month is written to data/raw/ems/YYYY-MM.parquet only after every page
for the month has downloaded and the row count matches the API count, so the
script can be re-run safely after an interruption.
"""

from __future__ import annotations

import io
import json
import logging
import sys
import time
from datetime import date

import pandas as pd
import requests

from src.config import (
    DOCS,
    EMS_ID,
    FACDB_ID,
    MODZCTA_ID,
    NYC_LAT,
    NYC_LON,
    OUT,
    RAW,
    RAW_EMS,
    SOCRATA,
    YEARS,
    app_token,
)

PAGE = 50_000
UA = "golden-minutes-research/0.1"
log = logging.getLogger("ingest")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    tok = app_token()
    if tok:
        s.headers["X-App-Token"] = tok
    else:
        log.warning("NYC_APP_TOKEN not set; using unauthenticated (throttled) access")
    return s


def _get(s: requests.Session, url: str, params: dict, tries: int = 8) -> requests.Response:
    for i in range(tries):
        try:
            r = s.get(url, params=params, timeout=180)
            if r.status_code == 200:
                return r
            if r.status_code == 403 and "app_token" in r.text and "X-App-Token" in s.headers:
                log.warning("API rejected NYC_APP_TOKEN; continuing without a token")
                del s.headers["X-App-Token"]
                continue
            log.warning("HTTP %s on %s %s (try %d)", r.status_code, url, params.get("$offset"), i + 1)
        except requests.RequestException as e:  # network hiccup
            log.warning("error %s (try %d)", e, i + 1)
        time.sleep(min(60, 2**i * 2))
    raise RuntimeError(f"failed after {tries} tries: {url} {params}")


def month_bounds(y: int, m: int) -> tuple[str, str]:
    start = date(y, m, 1)
    end = date(y + (m == 12), m % 12 + 1, 1)
    return f"{start.isoformat()}T00:00:00", f"{end.isoformat()}T00:00:00"


def ems_month(s: requests.Session, y: int, m: int) -> int:
    out = RAW_EMS / f"{y}-{m:02d}.parquet"
    if out.exists():
        return pd.read_parquet(out, columns=["incident_id"]).shape[0]
    lo, hi = month_bounds(y, m)
    where = f"incident_datetime >= '{lo}' AND incident_datetime < '{hi}'"
    url = f"{SOCRATA}/resource/{EMS_ID}"
    expected = int(_get(s, url + ".json", {"$select": "count(*)", "$where": where}).json()[0]["count"])
    frames, offset = [], 0
    while offset < expected:
        r = _get(s, url + ".csv", {"$where": where, "$order": "incident_id", "$limit": PAGE, "$offset": offset})
        df = pd.read_csv(io.StringIO(r.text), dtype=str, keep_default_na=False, na_values=[""])
        if df.empty:
            break
        frames.append(df)
        offset += len(df)
    df = pd.concat(frames, ignore_index=True)
    if len(df) != expected:
        raise RuntimeError(f"{y}-{m:02d}: got {len(df)} rows, API count {expected}")
    tmp = out.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.rename(out)
    return len(df)


def ems_all() -> pd.DataFrame:
    s = _session()
    rows = []
    for y in YEARS:
        for m in range(1, 13):
            n = ems_month(s, y, m)
            log.info("EMS %d-%02d: %d rows", y, m, n)
            rows.append({"year": y, "month": m, "rows": n})
    return pd.DataFrame(rows)


def modzcta() -> int:
    out = RAW / "modzcta.geojson"
    if not out.exists():
        r = _get(_session(), f"{SOCRATA}/resource/{MODZCTA_ID}.geojson", {"$limit": 1000})
        out.write_text(r.text)
    n = len(json.loads(out.read_text())["features"])
    log.info("MODZCTA: %d polygons", n)
    return n


def stations() -> int:
    out = RAW / "facdb_ems_stations.json"
    if not out.exists():
        where = "factype in('AMBULANCE STATION','EMERGENCY MEDICAL STATION','EMERGENCY MEDICL STN')"
        r = _get(_session(), f"{SOCRATA}/resource/{FACDB_ID}.json", {"$where": where, "$limit": 1000})
        out.write_text(r.text)
    n = len(json.loads(out.read_text()))
    log.info("FacDB EMS-related facilities: %d records", n)
    return n


def hospitals() -> int:
    out = RAW / "facdb_hospitals.json"
    if not out.exists():
        where = "factype in('HOSPITAL','ACUTE CARE HOSPITAL')"
        r = _get(_session(), f"{SOCRATA}/resource/{FACDB_ID}.json", {"$where": where, "$limit": 1000})
        out.write_text(r.text)
    n = len(json.loads(out.read_text()))
    log.info("FacDB hospitals: %d records", n)
    return n


def weather() -> int:
    out = RAW / "weather_hourly.parquet"
    if not out.exists():
        r = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": NYC_LAT,
                "longitude": NYC_LON,
                "start_date": f"{min(YEARS)}-01-01",
                "end_date": f"{max(YEARS)}-12-31",
                "hourly": "temperature_2m,precipitation,snowfall,relative_humidity_2m,wind_speed_10m",
                "timezone": "America/New_York",
            },
            headers={"User-Agent": UA},
            timeout=300,
        )
        r.raise_for_status()
        h = r.json()["hourly"]
        df = pd.DataFrame(h)
        df["time"] = pd.to_datetime(df["time"])
        df.to_parquet(out, index=False)
    n = pd.read_parquet(out).shape[0]
    log.info("Weather: %d hourly rows", n)
    return n


def write_doc(counts: dict, months: pd.DataFrame) -> None:
    lines = [
        "# Ingest row counts",
        "",
        "Generated by `src/ingest.py`. Each month is saved only when the rows downloaded equal the API's "
        "`count(*)` for that month.",
        "",
        f"- EMS incidents 2022-2025: **{counts['ems_rows_total']:,}** rows",
        f"- MODZCTA polygons: {counts['modzcta_polygons']} (including the 99999 placeholder, excluded later)",
        f"- Facilities Database EMS-related records: {counts['facdb_ems_records']}",
        f"- Facilities Database hospital records: {counts['facdb_hospital_records']}",
        f"- Hourly weather rows: {counts['weather_hours']:,}",
        "",
        "| Year | Rows |",
        "|---|---:|",
        *[f"| {y} | {n:,} |" for y, n in counts["ems_rows_by_year"].items()],
        "",
        "| Month | Rows |",
        "|---|---:|",
        *[f"| {r.year}-{r.month:02d} | {r.rows:,} |" for r in months.itertuples()],
        "",
    ]
    (DOCS / "ingest_row_counts.md").write_text("\n".join(lines))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(OUT / "ingest.log")],
    )
    counts = {
        "modzcta_polygons": modzcta(),
        "facdb_ems_records": stations(),
        "facdb_hospital_records": hospitals(),
        "weather_hours": weather(),
    }
    months = ems_all()
    months.to_csv(OUT / "ingest_row_counts.csv", index=False)
    counts["ems_rows_total"] = int(months["rows"].sum())
    counts["ems_rows_by_year"] = {int(k): int(v) for k, v in months.groupby("year")["rows"].sum().items()}
    (OUT / "ingest_summary.json").write_text(json.dumps(counts, indent=2))
    write_doc(counts, months)
    log.info("done: %s", counts)


if __name__ == "__main__":
    main()
