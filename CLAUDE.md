# Golden Minutes

Goal: find where and when NYC ambulance response times break down, forecast EMS demand by area and hour, and simulate staging idle ambulances to cut response times for life-threatening calls. Deliver a polished interactive web app, a README and a one-page memo.

## Data (real, public, full scale; no synthetic data anywhere)
- EMS Incident Dispatch Data, NYC Open Data id 76xm-jjuj. Read https://data.cityofnewyork.us/api/views/76xm-jjuj/columns.json first and build a data dictionary in docs/. Pull 2022-2025 via the Socrata API with paging, using the app token in .env (NYC_APP_TOKEN). Store as Parquet in data/; query with DuckDB.
- NYC zip geometry: Modified Zip Code Tabulation Areas (MODZCTA) from NYC Open Data.
- Hourly weather: Open-Meteo historical archive for NYC (no key needed).
- If available, EMS station or FDNY facility locations as the baseline for current positioning. If not, document that and use observed performance as the baseline.

## Pipeline (src/)
1. ingest: download, validate, log row counts, cache raw files. Resume safely if interrupted.
2. clean: parse timestamps; drop or flag impossible orders (arrival before dispatch), negative or extreme durations, held calls, duplicates. Write a data quality report with counts for every rule.
3. decompose: response time = call handling + dispatch + travel, using the dataset's own timestamp fields. Compute by zip, borough, hour of week and severity. Define life-threatening calls from the dataset's severity codes and document the mapping.
4. forecast: hourly demand of life-threatening calls by zip. Baseline = same hour over the previous 4 weeks. Model = gradient boosting with hour, weekday, holiday, weather and lagged demand. Train on 2022-2024, test on 2025. Report MAE against the baseline.
5. travel model: calibrate travel minutes from distance between zip centroids and hour of day, fitted on observed travel times. Report the fit.
6. simulate: choose K staging points (K = 10, 20, 30) by demand-weighted optimisation on forecast demand per hour block. Compare against the baseline: median and 90th percentile response for life-threatening calls, minutes saved, and the borough-by-borough split. Include sensitivity analysis.

## App (web/)
- Static site: Vite + React + TypeScript, MapLibre GL for the zip choropleth, D3 or visx for charts. Precompute all data to JSON in web/public/data.
- Layout: top bar with a Today / Optimised staging toggle and minutes saved; centre map of NYC zips with an hour-of-week slider; right panel with the response-time breakdown (call handling, dispatch, travel) for the selected zip plus a borough fairness bar; bottom hour-by-weekday heatmap of actual vs forecast demand.
- Design: Apple-like restraint. Light background, soft shadows on cards and controls only, Inter font, one red accent for delay, generous spacing, smooth transitions, flat high-contrast charts, good on a laptop screen. Must look professionally designed.

## Quality bar
- Every number in the app and memo traces to a script output. No invented figures.
- Tests for cleaning rules and metrics (pytest). Lint passes.
- README.md: problem, data, method, findings with real numbers, limitations (aggregated locations, crew availability not modelled, travel model approximations, reporting artefacts), how to run.
- MEMO.md: one page of findings and recommendations with real numbers, and what the data cannot tell you.
- Do not write that the project was built with AI.

## Working rules
- Work milestone by milestone from PLAN.md. After each: run tests, commit with a clear message, push, and update PROGRESS.md.
- If blocked, write the blocker in PROGRESS.md, choose the most reasonable fallback, and continue. Do not stop until every acceptance check in PLAN.md passes.
- Never delete raw data, never force-push, never touch files outside this folder, never commit .env or the data/ folder.
- Follow DESIGN.md exactly for all UI work, including the Island component and the screenshot review loop.
