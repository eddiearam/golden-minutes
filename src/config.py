"""Shared paths and constants."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
RAW_EMS = RAW / "ems"
CLEAN = DATA / "clean"
OUT = DATA / "out"
DOCS = ROOT / "docs"
WEB_DATA = ROOT / "web" / "public" / "data"

EMS_ID = "76xm-jjuj"
MODZCTA_ID = "pri4-ifjk"
FACDB_ID = "ji82-xba5"
SOCRATA = "https://data.cityofnewyork.us"

YEARS = (2022, 2023, 2024, 2025)
TRAIN_YEARS = (2022, 2023, 2024)
TEST_YEAR = 2025

# NYC (Central Park) for Open-Meteo archive
NYC_LAT, NYC_LON = 40.7812, -73.9665

# Life-threatening = FDNY segments 1-3 (see docs/data_dictionary.md)
LIFE_THREATENING_SEGMENTS = ("1", "2", "3")

# Extreme-duration threshold for any single component (seconds)
MAX_COMPONENT_SECONDS = 3 * 3600
MAX_RESPONSE_SECONDS = 3 * 3600


def app_token() -> str | None:
    """Return NYC_APP_TOKEN from .env or environment, or None if unset/placeholder."""
    tok = os.environ.get("NYC_APP_TOKEN")
    env = ROOT / ".env"
    if not tok and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("NYC_APP_TOKEN="):
                tok = line.split("=", 1)[1].strip()
    placeholders = {"PASTE_TOKEN_HERE", "YOURTOKEN", "YOUR_TOKEN", "TOKEN", "CHANGEME"}
    if not tok or tok.upper() in placeholders:
        return None
    return tok


for p in (RAW_EMS, CLEAN, OUT, DOCS):
    p.mkdir(parents=True, exist_ok=True)
