"""Independent pinned-source schema verification; historical attempt labels are retained."""

import collections
import hashlib
import io
import json
import math
import re

# Callbacks run synchronously inside each parse; none escape a loop iteration.
# ruff: noqa: B023
import resource
import signal
import time
import xml.parsers.expat as expat
import zipfile
from pathlib import Path

if not __debug__:
    raise RuntimeError("Run this independent checker without Python optimization")
resource.setrlimit(resource.RLIMIT_AS, (536870912, 536870912))
signal.alarm(120)
start = time.monotonic()


def fail(*args):
    raise ValueError("DTD/entity/external declaration forbidden")


def parse(stream, begin=None, end=None, text=None):
    p = expat.ParserCreate(namespace_separator="}")
    p.StartDoctypeDeclHandler = fail
    p.EntityDeclHandler = fail
    p.ExternalEntityRefHandler = fail
    p.StartElementHandler = begin
    p.EndElementHandler = end
    p.CharacterDataHandler = text
    p.ParseFile(stream)


def local(name):
    return name.rsplit("}", 1)[-1]


p = Path("results/characterization-source-audit/Source_Data.zip")
assert p.stat().st_size <= 12000000
raw = p.read_bytes()
md5 = hashlib.md5(raw).hexdigest()
sha = hashlib.sha256(raw).hexdigest()
assert (
    len(raw) == 10776640
    and md5 == "686c44f88eb26d26956a06c3d144409f"
    and sha == "054b6019a110d2928f5abf1420ed13febf57231f6d8abb76a799ef0447765964"
)
z = zipfile.ZipFile(io.BytesIO(raw))
assert len(z.infolist()) <= 200 and sum(i.file_size for i in z.infolist()) <= 150000000
out = {
    "bytes": len(raw),
    "md5": md5,
    "sha256": sha,
    "independent_parser": "streaming stdlib Expat; DTD/entity/external declarations rejected",
    "previous_attempts": [
        {"parser": "openpyxl", "result": "defusedxml unavailable; stopped before workbook parsing"},
        {
            "parser": "openpyxl with Expat preflight",
            "result": "512 MiB memory limit reached; no completed receipt",
        },
    ],
    "workbooks": [],
}
for figure in (10, 14):
    name = f"Source_Data/Supplementary Figure {figure}.xlsx"
    data = z.read(name)
    w = zipfile.ZipFile(io.BytesIO(data))
    infos = w.infolist()
    assert (
        len(infos) <= 200
        and sum(i.file_size for i in infos) <= 100000000
        and len({i.filename for i in infos}) == len(infos)
    )
    assert all(not i.flag_bits & 1 for i in infos)
    strings = []
    parts = []
    intext = [False]

    def sb(tag, a):
        if local(tag) == "si":
            parts.clear()
        if local(tag) == "t":
            intext[0] = True

    def se(tag):
        if local(tag) == "t":
            intext[0] = False
        if local(tag) == "si":
            strings.append("".join(parts))

    if "xl/sharedStrings.xml" in w.namelist():
        with w.open("xl/sharedStrings.xml") as f:
            parse(f, sb, se, lambda text: parts.append(text) if intext[0] else None)
    sheets = []
    rels = {}
    with w.open("xl/workbook.xml") as f:
        parse(f, lambda tag, a: sheets.append(a) if local(tag) == "sheet" else None)
    with w.open("xl/_rels/workbook.xml.rels") as f:
        parse(f, lambda tag, a: rels.update({a["Id"]: a}) if local(tag) == "Relationship" else None)
    book = {"name": name, "sha256": hashlib.sha256(data).hexdigest(), "sheets": []}
    for sheet in sheets:
        rel = rels[next(v for k, v in sheet.items() if k.endswith("}id"))]
        assert rel.get("TargetMode") != "External"
        target = rel["Target"]
        member = target.lstrip("/") if target.startswith("/") else "xl/" + target
        assert ".." not in member.split("/")
        sh = {
            "sheet": sheet["name"],
            "member": member,
            "rows": 0,
            "headers": {},
            "all_text_cells": [],
            "formula_count": 0,
            "columns": {},
            "maximum_column_index": 0,
        }
        state = {"cell": None, "capture": False, "parts": [], "rowcols": set()}
        gaps = []
        prev = [None]
        pairmismatch = [0, 0]
        griderror = [0.0]

        def begin(tag, a):
            tag = local(tag)
            if tag == "row":
                assert 1 <= int(a["r"]) <= 200000
                state["rowcols"] = set()
                sh["rows"] += 1
            if tag == "c":
                state["cell"] = {
                    "address": a["r"],
                    "type": a.get("t"),
                    "formula": False,
                    "value": [],
                }
            if tag == "f" and state["cell"]:
                state["cell"]["formula"] = True
            if tag in ("v", "t") and state["cell"]:
                state["capture"] = True

        def characters(text):
            if state["capture"]:
                state["cell"]["value"].append(text)

        def end(tag):
            tag = local(tag)
            if tag in ("v", "t"):
                state["capture"] = False
            if tag == "row" and figure == 14:
                cols = state["rowcols"]
                pairmismatch[0] += int(("A" in cols) != ("B" in cols))
                pairmismatch[1] += int(("C" in cols) != ("D" in cols))
            if tag != "c":
                return
            c = state["cell"]
            state["cell"] = None
            coord = re.fullmatch(r"([A-Z]+)([0-9]+)", c["address"])
            assert coord
            col, row = coord[1], int(coord[2])
            colnum = 0
            for ch in col:
                colnum = colnum * 26 + ord(ch) - 64
            assert 1 <= row <= 200000 and 1 <= colnum <= 100
            sh["maximum_column_index"] = max(sh["maximum_column_index"], colnum)
            value = "".join(c["value"])
            sh["formula_count"] += int(c["formula"])
            if c["type"] == "s":
                value = strings[int(value)]
            if c["type"] in ("s", "str", "inlineStr"):
                sh["all_text_cells"].append([c["address"], value])
                assert len(sh["all_text_cells"]) <= 1000
                if row == 1:
                    sh["headers"][col] = value
                return
            if value == "":
                return
            v = float(value)
            assert math.isfinite(v)
            state["rowcols"].add(col)
            stats = sh["columns"].setdefault(
                col, {"numeric_count": 0, "first_row": row, "first": v, "min": v, "max": v}
            )
            stats["numeric_count"] += 1
            stats["last_row"] = row
            stats["last"] = v
            stats["min"] = min(stats["min"], v)
            stats["max"] = max(stats["max"], v)
            if figure == 10 and col == "A":
                griderror[0] = max(griderror[0], abs(v - (stats["numeric_count"] - 1) / 999))
            if figure == 14 and col == "A":
                if prev[0] is not None:
                    gaps.append((v - prev[0]) * 3600)
                prev[0] = v

        with w.open(member) as f:
            parse(f, begin, end, characters)
        for stats in sh["columns"].values():
            stats["missing_rows_within_extent"] = (
                stats["last_row"] - stats["first_row"] + 1 - stats["numeric_count"]
            )
        if figure == 10:
            sh["sto_grid_maximum_deviation_from_i_over_999"] = griderror[0]
        if figure == 14:
            assert sh["headers"] == {
                "A": "Time_h_Experiment",
                "B": "Voltage_V_Experiment",
                "C": "Time_h_Model",
                "D": "Voltage_V_Model",
            }
            ordered = sorted(gaps)
            freq = collections.Counter(round(g, 6) for g in gaps)
            sh["paired_experimental_row_mismatch_count"] = pairmismatch[0]
            sh["paired_model_row_mismatch_count"] = pairmismatch[1]
            sh["experimental_timestamp_spacing_seconds"] = {
                "meaning": (
                    "Workbook timestamp differences, "
                    "not instrument sampling/latency or synchronization"
                ),
                "count": len(gaps),
                "negative_count": sum(g < 0 for g in gaps),
                "zero_count": sum(g == 0 for g in gaps),
                "min": min(gaps),
                "max": max(gaps),
                "median": (ordered[(len(ordered) - 1) // 2] + ordered[len(ordered) // 2]) / 2,
                "first": gaps[0],
                "within_one_microsecond_of_0_1_count": sum(abs(g - 0.1) <= 1e-6 for g in gaps),
                "frequency_rounded_to_microsecond": sorted(freq.items()),
            }
        book["sheets"].append(sh)
    out["workbooks"].append(book)
out["elapsed_seconds"] = time.monotonic() - start
Path("results/characterization-source-audit/independent-check.json").write_text(
    json.dumps(out, indent=2) + "\n"
)
for book in out["workbooks"]:
    for sh in book["sheets"]:
        if "experimental_timestamp_spacing_seconds" in sh:
            stats = sh["experimental_timestamp_spacing_seconds"]
            stats["frequency_rounded_to_microsecond"] = sorted(
                stats["frequency_rounded_to_microsecond"], key=lambda pair: pair[1], reverse=True
            )[:15]
print(json.dumps(out, indent=2))
