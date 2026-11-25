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

### 3. Decompose: done (2026-11-25)
- Response = call handling (created → assigned) + dispatch (assigned → en route) + travel (en route → on scene), from the dataset's own timestamps. Life-threatening = initial segment 1-3 (mapping in `docs/data_dictionary.md`).
- Tables by year, borough, zip, hour of week, severity segment and held status: `docs/tables/*.csv`; summary in `docs/findings.md`.
- Headline findings (from `data/out/findings.json`):
  1. Life-threatening median response 7.4 min in 2025 (p90 13.2) vs 6.8 (p90 11.8) in 2022; travel +0.5 min is most of the rise (call handling +0.1, dispatch -0.0).
  2. 5.2% of 2025 life-threatening calls were held; held median 9.5 min (p90 19.6) vs 7.3 (p90 12.9) not held. Of the 3.7 min gap in mean response, 2.2 min (60%) is travel.
  3. Of 173 zips with 200+ life-threatening calls in 2025, the 10 slowest had median 9.4 min vs 5.8 min for the 10 fastest (slowest 10464 at 11.8). Slowest hour of week Fri 18:00 (median 8.6, p90 15.7); fastest Tue 00:00 (6.4).

### 4. Forecast: done (2026-11-25)
- Hourly life-threatening demand for 177 zips. Baseline = mean of the same hour over the previous 4 weeks. Model = scikit-learn HistGradientBoostingRegressor (Poisson loss) with zip, hour, weekday, hour of week, month, NY holidays, hourly weather and demand lags of 1-4 weeks plus a lagged weekly mean (one-week-ahead forecast). Train 2022-01-29 to 2024-12-31 (4,536,864 zip-hours), test 2025 (1,550,520 zip-hours, 597,683 calls).
- 2025 holdout MAE (`docs/results/forecast_metrics.json`): zip-hour 0.445 vs baseline 0.463 (-3.8%); zip x 4 h block 0.930 vs 1.021 (-8.8%); citywide hour 7.60 vs 8.44 (-9.9%). RMSE and Poisson deviance also favour the model (zip-hour deviance 0.80 vs 2.43).
- Caveat recorded: at zip-hour level counts are sparse (mean 0.385), so a forecast of zero would have a lower MAE (0.385) than either; MAE is therefore also reported at block and city level, with RMSE and deviance.
- Fallback: LightGBM unavailable (needs system libomp), so scikit-learn's histogram gradient boosting is used.

### 5. Travel model: done (2026-11-25)
- Form: travel_min = a[4 h block] + b[block] x d_base_km + c x zip radius + borough effect + g x (year - 2022), weighted least squares on median life-threatening travel time per zip x block x year (2022-2024 train, 2025 test). Distance = zip interior point to the nearest FDNY EMS station or hospital.
- Fit (`docs/results/travel_model.json`): train MAE 0.53 min (R² 0.22); 2025 test MAE 0.67 min, RMSE 0.87, bias +0.39 min (2025 travel ran above the 2022-2024 trend), R² 0.01. A reference with no geography (block mean + year trend) scores MAE 0.71 on 2025. Leave-one-borough-out 2025 MAE 0.51-0.92 min.
- Distance effect b = 0.10-0.21 min per km (lowest midday, highest overnight and evening).
- Blocker and fallback: the data has no origin for the responding unit, and station distance alone was a weak proxy (b = -0.00 to 0.07 min/km, test MAE 0.68; kept as `station_only_reference`). Hospitals were added because crews often respond as they clear a hospital. Because the proxy is noisy, b is probably understated; the simulation adds a x2 slope scenario to its sensitivity analysis.

### 6. Simulation: done (2026-11-25)
- Demand-weighted p-median per 4-hour block of the week (42 blocks): candidates are the 177 zip interior points, weights are the 2025 forecast demand, served distance = nearer of nearest EMS station/hospital and nearest staging point. Greedy then pairwise swaps (tested against brute force). Saving per call = travel slope x km closer, applied to each observed 2025 life-threatening call (576,332 calls).
- Results (`docs/simulation.md`, `docs/results/simulation_results.json`), median / p90 minutes saved and share of calls helped: K=10 0.033 / 0.033 (12.9%); K=20 0.067 / 0.067 (24.2%); K=30 0.089 / 0.099 (34.5%). Mean km closer: 0.26 / 0.43 / 0.57. Borough split at K=20, median saved: Staten Island 0.134, Queens 0.128, Brooklyn 0.083, Bronx 0.048, Manhattan 0.009.
- Sensitivity: staged unit free 50% / 75% of the time, travel slope x0.75 / x1.25 / x2, demand from actual 2025 or 2022-2024 history instead of forecast, one static plan for all hours, and the final-segment life-threatening definition. At K=20 the median saved ranges from 0.033 (50% availability) to 0.133 (slope x2); plan choice and demand input change it by under 0.01 min.
- Finding: with travel calibrated on observed data, staging alone moves response times by seconds, not minutes. Most of the citywide gap is not explained by distance from known bases (see milestone 5).
