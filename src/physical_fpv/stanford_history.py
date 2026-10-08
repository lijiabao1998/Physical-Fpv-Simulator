"""Classify the predeclared k2/k6 published-history premise without model runs."""

from __future__ import annotations

from physical_fpv.stanford_chronology import NAME, summarize_chronology

SELECTED_CELLS = ("k2", "k6")
RATES = ("0_05", "1", "2", "3", "5")
TEMPERATURES = ("05", "25", "35")


def aggregate_selected_histories(reports: list[dict], manifest: dict) -> dict:
    """Test only the recorded k6-prior-2C / k2-no-prior-2C contrast.

    Both full fifteen-file histories must qualify before either a true or false
    premise is reported. A partial report, unsupported clock, hash mismatch or
    ambiguous target leaves the premise unresolved. This function neither reads
    workbooks nor makes any statement about unrecorded history or causation.
    """
    selected = {cell: [] for cell in SELECTED_CELLS}
    entries = {entry["filename"]: entry for entry in manifest["files"]}
    if len(entries) != len(manifest["files"]):
        raise ValueError("Duplicate selected workbook in manifest")
    for filename, entry in entries.items():
        match = NAME.fullmatch(filename)
        if match is None or match[1] not in SELECTED_CELLS:
            raise ValueError("Unselected or cross-cell manifest workbook")
        selected[match[1]].append(entry)
    names = [report["source"]["filename"] for report in reports]
    if len(names) != len(set(names)) or set(names) - set(entries):
        raise ValueError("Duplicate or unselected workbook report")
    targets = manifest.get("target_filenames", {})
    if set(targets) - set(SELECTED_CELLS):
        raise ValueError("Unselected target cell")
    histories = {}
    for cell in SELECTED_CELLS:
        cell_manifest = {
            **manifest,
            "files": selected[cell],
            "target_filename": targets.get(cell),
        }
        cell_names = {entry["filename"] for entry in selected[cell]}
        cell_reports = [report for report in reports if report["source"]["filename"] in cell_names]
        history = summarize_chronology(cell_reports, cell_manifest, cell_id=cell)
        complete_campaign = cell_names == {
            f"NMC_{cell}_{rate}C_{temperature}degC.xlsx"
            for rate in RATES
            for temperature in TEMPERATURES
        }
        history["full_campaign_selected"] = complete_campaign
        if not complete_campaign:
            history["history_unresolved_reasons"].append("incomplete_fifteen_workbook_selection")
        if targets.get(cell) != f"NMC_{cell}_1C_25degC.xlsx":
            history["history_unresolved_reasons"].append(
                "missing_or_incorrect_nominal_25C_1C_target"
            )
        if history["history_unresolved_reasons"]:
            history["history_qualified"] = False
            history["qualified_earlier_high_rate_files"] = None
            history["recorded_prior_high_rate_exposure"] = None
        histories[cell] = history
    qualified = all(history["history_qualified"] for history in histories.values())
    holds = None
    if qualified:
        holds = (
            histories["k6"]["recorded_prior_high_rate_exposure"]
            and not histories["k2"]["recorded_prior_high_rate_exposure"]
        )
    status = "unresolved" if holds is None else "holds" if holds else "false"
    return {
        "dataset_doi": manifest["dataset_doi"],
        "license": manifest["license"],
        "authors": manifest["authors"],
        "selected_cells": list(SELECTED_CELLS),
        "target_filenames": dict(targets),
        "expected_files": len(entries),
        "inspected_files": len(reports),
        "missing_files": sorted(set(entries) - set(names)),
        "histories": histories,
        "full_histories_qualified": qualified,
        "recorded_premise_status": status,
        "recorded_premise_holds": holds,
        "recorded_premise": (
            "Strictly before each nominal 25C/1C target in the published campaign, "
            "k6 had at least one nominal >=2C experiment and k2 had none."
        ),
        "nominal_high_rate_threshold_c": 2.0,
        "qualification_scope": (
            "Both complete selected histories, source hashes, date/test and source-step clocks, "
            "supported recorded phases, no same-cell overlaps and strict target boundaries. "
            "Legacy recorded_order_qualified alone cannot establish this premise."
        ),
        "interpretation": (
            "Recorded campaign ordering only; no causal, damage, manufacturing-batch, "
            "freshness or independent-validation conclusion."
        ),
        "unrecorded_history": "Unresolved regardless of the published ordering result",
        "other_cells_history": "k3-k5 remain unqualified; k1 is prior documented context only",
        "fresh_target_established": False,
        "causation_established": False,
        "damage_established": False,
        "independent_validation_established": False,
        "model_runs": 0,
        "fitting_performed": False,
    }
