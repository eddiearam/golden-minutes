import duckdb
import pandas as pd
import pytest

from src.clean import RULES, clean_sql, quality_counts

BASE = {
    "incident_id": "1",
    "incident_datetime": "2024-03-01T10:00:00.000",
    "initial_call_type": "ARREST",
    "initial_severity_level_code": "1",
    "final_call_type": "ARREST",
    "final_severity_level_code": "1",
    "first_assignment_datetime": "2024-03-01T10:01:00.000",
    "valid_dispatch_rspns_time_indc": "Y",
    "dispatch_response_seconds_qy": "60",
    "first_activation_datetime": "2024-03-01T10:01:30.000",
    "first_on_scene_datetime": "2024-03-01T10:08:00.000",
    "valid_incident_rspns_time_indc": "Y",
    "incident_response_seconds_qy": "480",
    "incident_travel_tm_seconds_qy": "420",
    "first_to_hosp_datetime": None,
    "first_hosp_arrival_datetime": None,
    "incident_close_datetime": "2024-03-01T11:00:00.000",
    "held_indicator": "N",
    "incident_disposition_code": "82",
    "borough": "BRONX",
    "incident_dispatch_area": "B1",
    "zipcode": "10456",
    "reopen_indicator": "N",
    "special_event_indicator": "N",
    "standby_indicator": "N",
    "transfer_indicator": "N",
}


def run(rows: list[dict]) -> pd.DataFrame:
    con = duckdb.connect()
    con.register("raw_df", pd.DataFrame([{**BASE, **r} for r in rows]).astype("string"))
    con.execute("CREATE TABLE raw AS SELECT * FROM raw_df")
    con.execute("CREATE TABLE zipmap AS SELECT * FROM (VALUES ('10456','10456'), ('10001','10001')) t(zip, modzcta)")
    con.execute(f"CREATE TABLE flagged AS {clean_sql('raw')}")
    return con.execute("SELECT * FROM flagged ORDER BY incident_id").df(), con


def test_clean_row_passes_and_components_sum():
    df, _ = run([{}])
    r = df.iloc[0]
    assert r.rt_ok
    assert (r.call_handling_s, r.dispatch_s, r.travel_s, r.response_s) == (60, 30, 390, 480)
    assert r.call_handling_s + r.dispatch_s + r.travel_s == r.response_s
    assert r.life_threatening
    assert r.modzcta == "10456"


@pytest.mark.parametrize(
    "override,flag",
    [
        ({"first_on_scene_datetime": "2024-03-01T10:00:50.000"}, "f_order_arrival_before_dispatch"),
        ({"first_assignment_datetime": "2024-03-01T09:59:00.000"}, "f_order_assign_before_create"),
        ({"first_activation_datetime": "2024-03-01T10:00:30.000"}, "f_order_activation_before_assign"),
        ({"first_on_scene_datetime": None}, "f_no_on_scene"),
        ({"first_assignment_datetime": None}, "f_no_assignment"),
        ({"first_activation_datetime": None}, "f_no_activation"),
        ({"first_on_scene_datetime": "2024-03-01T14:00:00.000"}, "f_extreme_component"),
        ({"first_on_scene_datetime": "2024-03-01T10:01:30.000"}, "f_zero_travel"),
        ({"standby_indicator": "Y"}, "f_standby"),
        ({"transfer_indicator": "Y"}, "f_transfer"),
        ({"valid_incident_rspns_time_indc": "N"}, "f_dataset_invalid"),
    ],
)
def test_exclusion_rules(override, flag):
    df, _ = run([override])
    r = df.iloc[0]
    assert r[flag], flag
    assert not r.rt_ok


@pytest.mark.parametrize(
    "override,flag",
    [
        ({"held_indicator": "Y"}, "f_held"),
        ({"reopen_indicator": "Y"}, "f_reopen"),
        ({"special_event_indicator": "Y"}, "f_special_event"),
        ({"incident_response_seconds_qy": "900"}, "f_qy_mismatch"),
        ({"zipcode": "99999"}, "f_no_zip"),
    ],
)
def test_flag_only_rules_keep_row(override, flag):
    df, _ = run([override])
    r = df.iloc[0]
    assert r[flag]
    assert r.rt_ok


def test_extreme_response_flag():
    df, _ = run(
        [
            {
                "first_assignment_datetime": "2024-03-01T12:00:00.000",
                "first_activation_datetime": "2024-03-01T12:30:00.000",
                "first_on_scene_datetime": "2024-03-01T13:30:01.000",
            }
        ]
    )
    assert df.iloc[0].f_extreme_response and not df.iloc[0].f_extreme_component


def test_duplicates_flag_only_later_copy():
    df, _ = run([{}, {}])
    assert df.f_duplicate.sum() == 1
    assert df.rt_ok.sum() == 1


def test_bad_timestamp_and_severity():
    df, _ = run(
        [
            {"incident_id": "2", "incident_datetime": "not a date"},
            {"incident_id": "3", "initial_severity_level_code": "5"},
        ]
    )
    by = df.set_index("incident_id")
    assert by.loc["2", "f_bad_incident_ts"]
    assert not by.loc["3", "life_threatening"]


def test_quality_counts_has_every_rule():
    _, con = run(
        [
            {},
            {"incident_id": "2", "held_indicator": "Y"},
            {"incident_id": "3", "first_on_scene_datetime": None},
        ]
    )
    q = quality_counts(con, "flagged").set_index("rule")
    assert q.loc["total_rows", "rows"] == 3
    for r, _, _ in RULES:
        assert r in q.index
    assert q.loc["f_held", "rows"] == 1
    assert q.loc["f_no_on_scene", "rows"] == 1
    assert q.loc["rt_ok", "rows"] == 2
