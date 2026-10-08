"""Self-contained source notices for exported evidence, distinct from code licensing."""

from __future__ import annotations

import json
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path

CC_BY_4_URL = "https://creativecommons.org/licenses/by/4.0/"
TEC_LICENSE_URL = "https://github.com/brosaplanella/TEC-reduced-model/blob/v1.0/LICENSE"

# Kept inside the installed package: an evidence export cannot depend on a checkout.
TEC_BSD_3_CLAUSE_NOTICE = """BSD 3-Clause License

Copyright (c) 2020, Ferran Brosa Planella
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

_DATASETS = {
    "chen2020": {
        "title": "Chen et al. LG M50 full-cell validation data (2020)",
        "authors": [
            "Chen, Chang-Hui",
            "Brosa Planella, Ferran",
            "O'Regan, Kieran",
            "Gastol, Dominika",
            "Widanage, W. Dhammika",
            "Kendrick, Emma",
        ],
        "doi": "10.5281/zenodo.4032561",
        "source_url": "https://zenodo.org/records/4032561",
        "paper_doi": "10.1149/1945-7111/ab9050",
        "license": "CC-BY-4.0",
        "license_url": CC_BY_4_URL,
        "modifications": (
            "Downloaded source CSVs are unmodified. Analysis selects complete discharge "
            "steps 7, 12, 17 and 22 and converts measured temperatures from Celsius to Kelvin. "
            "Generated comparisons, interpolated residuals and metrics are derived analyses; "
            "they are not original measurements. No smoothing, curve stretching or fitting."
        ),
    },
    "tec_validation": {
        "title": "TEC-reduced-model v1.0 thermal validation archive",
        "authors": ["Ferran Brosa Planella", "Muhammad Sheikh", "W. Dhammika Widanage"],
        "archive_creator": "Ferran Brosa Planella",
        "authors_basis": "Related source-paper authors; archive creator is Ferran Brosa Planella.",
        "doi": "10.5281/zenodo.4864437",
        "source_url": "https://zenodo.org/records/4864437",
        "paper_doi": "10.1016/j.electacta.2021.138524",
        "license": "BSD-3-Clause",
        "license_url": TEC_LICENSE_URL,
        "license_basis": "v1.0 archive LICENSE; Zenodo record label is other-open",
        "copyright": "Copyright (c) 2020, Ferran Brosa Planella",
        "license_notice": TEC_BSD_3_CLAUSE_NOTICE,
        "license_notice_file": "licenses/TEC-BSD-3-Clause.txt",
        "modifications": (
            "The downloaded archive is unmodified. Analysis selects the first contiguous "
            "discharge, retains the last row at duplicate timestamps, converts Celsius to "
            "Kelvin and changes discharge current to a positive magnitude. "
            "Initial cell temperature "
            "uses the preceding rest; electrode concentrations stay published and nominal "
            "ambient is used by the model. Generated "
            "comparisons, interpolated residuals and integrated metrics are derived analyses. "
            "Duplicate conflicts and source quality warnings are retained in the reports."
        ),
    },
    "stanford2021": {
        "title": "Catenaro and Onori experimental galvanostatic battery data, version 2",
        "authors": ["Edoardo Catenaro", "Simona Onori"],
        "doi": "10.17632/kxsbr4x3j2.2",
        "source_url": "https://data.mendeley.com/datasets/kxsbr4x3j2/2",
        "paper_doi": "10.1016/j.dib.2021.106894",
        "license": "CC-BY-4.0",
        "license_url": CC_BY_4_URL,
        "modifications": (
            "Original XLSX workbooks are retained unchanged and checked against official "
            "file SHA256 digests. Inspection describes every contiguous protocol step. "
            "Derived discharge exports preserve the measured step clock and current sign "
            "and convert surface temperature from Celsius to Kelvin. No smoothing, "
            "initial-SOC fitting, time stretching or inferred points fill the missing start. "
            "Derived summaries are not new physical measurements or a validation claim."
        ),
    },
    "oregan2022_parameters": {
        "title": "O'Regan et al. thermal-electrochemical parameter measurements",
        "authors_basis": "Related source-paper authors; record-level creator list not refreshed.",
        "authors": [
            "O'Regan, Kieran",
            "Brosa-Planella, Ferran",
            "Widanage, W. Dhammika",
            "Kendrick, Emma",
        ],
        "doi": "10.5281/zenodo.5171874",
        "source_url": "https://zenodo.org/records/5171874",
        "paper_doi": "10.1016/j.electacta.2022.140700",
        "license": "CC-BY-4.0",
        "license_url": CC_BY_4_URL,
        "modifications": (
            "Measurement-source provenance for the published ORegan2022 parameterization. "
            "The model uses the installed PyBaMM implementation of published functions "
            "and corrections; no new parameter fitting is performed. Model outputs are "
            "derived calculations, not redistributed parameter-measurement records. "
            "PyBaMM's BSD-3-Clause software license does not replace this data license."
        ),
    },
}

_PYBAMM = {
    "name": "PyBaMM",
    "authors": [
        "Valentin Sulzer",
        "Scott G. Marquis",
        "Robert Timms",
        "Martin Robinson",
        "S. Jon Chapman",
    ],
    "doi": "10.5334/jors.309",
    "source_url": "https://github.com/pybamm-team/PyBaMM",
    "license": "BSD-3-Clause",
    "license_url": "https://github.com/pybamm-team/PyBaMM/blob/main/LICENSE.txt",
    "scope": "Software implementation only; measurement-data licenses are listed separately.",
}


def write_evidence_attribution(output_dir: str | Path, datasets: Iterable[str]) -> dict:
    """Write portable JSON/Markdown attribution and any required full source notice.

    Dataset IDs include ``chen2020``, ``tec_validation``, ``oregan2022_parameters``
    and ``stanford2021``.
    Callers select the sources actually used; an empty iterable covers code-only output.
    Repeated IDs are included once. All IDs are validated before creating output files.
    This records source licenses and does not select a license for original project code.
    """
    if isinstance(datasets, (str, bytes)):
        raise TypeError("datasets must be an iterable of dataset IDs, not a single string")
    selected = []
    for dataset_id in datasets:
        if not isinstance(dataset_id, str) or dataset_id not in _DATASETS:
            raise ValueError(f"Unknown attribution dataset ID: {dataset_id!r}")
        if dataset_id not in selected:
            selected.append(dataset_id)
    sources = [{"id": key, **deepcopy(_DATASETS[key])} for key in selected]
    report = {
        "schema_version": 1,
        "datasets": sources,
        "software": [deepcopy(_PYBAMM)],
        "original_project_code_license": "No license has been selected.",
        "scope": (
            "Source licenses remain separate. This attribution is not a blanket license "
            "for the evidence bundle or original project code. Cited authors and projects "
            "do not endorse this analysis. Source paper licenses are not inferred from "
            "dataset licenses."
        ),
    }
    lines = ["# Evidence source attribution", "", report["scope"], ""]
    for source in sources:
        lines.extend(
            [
                f"## {source['title']}",
                "",
                f"Authors: {'; '.join(source['authors'])}",
                "Attribution basis: " + source.get("authors_basis", "Dataset record creator list"),
                f"Source: https://doi.org/{source['doi']}",
                f"Record: {source['source_url']}",
                f"Related paper: https://doi.org/{source['paper_doi']}",
                f"License: {source['license']} ({source['license_url']})",
                f"Changes and use: {source['modifications']}",
                "",
            ]
        )
        if "license_notice" in source:
            lines.extend([source["license_basis"], "", source["license_notice"], ""])
    lines.extend(
        [
            "## Software, separately licensed",
            "",
            f"PyBaMM: {'; '.join(_PYBAMM['authors'])}",
            f"Citation: https://doi.org/{_PYBAMM['doi']}",
            f"License: {_PYBAMM['license']} ({_PYBAMM['license_url']})",
            _PYBAMM["scope"],
            "",
            "Original project code: " + report["original_project_code_license"],
            "",
        ]
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for source in sources:
        if "license_notice" in source:
            notice = output / source["license_notice_file"]
            notice.parent.mkdir(parents=True, exist_ok=True)
            notice.write_text(source["license_notice"], encoding="utf-8")
    (output / "source-attribution.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )
    (output / "ATTRIBUTION.md").write_text("\n".join(lines), encoding="utf-8")
    return report
