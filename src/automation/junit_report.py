# -*- coding: utf-8 -*-
"""JUnit XML report builder for automated sequence runs (Qt-free).

Produces Jenkins/GitLab-compatible JUnit XML from a sequence snapshot.
"""
from __future__ import print_function

import re
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Cap wire-frame dumps so reports stay readable.
MAX_FRAME_CHARS = 512

# XML 1.0 forbids most control characters outright; raw wire bytes would make
# the report unparseable for Jenkins/GitLab, so they are escaped textually.
_XML_ILLEGAL = re.compile(
    "[^\u0009\u000a\u000d\u0020-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def _xml_safe(text):
    s = "" if text is None else str(text)
    return _XML_ILLEGAL.sub(lambda m: "\\x%02x" % ord(m.group(0)), s)


def _clip(text, n=MAX_FRAME_CHARS):
    s = "" if text is None else str(text)
    if len(s) > n:
        return s[:n] + "..."
    return s


def _ms_to_sec(ms):
    try:
        return max(0.0, float(ms) / 1000.0)
    except (TypeError, ValueError):
        return 0.0


def _set_props(parent, props):
    """Attach <properties><property name=.. value=../></properties>."""
    if not props:
        return
    props_el = ET.SubElement(parent, "properties")
    for key in sorted(props.keys()):
        val = props[key]
        if val is None or val == "":
            continue
        p = ET.SubElement(props_el, "property")
        p.set("name", _xml_safe(key))
        p.set("value", _xml_safe(val))


def cases_from_snapshot(steps, results, summary, detail_resolver=None):
    """Build JUnit case dicts from a sequence run snapshot.

    detail_resolver(res) -> localized failure/detail string (optional).
    Loop/CSV runs: one case per completed round. A stopped run whose completed
    rounds all passed gets one additional failure marker so CI cannot report it
    as successful. Single run: one case per enabled step.
    """
    summary = summary or {}
    resolve = detail_resolver or (lambda r: str((r or {}).get("detail") or ""))
    rounds = list(summary.get("round_list") or [])
    is_loop = int(summary.get("loops", 1) or 1) > 1 or bool(summary.get("csv_path"))
    if is_loop and rounds:
        cases = []
        for r in rounds:
            round_no = r.get("round", len(cases) + 1)
            label = str(r.get("csv_label") or "").strip()
            # Loop/CSV reports intentionally use one testcase per round. Detailed
            # per-step evidence remains available in the HTML/CSV reports.
            name = "round_%s" % round_no
            if label:
                name = "%s_%s" % (name, label)
            st = "pass" if r.get("pass") else "fail"
            msg = ""
            if st == "fail":
                msg = "round %s: %s/%s steps" % (
                    round_no, r.get("ok", 0), r.get("total", 0))
            props = {"steps_ok": r.get("ok", 0), "steps_total": r.get("total", 0)}
            if "csv_row" in r:
                props["csv_row"] = r.get("csv_row")
            if label:
                props["csv_label"] = label
            cases.append({
                "name": name,
                "classname": "CommTool.Sequence",
                "time_s": _ms_to_sec(r.get("ms", 0)),
                "status": st,
                "message": msg,
                "detail": msg,
                "properties": props,
            })
        if summary.get("stopped") and not any(c.get("status") == "fail" for c in cases):
            msg = "sequence stopped before completion"
            cases.append({
                "name": "sequence_stopped",
                "classname": "CommTool.Sequence",
                "time_s": 0.0,
                "status": "fail",
                "message": msg,
                "detail": msg,
                "properties": {
                    "rounds_completed": len(rounds),
                    "rounds_planned": summary.get("loops"),
                },
            })
        return cases

    cases = []
    steps = steps or []
    results = results or []
    for i, step in enumerate(steps):
        if not step.get("on", True):
            continue
        res = results[i] if i < len(results) else {}
        st = str(res.get("status") or "pending")
        name = str(step.get("name") or "") or ("step_%d" % (i + 1))
        detail = resolve(res)
        props = {
            "step": i + 1,
            "send": _clip(step.get("send")),
            "expect": _clip(step.get("expect")),
        }
        if res.get("tx"):
            props["tx"] = _clip(res.get("tx"))
        if res.get("rx_hex"):
            props["rx_hex"] = _clip(res.get("rx_hex"))
        if res.get("attempt"):
            props["attempt"] = res.get("attempt")
        if res.get("detail_key"):
            props["detail_key"] = res.get("detail_key")

        if st in ("pass", "sent"):
            jstatus = "pass"
        elif st == "skip":
            jstatus = "skip"
        elif st == "stopped":
            jstatus = "fail"
            detail = detail or "stopped"
        else:
            jstatus = "fail"
            if not detail:
                detail = st

        cases.append({
            "name": name,
            "classname": "CommTool.Sequence",
            "time_s": _ms_to_sec(res.get("ms", 0)),
            "status": jstatus,
            "message": detail if jstatus == "fail" else "",
            "detail": detail,
            "properties": props,
        })
    return cases


def build_junit_xml(suite_name, cases, metadata=None):
    """Return pretty JUnit XML string (UTF-8 declaration)."""
    metadata = dict(metadata or {})
    cases = list(cases or [])
    tests = len(cases)
    failures = sum(1 for c in cases if c.get("status") == "fail")
    skipped = sum(1 for c in cases if c.get("status") == "skip")
    total_time = sum(float(c.get("time_s") or 0) for c in cases)

    suites = ET.Element("testsuites")
    suites.set("name", _xml_safe(suite_name or "CommTool"))
    suites.set("tests", str(tests))
    suites.set("failures", str(failures))
    suites.set("skipped", str(skipped))
    suites.set("time", "%.3f" % total_time)

    suite = ET.SubElement(suites, "testsuite")
    suite.set("name", _xml_safe(suite_name or "CommTool.Sequence"))
    suite.set("tests", str(tests))
    suite.set("failures", str(failures))
    suite.set("skipped", str(skipped))
    suite.set("time", "%.3f" % total_time)
    if metadata.get("started_at"):
        suite.set("timestamp", _xml_safe(str(metadata["started_at"]).replace(" ", "T")))
    _set_props(suite, {
        "app": metadata.get("app") or "CommTool",
        "version": metadata.get("version"),
        "started_at": metadata.get("started_at"),
        "finished_at": metadata.get("finished_at"),
        "loops": metadata.get("loops"),
        "stop_on_fail": metadata.get("stop_on_fail"),
        "csv_path": metadata.get("csv_path"),
        "csv_rows": metadata.get("csv_rows"),
        "pass": metadata.get("pass"),
        "stopped": metadata.get("stopped"),
    })

    for c in cases:
        tc = ET.SubElement(suite, "testcase")
        tc.set("name", _xml_safe(c.get("name") or "case"))
        tc.set("classname", _xml_safe(c.get("classname") or "CommTool.Sequence"))
        tc.set("time", "%.3f" % float(c.get("time_s") or 0))
        _set_props(tc, c.get("properties") or {})
        st = c.get("status")
        if st == "fail":
            fail = ET.SubElement(tc, "failure")
            fail.set("message", _xml_safe(c.get("message") or "failed"))
            fail.set("type", "AssertionError")
            fail.text = _xml_safe(c.get("detail") or c.get("message") or "")
        elif st == "skip":
            sk = ET.SubElement(tc, "skipped")
            if c.get("detail"):
                sk.set("message", _xml_safe(c.get("detail")))
        # system-out with frames when present
        props = c.get("properties") or {}
        out_lines = []
        for key in ("tx", "rx_hex", "send", "expect"):
            if props.get(key):
                out_lines.append("%s=%s" % (key, props[key]))
        if out_lines:
            so = ET.SubElement(tc, "system-out")
            so.text = _xml_safe("\n".join(out_lines))

    raw = ET.tostring(suites, encoding="utf-8")
    try:
        pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")
        return pretty.decode("utf-8")
    except Exception:
        return '<?xml version="1.0" encoding="utf-8"?>\n' + raw.decode("utf-8")
