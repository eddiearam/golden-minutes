"""Milestone 6: choose K staging points and simulate the effect on 2025 calls.

Method
- Hour-of-week blocks: 7 days x 6 four-hour blocks = 42 blocks.
- Demand weight for each zip and block = forecast life-threatening calls for 2025
  (src/forecast.py output), summed over the hours in the block.
- Candidates: the interior point of each of the 177 MODZCTAs.
- Objective (demand-weighted p-median): minimise sum over zips of
  demand x modelled travel, where a zip is served from the nearer of its nearest
  EMS station and its nearest staging point. Only the distance term of the
  travel model changes, so the objective is sum(w * b[block] * distance).
  Solved per block by greedy addition followed by pairwise swaps until no swap helps.
- Effect on a call = b[block] x (station distance - served distance) minutes,
  subtracted from the call's observed travel time (never below 1 minute of travel).
  Today = observed 2025 response; Optimised = observed minus that saving.

Staging points add coverage on top of current positioning; crew availability,
the knock-on effect of moving units, and unit workload are not modelled. The
availability sensitivity applies each saving to only a random share of calls.
"""

from __future__ import annotations

import json

import duckdb
import numpy as np
import pandas as pd

from src.config import CLEAN, OUT, TEST_YEAR
from src.geo import dist_matrix, nearest_station_km, zips
from src.travel import BLOCKS, zip_borough

KS = (10, 20, 30)
DEFAULT_K = 20
MIN_TRAVEL_MIN = 1.0
N_BLOCKS = 7 * BLOCKS


