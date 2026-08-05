import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from device_resources import (
    StructuredRecorder, decode_modbus_samples, decode_register_value,
    normalize_registers,
)


def test_register_normalization_and_32bit_word_order():
    records = normalize_registers([{
        "name": "temperature", "slave": "1", "function": "3",
        "address": "10", "type": "u32", "order": "CDAB",
        "scale": "0.1", "unit": "C",
    }])
    assert records[0]["address"] == 10
    value, raw = decode_register_value(records[0], [0x0002, 0x0001])
    assert value == 6553.8
    assert raw == "0002 0001"


def test_register_types_scaling_and_bit_decode():
    signed = {"type": "i16", "order": "AB", "scale": 0.5, "offset": 1}
    value, _ = decode_register_value(signed, [0xFFFE])
    assert value == 0
    bit = {"type": "bit", "bit": 3}
    assert decode_register_value(bit, [0b1000])[0] == 1


def test_modbus_response_maps_only_matching_tags():
    definitions = [
        {"name": "voltage", "slave": 2, "function": 3, "address": 100,
         "type": "u16", "scale": 0.1, "unit": "V"},
        {"name": "other", "slave": 3, "function": 3, "address": 100},
    ]
    samples = decode_modbus_samples(definitions, 2, 3, 100, [330], timestamp=10)
    assert len(samples) == 1
    assert samples[0]["tag"] == "voltage"
    assert samples[0]["value"] == 33
    assert samples[0]["timestamp"] == 10


def test_structured_recorder_csv_query_and_reload(tmp_path):
    recorder = StructuredRecorder(max_rows=3)
    recorder.start()
    assert recorder.add([
        {"timestamp": 1, "source": "modbus", "tag": "temp", "value": 20.5},
        {"timestamp": 2, "source": "protocol", "tag": "state", "value": 1},
    ]) == 2
    assert [row["tag"] for row in recorder.query("temp")] == ["temp"]
    assert [row["tag"] for row in recorder.query(source="protocol")] == ["state"]

    path = tmp_path / "history.csv"
    assert recorder.save_csv(path) == 2
    loaded = StructuredRecorder()
    assert loaded.load_csv(path) == 2
    assert loaded.rows[0]["value"] == 20.5
    assert loaded.rows[1]["source"] == "protocol"


def test_structured_recorder_caps_rows_and_rejects_nonfinite():
    recorder = StructuredRecorder(max_rows=1)
    recorder.start()
    recorder.add([{"tag": "x", "value": math.inf}, {"tag": "y", "value": 2}])
    assert len(recorder.rows) == 1
    assert recorder.rows[0]["value"] == ""
    assert recorder.truncated is True


def test_f64_and_bitfields():
    import struct
    from device_resources import decode_register_value, decode_modbus_samples, parse_bitfields
    # f64 AB order across 4 regs: pack as big-endian double split into words
    raw8 = struct.pack(">d", 1.5)
    regs = [int.from_bytes(raw8[i:i+2], "big") for i in range(0, 8, 2)]
    val, _ = decode_register_value({"type": "f64", "order": "ABCDEFGH"}, regs)
    assert abs(val - 1.5) < 1e-9
    assert parse_bitfields("0:4:nibble,4:1:flag") == [(0, 4, "nibble"), (4, 1, "flag")]
    samples = decode_modbus_samples(
        [{"name": "st", "slave": 1, "function": 3, "address": 0,
          "type": "u16", "bitfields": "0:3:code,3:1:ok", "alarm_hi": 100}],
        1, 3, 0, [0b1011], timestamp=1)
    tags = {s["tag"]: s["value"] for s in samples}
    assert tags["st"] == 0b1011
    assert tags["st.code"] == 0b011
    assert tags["st.ok"] == 1


def test_value_level_thresholds():
    from device_resources import value_level
    rec = {"warn_hi": 80, "alarm_hi": 100}
    assert value_level(50, rec) == ""
    assert value_level(85, rec) == "warn"
    assert value_level(120, rec) == "alarm"
