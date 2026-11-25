#!/usr/bin/env bash
# Run the full pipeline end to end. Safe to re-run: ingest skips months already cached.
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
$PY -m src.ingest
$PY -m src.dictionary
$PY -m src.clean
$PY -m src.decompose
$PY -m src.forecast
$PY -m src.travel
$PY -m src.simulate
$PY -m src.export_web
# copy small result files into docs/results so they are versioned (data/ is not)
mkdir -p docs/results
cp data/out/{ingest_summary,findings,forecast_metrics,travel_model,simulation_results}.json data/out/sensitivity.csv data/out/quality_counts.csv docs/results/
