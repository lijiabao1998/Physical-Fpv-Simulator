"""Descriptive saved-record interruption timing; no model, fit or network access."""

import argparse
import bisect
import csv
import gzip
import hashlib
import io
import json
import math
import resource
import signal
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/benchmarks"
PROTOCOL = BASE / "stanford-k2-rest-timing-protocol.json"
PROTOCOL_SHA = "3025ddf13b794034cb7cd8a7e73cf5ae7a3b461b9fd4be65b74f453b9593beca"
LOW_RECORDS = BASE / "stanford-k2-low-rate-rest-records.csv.gz"
LOW_RECEIPT = BASE / "stanford-k2-low-rate-rest-source.json"
LOW_RECORDS_SHA = "e1e16db21fa2e8408934ec758d8b1b5e713846a4b4149b337641634197e873d9"
FIELDS = [
    "Date_Time",
    "Test_Time(s)",
    "Step_Time(s)",
    "Step_Index",
    "Voltage(V)",
    "Current(A)",
    "Surface_Temp(degC)",
]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def protocol():
    raw = PROTOCOL.read_bytes()
    if digest(raw) != PROTOCOL_SHA:
        raise ValueError("Frozen characterization protocol changed")
    return json.loads(raw)


def bounded():
    spec = protocol()
    resource.setrlimit(resource.RLIMIT_AS, (spec["maximum_address_space_bytes"],) * 2)
    signal.alarm(spec["maximum_wall_s_per_offline_pass"])


def extract_low(path):
    spec = protocol()
    raw = path.read_bytes()
    if (
        len(raw) != spec["source_low_workbook_bytes"]
        or digest(raw) != spec["source_low_workbook_sha256"]
    ):
        raise ValueError("Wrong original low-rate workbook")
    import openpyxl

    if not openpyxl.DEFUSEDXML:
        raise ValueError("Pinned safe XML parser required")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True, keep_links=False)
    selected, last_load = [], None
    try:
        if len(workbook.worksheets) != 1:
            raise ValueError("Unexpected workbook sheets")
        stream = workbook.active.iter_rows(values_only=True)
        if list(next(stream)) != FIELDS:
            raise ValueError("Original workbook schema changed")
        for index, row in enumerate(stream, 2):
            if row[3] == 5:
                last_load = [index, row[0].isoformat(), *row[1:]]
            elif row[3] == 6:
                selected.append([index, row[0].isoformat(), *row[1:]])
    finally:
        workbook.close()
    if last_load is None or len(selected) != 3601:
        raise ValueError("Expected one last load and3601 rest samples")
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["excel_row", *FIELDS])
    writer.writerows([last_load, *selected])
    content = output.getvalue().encode()
    compressed = gzip.compress(content, mtime=0)
    if digest(compressed) != LOW_RECORDS_SHA:
        raise ValueError("Normalized source differs from independently verified bytes")
    LOW_RECORDS.write_bytes(compressed)
    receipt = {
        "source_filename": path.name,
        "source_workbook_bytes": len(raw),
        "source_workbook_sha256": digest(raw),
        "selected_rows": 3602,
        "excel_rows_inclusive": [last_load[0], selected[-1][0]],
        "records_gzip_sha256": digest(compressed),
        "records_csv_sha256": digest(content),
        "protocol_sha256": PROTOCOL_SHA,
        "authors": ["Edoardo Catenaro", "Simona Onori"],
        "doi": "10.17632/kxsbr4x3j2.2",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "modifications": (
            "Only select last step5 row and complete step6, add Excel row index, "
            "serialize dates and numerics; no measurement value change"
        ),
    }
    LOW_RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def read_rows(raw):
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(raw).decode())))
    if not rows or list(rows[0]) != ["excel_row", *FIELDS]:
        raise ValueError("Saved record schema changed")
    return rows


def interpolate(rest, query):
    times = [float(row["Step_Time(s)"]) for row in rest]
    if not math.isfinite(query) or not times[0] <= query <= times[-1]:
        raise ValueError("Query outside recorded support")
    right = bisect.bisect_left(times, query)
    left = right if times[right] == query else right - 1
    fraction = 0.0 if left == right else (query - times[left]) / (times[right] - times[left])
    values = {}
    for name in ("Voltage(V)", "Current(A)", "Surface_Temp(degC)"):
        a, b = float(rest[left][name]), float(rest[right][name])
        values[name] = a + fraction * (b - a)
    return {
        "nominal_rest_time_s": query,
        "lower_source_row": rest[left],
        "upper_source_row": rest[right],
        "upper_weight": fraction,
        "values": values,
    }


