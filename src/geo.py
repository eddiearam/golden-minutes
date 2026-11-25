"""Zip geometry, EMS station locations and distances."""

from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import pandas as pd
from shapely.geometry import shape

from src.config import RAW

LAT0 = 40.7128
KM_PER_DEG_LAT = 110.574
KM_PER_DEG_LON = 111.320 * np.cos(np.radians(LAT0))


def to_km(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Local equirectangular projection (km) centred on NYC; error < 0.5% across the city."""
    return (np.asarray(lon) + 74.0) * KM_PER_DEG_LON, (np.asarray(lat) - LAT0) * KM_PER_DEG_LAT


@lru_cache
def zips() -> pd.DataFrame:
    """MODZCTA with a representative interior point, area and equivalent radius (km)."""
    feats = json.loads((RAW / "modzcta.geojson").read_text())["features"]
    rows = []
    for f in feats:
        mz = f["properties"]["modzcta"]
        if mz == "99999":
            continue
        g = shape(f["geometry"])
        # point guaranteed inside the polygon (centroids of odd shapes can fall in water)
        c = g.centroid if g.contains(g.centroid) else g.representative_point()
        area = _area_km2(g)
        rows.append(
            {
                "modzcta": mz,
                "lon": c.x,
                "lat": c.y,
                "area_km2": area,
                "radius_km": float(np.sqrt(area / np.pi)),
                "pop_est": float(f["properties"].get("pop_est") or 0),
            }
        )
    df = pd.DataFrame(rows).sort_values("modzcta").reset_index(drop=True)
    df["x"], df["y"] = to_km(df.lon.values, df.lat.values)
    return df


def _area_km2(g) -> float:
    from shapely.ops import transform

    return transform(lambda x, y, z=None: to_km(x, y), g).area


@lru_cache
def stations() -> pd.DataFrame:
    """FDNY-operated EMS stations from the Facilities Database, one row per location.

    The Facilities Database list is incomplete (for example it has a single Staten Island
    site), so distances to the nearest station overstate true distances in some areas.
    """
    recs = json.loads((RAW / "facdb_ems_stations.json").read_text())
    df = pd.DataFrame(recs)
    # FDNY-operated records whose name identifies an EMS station (drops HQ and non-station sites)
    df = df[df.opname.eq("NYC Fire Department") & df.facname.str.contains("EMS")].copy()
    df["lat"], df["lon"] = df.latitude.astype(float), df.longitude.astype(float)
    df = df.drop_duplicates(subset=["lat", "lon"]).reset_index(drop=True)
    df["x"], df["y"] = to_km(df.lon.values, df.lat.values)
    return df[["facname", "factype", "boro", "zipcode", "lat", "lon", "x", "y"]]


def dist_matrix(ax, ay, bx, by) -> np.ndarray:
    return np.hypot(np.subtract.outer(ax, bx), np.subtract.outer(ay, by))


def nearest_station_km() -> pd.Series:
    z, s = zips(), stations()
    d = dist_matrix(z.x.values, z.y.values, s.x.values, s.y.values)
    return pd.Series(d.min(axis=1), index=z.modzcta, name="d_station_km")