def block_of(how: np.ndarray) -> np.ndarray:
    how = np.asarray(how)
    return (how // 24) * BLOCKS + (how % 24) // 4


def solve_pmedian(w: np.ndarray, d_sta: np.ndarray, dc: np.ndarray, k: int, max_swaps: int = 400) -> list[int]:
    """Pick k candidate indices minimising sum_i w_i * min(d_sta_i, min_j d_ij).

    w: demand per zip (n), d_sta: distance to nearest station (n),
    dc: zip-to-candidate distance matrix (n x m).
    """
    cur = d_sta.copy()
    chosen: list[int] = []
    for _ in range(k):
        gain = (w[:, None] * np.maximum(cur[:, None] - dc, 0)).sum(axis=0)
        gain[chosen] = -1
        j = int(np.argmax(gain))
        chosen.append(j)
        cur = np.minimum(cur, dc[:, j])

    def cost(sel: list[int]) -> float:
        return float((w * np.minimum(d_sta, dc[:, sel].min(axis=1))).sum())

    best = cost(chosen)
    for _ in range(max_swaps):
        improved = False
        for pos in range(k):
            others = chosen[:pos] + chosen[pos + 1 :]
            base = np.minimum(d_sta, dc[:, others].min(axis=1)) if others else d_sta
            cand = (w[:, None] * np.minimum(base[:, None], dc)).sum(axis=0)
            cand[others] = np.inf
            j = int(np.argmin(cand))
            if cand[j] < best - 1e-9 and j != chosen[pos]:
                chosen[pos], best, improved = j, float(cand[j]), True
        if not improved:
            break
    return chosen


def demand_by_block(source: str) -> pd.DataFrame:
    """Zip x block demand. source: 'forecast' | 'actual' | 'history'."""
    con = duckdb.connect()
    if source in ("forecast", "actual"):
        col = "pred" if source == "forecast" else "y"
        df = con.execute(
            f"SELECT modzcta, how, sum({col}) AS w FROM read_parquet('{OUT}/forecast_test_2025.parquet') GROUP BY 1, 2"
        ).df()
    else:
        df = con.execute(
            f"""SELECT modzcta, (isodow(incident_datetime) - 1) * 24 + hour(incident_datetime) AS how,
                       count(*) / 3.0 AS w
                FROM read_parquet('{CLEAN}/incidents.parquet')
                WHERE life_threatening AND modzcta IS NOT NULL AND NOT f_standby AND NOT f_transfer
                  AND year(incident_datetime) < {TEST_YEAR}
                GROUP BY 1, 2"""
        ).df()
    df["block"] = block_of(df.how.values)
    return df.groupby(["modzcta", "block"]).w.sum().reset_index()


def plan(demand: pd.DataFrame, k: int, per_block: bool = True) -> dict[int, list[int]]:
    z = zips()
    d_sta = nearest_station_km().reindex(z.modzcta).values
    dc = dist_matrix(z.x.values, z.y.values, z.x.values, z.y.values)
    wide = demand.pivot(index="modzcta", columns="block", values="w").reindex(index=z.modzcta, columns=range(N_BLOCKS))
    wide = wide.fillna(0)
    if not per_block:
        sel = solve_pmedian(wide.sum(axis=1).values, d_sta, dc, k)
        return {b: sel for b in range(N_BLOCKS)}
    return {b: solve_pmedian(wide[b].values, d_sta, dc, k) for b in range(N_BLOCKS)}


def served_distance(plans: dict[int, list[int]]) -> np.ndarray:
    """Array (n_zips x N_BLOCKS) of distance to nearest station or staging point."""
    z = zips()
    d_sta = nearest_station_km().reindex(z.modzcta).values
    dc = dist_matrix(z.x.values, z.y.values, z.x.values, z.y.values)
    out = np.empty((len(z), N_BLOCKS))
    for b in range(N_BLOCKS):
        out[:, b] = np.minimum(d_sta, dc[:, plans[b]].min(axis=1))
    return out


def load_calls(lt_col: str = "life_threatening", all_calls: bool = False) -> pd.DataFrame:
    con = duckdb.connect()
    where = "TRUE" if all_calls else lt_col
    df = con.execute(
        f"""SELECT modzcta, borough, life_threatening,
                   (isodow(incident_datetime) - 1) * 24 + hour(incident_datetime) AS how,
                   call_handling_s / 60.0 AS ch, dispatch_s / 60.0 AS dp, travel_s / 60.0 AS tr,
                   response_s / 60.0 AS rt
            FROM read_parquet('{CLEAN}/incidents.parquet')
            WHERE rt_ok AND modzcta IS NOT NULL AND year(incident_datetime) = {TEST_YEAR} AND {where}"""
    ).df()
    df["block"] = block_of(df.how.values)
    return df


def apply_savings(
    calls: pd.DataFrame,
    served: np.ndarray,
    slope: np.ndarray,
    availability: float = 1.0,
    seed: int = 0,
) -> np.ndarray:
    """Per-call saving in minutes."""
    z = zips()
    zi = pd.Series(np.arange(len(z)), index=z.modzcta)
    d_sta = nearest_station_km().reindex(z.modzcta).values
    i = zi.reindex(calls.modzcta).values
    b = calls.block.values
    hb = b % BLOCKS
    save = np.maximum(slope[hb], 0) * (d_sta[i] - served[i, b])
    save = np.minimum(save, np.maximum(calls.tr.values - MIN_TRAVEL_MIN, 0))
    if availability < 1.0:
        rng = np.random.default_rng(seed)
        save = save * (rng.random(len(save)) < availability)
    return save


def summarise(calls: pd.DataFrame, save: np.ndarray) -> dict:
    opt = calls.rt.values - save

    def stats(mask: np.ndarray) -> dict:
        t, o, s = calls.rt.values[mask], opt[mask], save[mask]
        return {
            "calls": int(mask.sum()),
            "today_median": round(float(np.median(t)), 3),
            "today_p90": round(float(np.quantile(t, 0.9)), 3),
            "opt_median": round(float(np.median(o)), 3),
            "opt_p90": round(float(np.quantile(o, 0.9)), 3),
            "median_saved": round(float(np.median(t) - np.median(o)), 3),
            "p90_saved": round(float(np.quantile(t, 0.9) - np.quantile(o, 0.9)), 3),
            "mean_saving_per_call": round(float(s.mean()), 3),
            "share_calls_improved": round(float((s > 0).mean()), 4),
            "total_minutes_saved": round(float(s.sum()), 1),
        }

    res = {"city": stats(np.ones(len(calls), bool))}
    res["borough"] = {b: stats(calls.borough.values == b) for b in sorted(calls.borough.dropna().unique())}
    return res


def main() -> None:
    tm = json.loads((OUT / "travel_model.json").read_text())
    slope = np.array(tm["params"]["min_per_km_by_block"])
    z = zips()
    calls = load_calls()
    demand = demand_by_block("forecast")

    results, plans_out, served_by_k = {}, {}, {}
    for k in KS:
        p = plan(demand, k)
        served = served_distance(p)
        served_by_k[k] = served
        results[str(k)] = summarise(calls, apply_savings(calls, served, slope))
        plans_out[str(k)] = {str(b): [z.modzcta[j] for j in sel] for b, sel in p.items()}
        print(k, results[str(k)]["city"])

    # sensitivity analysis at each K
    sens = []
    for k in KS:
        served = served_by_k[k]
        for a in (0.5, 0.75, 1.0):
            c = summarise(calls, apply_savings(calls, served, slope, availability=a))["city"]
            sens.append({"k": k, "factor": "availability", "value": a, **c})
        for m in (0.75, 1.25):
            c = summarise(calls, apply_savings(calls, served, slope * m))["city"]
            sens.append({"k": k, "factor": "travel_slope_multiplier", "value": m, **c})
        for src in ("actual", "history"):
            sv = served_distance(plan(demand_by_block(src), k))
            c = summarise(calls, apply_savings(calls, sv, slope))["city"]
            sens.append({"k": k, "factor": "demand_input", "value": src, **c})
        sv = served_distance(plan(demand, k, per_block=False))
        c = summarise(calls, apply_savings(calls, sv, slope))["city"]
        sens.append({"k": k, "factor": "plan", "value": "one static plan for all hours", **c})
        calls_f = load_calls("life_threatening_final")
        c = summarise(calls_f, apply_savings(calls_f, served, slope))["city"]
        sens.append({"k": k, "factor": "lt_definition", "value": "final segment 1-3", **c})
    sens_df = pd.DataFrame(sens)
    sens_df.to_csv(OUT / "sensitivity.csv", index=False)

    zb = zip_borough()
    station_d = nearest_station_km()
    (OUT / "simulation_results.json").write_text(
        json.dumps(
            {
                "ks": list(KS),
                "default_k": DEFAULT_K,
                "results": results,
                "slope_min_per_km_by_block": slope.tolist(),
                "zips_with_station_within_1km": int((station_d < 1).sum()),
            },
            indent=2,
        )
    )
    (OUT / "staging_plans.json").write_text(json.dumps(plans_out))
    np.save(OUT / "served_distance_default.npy", served_by_k[DEFAULT_K])
    # per-zip zip-level sanity output
    pd.DataFrame({"modzcta": z.modzcta, "borough": z.modzcta.map(zb), "d_station_km": station_d.values}).to_csv(
        OUT / "zip_station_distance.csv", index=False
    )


if __name__ == "__main__":
    main()