def characterize(rows, spec):
    load = [row for row in rows if float(row["Step_Index"]) == 5][-1]
    rest = [row for row in rows if float(row["Step_Index"]) == 6]
    if len(rest) != 3601:
        raise ValueError("Wrong rest row count")
    for row in [load, *rest]:
        if not all(math.isfinite(float(row[field])) for field in FIELDS[1:]):
            raise ValueError("Nonfinite source value")
    times = [float(row["Step_Time(s)"]) for row in rest]
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        raise ValueError("Nonmonotone rest time")
    if any(float(row["Current(A)"]) != 0 for row in rest):
        raise ValueError("Rest has nonzero recorded current")
    first_v, load_v = float(rest[0]["Voltage(V)"]), float(load["Voltage(V)"])
    jump = first_v - load_v
    points = []
    for query in spec["queries_nominal_rest_s"]:
        point = interpolate(rest, float(query))
        voltage = point["values"]["Voltage(V)"]
        point["voltage_minus_last_loaded_v"] = voltage - load_v
        point["voltage_minus_first_rest_v"] = voltage - first_v
        closure = (voltage - load_v) - (jump + voltage - first_v)
        if abs(closure) > spec["numerical_identity_tolerance_v"]:
            raise ValueError("Recovery arithmetic identity failed")
        point["identity_closure_v"] = closure
        points.append(point)
    return {
        "last_loaded_source_row": load,
        "first_rest_source_row": rest[0],
        "last_rest_source_row": rest[-1],
        "last_load_to_first_rest_sample_bracket_s": float(rest[0]["Test_Time(s)"])
        - float(load["Test_Time(s)"]),
        "sample_bracket_bounds_physical_switch_time": False,
        "first_recorded_recovery_v": jump,
        "further_first_to_last_rest_recovery_v": float(rest[-1]["Voltage(V)"]) - first_v,
        "rest_rows": len(rest),
        "recorded_rest_current_a": 0,
        "points": points,
    }


def analyze():
    spec = protocol()
    high = (BASE / "stanford-k2-rest-records.csv.gz").read_bytes()
    low = LOW_RECORDS.read_bytes()
    receipt = json.loads(LOW_RECEIPT.read_text())
    if digest(high) != spec["source_high_records_sha256"]:
        raise ValueError("High-rate source identity changed")
    if (
        digest(low) != LOW_RECORDS_SHA
        or receipt["source_workbook_sha256"] != spec["source_low_workbook_sha256"]
        or receipt["protocol_sha256"] != PROTOCOL_SHA
        or digest(low) != receipt["records_gzip_sha256"]
        or digest(gzip.decompress(low)) != receipt["records_csv_sha256"]
    ):
        raise ValueError("Low-rate source identity changed")
    return {
        "protocol_sha256": PROTOCOL_SHA,
        "low_source": receipt,
        "high_records_sha256": digest(high),
        "cases": {
            "low": characterize(read_rows(low), spec),
            "high": characterize(read_rows(high), spec),
        },
        "new_model_solves": 0,
        "new_downloads": 0,
        "fitted_parameters": False,
        "identified_resistance": False,
        "independent_experimental_validation": False,
        "common_SOC_established": False,
        "description": (
            "Finite-time descriptive characterization; no new physical acceptance threshold"
        ),
    }


def write_csv(result, path):
    fields = [
        "record",
        "nominal_rest_s",
        "voltage_v",
        "raw_current_a",
        "skin_c",
        "recovery_from_last_load_v",
        "recovery_from_first_rest_v",
        "lower_excel_row",
        "upper_excel_row",
        "lower_nominal_rest_s",
        "upper_nominal_rest_s",
        "upper_weight",
    ]
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(fields)
        for name, case in result["cases"].items():
            for point in case["points"]:
                lower, upper = point["lower_source_row"], point["upper_source_row"]
                values = point["values"]
                writer.writerow(
                    [
                        name,
                        point["nominal_rest_time_s"],
                        values["Voltage(V)"],
                        values["Current(A)"],
                        values["Surface_Temp(degC)"],
                        point["voltage_minus_last_loaded_v"],
                        point["voltage_minus_first_rest_v"],
                        lower["excel_row"],
                        upper["excel_row"],
                        lower["Step_Time(s)"],
                        upper["Step_Time(s)"],
                        point["upper_weight"],
                    ]
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract-low", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    bounded()
    if args.extract_low:
        extract_low(args.extract_low)
    result = analyze()
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    write_csv(result, args.out.with_suffix(".csv"))
    print(
        json.dumps(
            {
                "elapsed_s": time.monotonic() - started,
                "maximum_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "output": str(args.out),
            }
        )
    )
