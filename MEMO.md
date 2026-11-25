# Memo: NYC ambulance response times, 2022-2025

**To:** EMS operations leadership  **Re:** Why responses are slowing, and which levers buy time back

## What we found

1. **Life-threatening calls are getting slower.** Median response (incident created to first unit on scene) rose from 6.8 min in 2022 to 7.4 min in 2025, and the 90th percentile from 11.8 to 13.2 min, across 581,682 life-threatening calls in 2025. Travel accounts for +0.5 of the +0.6 min rise.

2. **The cause is ambulances tied up longer, not more calls.** Jobs were flat (1,573,224 in 2022; 1,573,538 in 2025), but the average job, from assignment to close, grew from 65.2 to 71.4 min. On average 214 ambulances were busy at any moment in 2025, against 195 in 2022. Getting to the scene grew most (+2.5 min per job), then time on scene (+1.9), at hospital (+1.1) and transport (+0.7). Slower arrivals keep ambulances busy longer, which makes the next arrival slower still. Time at hospital is the largest single stage of a transport, with a median of 41 min.

3. **Each busy ambulance costs the next life-threatening call 2.4 seconds.** We compared calls in the same borough, hour of week and day. With one more ambulance busy in the borough, life-threatening response is 2.4 s slower (95% CI 2.2-2.5 s), almost all of it longer travel. Other calls are 20 s slower, half of it waiting for assignment. The effect holds every year and in every borough, and is largest on Staten Island (9.7 s). Busy ambulances in another borough have no effect, which rules out weather and traffic. Fitted on 2022-2024, the estimate predicted 2025 with an error of 0.04 min, against 0.23 min assuming no effect.

4. **Freeing ambulances beats moving them.** Priced on every 2025 call (average seconds saved per life-threatening call):
   - Staging idle ambulances at 20 points saves 4 s, and only if they are free.
   - One more ambulance on every shift in every borough (15 a day) saves 3 s for life-threatening calls and 22 s for other calls.
   - A 10-minute faster hospital handover saves 11 s (95% CI 10-12 s) and 93 s for other calls. It frees about 22 ambulances at the weekday 15:00-19:00 peak and cuts held life-threatening calls from 5.2% to 4.5%.
   - Handover −10 min, plus 15 targeted ambulance-shifts, plus staging, saves 19 s. The median moves from 7.37 to 7.06 min, and held other calls fall from 29.0% to 23.8%.

5. **Where and when.** The Bronx had the slowest borough median (8.0 min) and the most holds (8.5%). The slowest zips sit at the network's edge: City Island 11.8 min, Roosevelt Island 10.6, Tottenville 10.1. The 15 slowest hours of the week all fall on weekdays between 15:00 and 19:00.

6. **Demand can be forecast a week ahead**, with 8.8% lower error than the usual 4-week average per zip and 4-hour block. That is accurate enough for weekly tour planning.

## Recommendations

1. **Make hospital handover time a managed metric.** It is the cheapest source of capacity: each minute cut frees about 2 ambulances at the weekday peak. Set a target, report it by hospital, and start with the 15:00-19:00 peak.
2. **Add tours where they buy the most.** One extra ambulance on the Manhattan evening or day shift saves about 55 life-threatening minutes a week. Brooklyn evenings and Bronx evenings and days follow at 38-39 minutes. Staten Island gains most per call.
3. **Track busy ambulances per borough as a live indicator.** Each extra busy unit has a known cost, so the count can trigger mutual aid or the release of units held at hospitals.
4. **Use staging only for remote areas.** The Rockaways (about 48 s per call) and eastern Queens (about 42 s) are worth a short, measured pilot; citywide staging is not.
5. **Publish the data needed to target these levers:** hospital name, every unit assigned, and the 911 answer time.

## What the data cannot tell us

- **Hospital, unit and street.** The data does not name the hospital, records only the first unit on each incident, and gives locations by zip only.
- **Whether short-run effects persist.** The 2.4 s estimate comes from hour-to-hour swings in workload. A permanent change could alter how dispatchers hold calls, so the savings show direction and size, not a guarantee. The planner stays within the range the data covers.
- **About three-quarters of the slowdown.** Extra busy ambulances explain about a quarter of the rise in mean life-threatening response (+0.19 of +0.75 min). The rest fits fewer staffed ambulances or slower traffic, which the data cannot separate.
- **Patient outcomes.** The call type reflects what the caller reported, and survival is not recorded.

Sources: FDNY EMS Incident Dispatch Data (6,444,090 incidents, 2022-2025), NYC DOHMH MODZCTA, NYC Planning Facilities Database, Open-Meteo. Method and full tables: `README.md`, `docs/capacity.md`, `docs/results/`.
