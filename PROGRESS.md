# Progress

## Blockers and fallbacks

| Date | Blocker | Fallback chosen |
|---|---|---|
| 2026-11-25 | `.env` holds a placeholder (`YOURTOKEN`), not a real NYC Open Data app token; the API rejects it with 403 "Invalid app_token". | Ingest treats placeholder values as no token and drops the header if the API rejects it, then pages through the API unauthenticated with retries. All rows were still downloaded; it is just slower. Add a real token to `.env` to speed up re-runs. |
| 2026-11-25 | The Socrata API returns 403 to the default `python-requests` User-Agent. | Requests send a generic client name (`golden-minutes-research/0.1`). |
| 2026-11-25 | LightGBM's macOS wheel needs `libomp`, which is not installed, and installing it would touch files outside this folder. | Gradient boosting uses scikit-learn's `HistGradientBoostingRegressor` (same histogram GBM approach, no system library). |
| 2026-11-25 | No published dataset of FDNY EMS station locations. | Station locations come from the NYC Planning Facilities Database (`ji82-xba5`): 34 FDNY-operated sites with "EMS" in the name. The list is incomplete (one Staten Island site). Today's numbers are observed performance; stations are used only as the travel-model reference point. |
| 2026-11-25 | Playwright's bundled browser would download outside this folder. | Screenshots use the installed Google Chrome (`channel: 'chrome'`). |

## Milestones

### 1. Ingest: done (2026-11-25)
- Data dictionary: `docs/data_dictionary.md` (31 source fields from the columns API with official descriptions, derived fields, severity mapping, disposition and call-type codes).
- Downloaded 6,444,090 EMS rows for 2022-2025 (2022: 1,583,531; 2023: 1,617,839; 2024: 1,630,447; 2025: 1,612,273), 48 monthly Parquet files, each checked against the API count. Plus 178 MODZCTA polygons, 66 Facilities Database EMS records, 35,064 hourly weather rows.
- Row counts: `docs/ingest_row_counts.md` and `data/out/ingest.log`.

### 2. Clean: done (2026-11-25)
- `src/clean.py` flags 19 rules (14 exclude a row from response-time analysis, 5 flag only). Report with counts per rule and a first-failing-rule waterfall: `docs/data_quality.md`.
- 6,007,941 of 6,444,090 rows (93.2%) eligible for response-time analysis. Largest exclusions: no unit on scene (222,197 first-failing), no unit assigned (86,631), zero travel time (66,824). No duplicate incident IDs and no unparseable timestamps. 956,055 rows (14.8%) were held calls; kept and flagged.
- Tests: `tests/test_clean.py` covers every rule, component arithmetic, duplicates and the report (21 tests); `pytest` 26 passed; `ruff` clean.
