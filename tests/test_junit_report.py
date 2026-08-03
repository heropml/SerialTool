# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import junit_report as jr
import xml.etree.ElementTree as ET


def test_build_junit_pass_fail_skip():
    cases = [
        {"name": "ok", "classname": "C", "time_s": 0.012, "status": "pass",
         "properties": {"tx": "AT", "rx_hex": "4f4b"}},
        {"name": "bad", "classname": "C", "time_s": 0.5, "status": "fail",
         "message": "timeout", "detail": "timeout",
         "properties": {"detail_key": "seq_st_fail"}},
        {"name": "off", "classname": "C", "time_s": 0, "status": "skip",
         "detail": "disabled"},
    ]
    xml = jr.build_junit_xml("CommTool.Sequence", cases, {
        "app": "CommTool", "version": "1.3.6",
        "started_at": "2026-08-03 21:00:00",
        "finished_at": "2026-08-03 21:00:01",
    })
    assert 'encoding="utf-8"' in xml
    root = ET.fromstring(xml)
    suite = root.find("testsuite")
    assert suite.get("tests") == "3"
    assert suite.get("failures") == "1"
    assert suite.get("skipped") == "1"
    props = {p.get("name"): p.get("value") for p in suite.find("properties")}
    assert props.get("version") == "1.3.6"
    tcs = suite.findall("testcase")
    assert tcs[1].find("failure").get("message") == "timeout"
    assert tcs[2].find("skipped") is not None
    assert "tx=AT" in (tcs[0].find("system-out").text or "")


def test_cases_from_single_run():
    steps = [
        {"on": True, "name": "ping", "send": "AT", "expect": "OK"},
        {"on": False, "name": "off", "send": "X", "expect": ""},
        {"on": True, "name": "fail", "send": "Z", "expect": "Y"},
    ]
    results = [
        {"status": "pass", "ms": 10, "tx": "AT", "rx_hex": "4f4b"},
        {"status": "skip", "ms": 0},
        {"status": "fail", "ms": 1000, "detail": "timeout", "detail_key": "seq_st_fail"},
    ]
    cases = jr.cases_from_snapshot(steps, results, {"loops": 1, "pass": False})
    assert len(cases) == 2  # disabled step omitted
    assert cases[0]["status"] == "pass"
    assert cases[1]["status"] == "fail"
    assert cases[1]["message"] == "timeout"


def test_cases_from_csv_rounds():
    summary = {
        "loops": 2, "csv_path": "/tmp/a.csv", "csv_rows": 2,
        "round_list": [
            {"round": 1, "ok": 1, "total": 1, "ms": 5, "pass": True,
             "csv_row": 2, "csv_label": "D1"},
            {"round": 2, "ok": 0, "total": 1, "ms": 9, "pass": False,
             "csv_row": 3, "csv_label": "D2"},
        ],
    }
    cases = jr.cases_from_snapshot([], [], summary)
    assert len(cases) == 2
    assert cases[0]["name"] == "round_1_D1"
    assert cases[1]["status"] == "fail"
    assert cases[1]["properties"]["csv_row"] == 3


def test_loop_with_step_snapshots_stays_round_level():
    """Production snapshots include step_defs/steps, but JUnit stays 1 case/round."""
    summary = {
        "loops": 2,
        "round_list": [{
            "round": 1, "ok": 1, "total": 2, "ms": 15, "pass": False,
            "step_defs": [
                {"on": True, "name": "ok", "send": "A", "expect": "B"},
                {"on": True, "name": "bad", "send": "C", "expect": "D"},
            ],
            "steps": [
                {"status": "pass", "ms": 5},
                {"status": "fail", "ms": 10, "detail": "timeout"},
            ],
        }],
    }
    cases = jr.cases_from_snapshot([], [], summary)
    assert len(cases) == 1
    assert cases[0]["name"] == "round_1"
    assert cases[0]["status"] == "fail"
    assert cases[0]["properties"] == {"steps_ok": 1, "steps_total": 2}


def test_stopped_between_rounds_adds_failure_marker():
    summary = {
        "loops": 3, "stopped": True, "pass": False,
        "round_list": [
            {"round": 1, "ok": 1, "total": 1, "ms": 5, "pass": True},
        ],
    }
    cases = jr.cases_from_snapshot([], [], summary)
    assert [c["status"] for c in cases] == ["pass", "fail"]
    assert cases[1]["name"] == "sequence_stopped"
    assert cases[1]["properties"] == {"rounds_completed": 1, "rounds_planned": 3}
    root = ET.fromstring(jr.build_junit_xml("S", cases, summary))
    suite = root.find("testsuite")
    assert suite.get("tests") == "2"
    assert suite.get("failures") == "1"


def test_stopped_loop_with_failed_round_does_not_duplicate_failure():
    summary = {
        "loops": 3, "stopped": True, "pass": False,
        "round_list": [
            {"round": 1, "ok": 0, "total": 1, "ms": 5, "pass": False},
        ],
    }
    cases = jr.cases_from_snapshot([], [], summary)
    assert len(cases) == 1
    assert cases[0]["name"] == "round_1"
    assert cases[0]["status"] == "fail"


def test_stopped_case_is_reported_as_failure():
    cases = jr.cases_from_snapshot(
        [{"on": True, "name": "wait", "send": "AT", "expect": "OK"}],
        [{"status": "stopped", "ms": 20}],
        {"loops": 1, "pass": False},
    )
    assert cases[0]["status"] == "fail"


def test_escape_special_chars():
    cases = [{"name": 'a<b>&"c', "classname": "C", "time_s": 0, "status": "fail",
              "message": 'x<y>&"z', "detail": "d"}]
    xml = jr.build_junit_xml("S", cases, {})
    # Must parse as well-formed XML
    ET.fromstring(xml)
    assert "&lt;" in xml or "a&lt;b" in xml


def test_control_chars_stay_well_formed():
    """Raw wire bytes must not make the report unparseable for CI."""
    cases = [{"name": "ctrl\x01", "classname": "C\x02", "time_s": 0, "status": "fail",
              "message": "bad\x00msg", "detail": "det\x08ail",
              "properties": {"send": "AT\x1f", "rx_hex": "de\x0cad", "csv_label": "row\x0b1"}}]
    xml = jr.build_junit_xml("S\x03", cases, {"started_at": "2026-01-01 00:00:00\x04"})
    root = ET.fromstring(xml)
    assert root.tag == "testsuites"
    for ch in ("\x00", "\x01", "\x02", "\x03", "\x04", "\x08", "\x0b", "\x0c", "\x1f"):
        assert ch not in xml
    assert "\\x01" in xml and "\\x1f" in xml


def test_skipped_case_keeps_tabs_and_newlines():
    cases = [{"name": "n", "classname": "C", "time_s": 0, "status": "skip",
              "detail": "line1\nline2\tend"}]
    xml = jr.build_junit_xml("S", cases, {})
    ET.fromstring(xml)
    assert "line1" in xml and "line2" in xml
