# Memo: NYC ambulance response times, 2022-2025

**To:** EMS operations leadership  **Re:** Where response times break down, and whether staging would help

## What we found

1. **Life-threatening calls are getting slower.** Median response (incident created to first unit on scene) rose from 6.8 min in 2022 to 7.4 min in 2025, and the 90th percentile from 11.8 to 13.2 min. That covers 581,682 life-threatening calls in 2025. Travel accounts for +0.5 of the +0.6 min rise, and it makes up 7.1 of the 8.2 min average response.

2. **The real constraint is free units.** The share of life-threatening calls held because no unit could be assigned doubled from 2.5% to 5.2%. For other calls it tripled, from 9.8% to 29.0%, and their median response rose from 9.0 to 12.4 min. Held life-threatening calls had a p90 of 19.6 min, against 12.9 for calls not held, and 60% of that gap is extra travel.

3. **The worst places are at the edges and in the Bronx.** The Bronx had the slowest borough median for life-threatening calls (8.0 min) and the most holds (8.5%). The slowest zips are on the edge of the network: City Island 11.8, Roosevelt Island 10.6, Tottenville 10.1 and College Point 10.0, against 5.8 for the fastest ten. The 15 slowest hours of the week all fall on weekdays between 15:00 and 19:00, the worst being Friday 18:00 (median 8.6, p90 15.7).

4. **Demand can be forecast a week ahead.** A gradient-boosting forecast beat the usual 4-week same-hour average on every 2025 test. Its error was 8.8% lower per zip and 4-hour block, and 9.9% lower per citywide hour.

5. **Staging idle units, on its own, saves seconds.** We placed 10, 20 or 30 staging points using the forecast and tested them on every 2025 life-threatening call. With 20 points, calls are on average 0.43 km closer to a unit and 24% of calls get faster, but the median saving is about 4 s (6 s at 30 points). Staten Island and Queens gain most (8 s each at 20 points), and a few far-flung zips gain much more: Rockaway 11694 and 11693 about 48 s per call, eastern Queens 11428 and 11427 34-42 s, south-east Queens 11434 38 s. Manhattan gains almost nothing. Even if distance matters twice as much as our model estimates, the saving is 8 s.

## Recommendations

1. **Treat unit availability as the main problem.** Holds have doubled and travel rises when they do. Measure free units by hour against forecast demand, and add capacity for the weekday 15:00-19:00 peak before redrawing posts.
2. **Use the demand forecast for weekly tour planning.** It is accurate enough to set staffing by zip block one week ahead.
3. **Target staging narrowly.** Use it only where known bases are far away: the Rockaways, eastern and south-east Queens, and Staten Island, where the model gives 26-48 s per call (`docs/tables/staging_saving_by_zip_k20.csv`). Pilot it as a short, measured trial rather than a citywide change.
4. **Fix the data that limits analysis.** Publish the responding unit's origin, or at least its post. Add the 911 answer time. Reduce the 4.9% of incidents with no on-scene time.

## What the data cannot tell us

- **Where the responding ambulance started.** Without its origin, travel is linked to distance only through a stand-in (the nearest station or hospital), which explains little. The staging savings are therefore estimates, and probably on the low side.
- **Exact locations.** Incidents are published by zip only.
- **Crew availability, unit workload, and the knock-on cost of moving a unit.** None of these are in the data. The staging figures assume the staged unit is free.
- **Patient outcomes.** The call type reflects what the caller reported, not what the patient had, and survival is not recorded.
- **Time before the EMS incident exists.** 911 answering and call-taking happen before the incident's start time, so they are not included.

Sources: FDNY EMS Incident Dispatch Data (6,444,090 incidents, 2022-2025), NYC DOHMH MODZCTA, NYC Planning Facilities Database, Open-Meteo. Method and full tables: `README.md`, `docs/`.
