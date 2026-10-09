"""Inspect pinned Li2025 figure workbooks without executing external content."""

import hashlib
import io
import json
import posixpath
import re
import resource
import signal
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

resource.setrlimit(resource.RLIMIT_AS, (536870912, 536870912))
signal.alarm(120)
p = Path(sys.argv[1])
if not p.stat().st_size <= 12000000:
    raise ValueError("Source audit guard rejected; inspect the condition above.")
raw = p.read_bytes()
if hashlib.sha256(raw).hexdigest() != (
    "054b6019a110d2928f5abf1420ed13febf57231f6d8abb76a799ef0447765964"
):
    raise ValueError("Source SHA256 mismatch")
if not len(raw) <= 12000000:
    raise ValueError("Source audit guard rejected; inspect the condition above.")
if not hashlib.md5(raw).hexdigest() == "686c44f88eb26d26956a06c3d144409f":
    raise ValueError("Source audit guard rejected; inspect the condition above.")


def checked_zip(data, cap):
    z = zipfile.ZipFile(io.BytesIO(data))
    items = z.infolist()
    names = [i.filename for i in items]
    if not (len(items) <= 200 and len(set(names)) == len(names)):
        raise ValueError("Source audit guard rejected; inspect the condition above.")
    if not sum(i.file_size for i in items) <= cap:
        raise ValueError("Source audit guard rejected; inspect the condition above.")
    for i in items:
        if not not i.flag_bits & 1:
            raise ValueError("Source audit guard rejected; inspect the condition above.")
        if not (not i.filename.startswith("/") and "\\" not in i.filename):
            raise ValueError("Source audit guard rejected; inspect the condition above.")
        if not ".." not in i.filename.split("/"):
            raise ValueError("Source audit guard rejected; inspect the condition above.")
        if not i.external_attr >> 16 & 61440 not in (40960, 24576, 4096):
            raise ValueError("Source audit guard rejected; inspect the condition above.")
    for i in items:
        if i.filename.endswith((".xml", ".rels")):
            content = z.read(i.filename)
            if not b"\x00" not in content:
                raise ValueError("Source audit guard rejected; inspect the condition above.")
            content.decode("utf-8-sig")
            if not not re.search(b"<!\\s*(DOCTYPE|ENTITY)", content, re.I):
                raise ValueError("Source audit guard rejected; inspect the condition above.")
    return z


z = checked_zip(raw, 150000000)
out = {
    "bytes": len(raw),
    "md5": hashlib.md5(raw).hexdigest(),
    "sha256": hashlib.sha256(raw).hexdigest(),
    "members": [{"name": i.filename, "bytes": i.file_size} for i in z.infolist()],
    "workbooks": [],
    "time_monotonicity": "not_evaluated",
    "time_step_distribution": "not_evaluated",
    "channel_synchronization": "not_evaluated",
}
ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
for name in z.namelist():
    if not name.lower().endswith(".xlsx") or not any(
        "figure " + str(n) + "." in name.lower() for n in (10, 14)
    ):
        continue
    data = z.read(name)
    w = checked_zip(data, 100000000)
    if not not any(
        "vbaproject" in n.lower() or "externallinks/" in n.lower() for n in w.namelist()
    ):
        raise ValueError("Source audit guard rejected; inspect the condition above.")
    strings = []
    if "xl/sharedStrings.xml" in w.namelist():
        for node in ET.fromstring(w.read("xl/sharedStrings.xml")):
            strings.append("".join(t.text or "" for t in node.iter("{" + ns["s"] + "}t")))
    wb = {"name": name, "sha256": hashlib.sha256(data).hexdigest(), "sheets": []}
    sheet_names = [n.attrib for n in ET.fromstring(w.read("xl/workbook.xml")).find("s:sheets", ns)]
    wb["sheet_names"] = sheet_names
    rels = {
        n.attrib["Id"]: n.attrib["Target"]
        for n in ET.fromstring(w.read("xl/_rels/workbook.xml.rels"))
    }
    sheet_map = {
        posixpath.normpath(
            posixpath.join(
                "xl",
                rels[n["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]],
            )
        ): n["name"]
        for n in sheet_names
    }
    for sn in w.namelist():
        if not sn.startswith("xl/worksheets/sheet") or not sn.endswith(".xml"):
            continue
        rows = []
        count = 0
        formulas = 0
        for _event, row in ET.iterparse(io.BytesIO(w.read(sn)), events=["end"]):
            if row.tag != "{" + ns["s"] + "}row":
                continue
            count += 1
            if not (count <= 200000 and int(row.attrib["r"]) <= 200000):
                raise ValueError("Source audit guard rejected; inspect the condition above.")
            cells = list(row)
            if not len(cells) <= 100:
                raise ValueError("Source audit guard rejected; inspect the condition above.")
            vals = []
            for c in cells:
                coord = re.fullmatch("([A-Z]+)([0-9]+)", c.attrib["r"])
                if not coord:
                    raise ValueError("Source audit guard rejected; inspect the condition above.")
                col = 0
                for ch in coord[1]:
                    col = col * 26 + ord(ch) - 64
                if not (col <= 100 and int(coord[2]) <= 200000):
                    raise ValueError("Source audit guard rejected; inspect the condition above.")
                v = c.find("s:v", ns)
                s = v.text if v is not None else None
                if c.attrib.get("t") == "s" and s is not None:
                    s = strings[int(s)]
                if c.attrib.get("t") == "inlineStr":
                    s = "".join(t.text or "" for t in c.iter("{" + ns["s"] + "}t"))
                if c.find("s:f", ns) is not None:
                    formulas += 1
                vals.append(
                    [
                        c.attrib.get("r"),
                        s,
                        "cached_formula" if c.find("s:f", ns) is not None else "stored_value",
                    ]
                )
            if count <= 12:
                rows.append(vals)
            row.clear()
        wb["sheets"].append(
            {
                "member": sn,
                "sheet_name": sheet_map.get(sn),
                "rows": count,
                "formula_cells": formulas,
                "first_rows": rows,
            }
        )
    out["workbooks"].append(wb)
if not len(out["workbooks"]) == 2:
    raise ValueError("Source audit guard rejected; inspect the condition above.")
Path("results/characterization-source-audit").mkdir(parents=True, exist_ok=True)
Path("results/characterization-source-audit/schema.json").write_text(
    json.dumps(out, indent=2) + "\n"
)
print(json.dumps(out, indent=2))
