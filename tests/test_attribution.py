import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import physical_fpv.attribution as attribution
from physical_fpv.attribution import TEC_BSD_3_CLAUSE_NOTICE, write_evidence_attribution

ROOT = Path(__file__).resolve().parents[1]


def test_chen_authors_match_manifest_and_data_license_remains_separate(tmp_path):
    report = write_evidence_attribution(tmp_path, ["chen2020"])
    source = report["datasets"][0]
    manifest = json.loads((ROOT / "data/manifest.json").read_text())
    assert source["authors"] == manifest["authors"]
    assert len(source["authors"]) == 6
    assert source["doi"] == manifest["dataset_doi"]
    assert source["license"] == "CC-BY-4.0"
    assert source["license_url"] == "https://creativecommons.org/licenses/by/4.0/"
    assert report["software"][0]["license"] == "BSD-3-Clause"
    assert report["original_project_code_license"] == "No license has been selected."
    assert not (tmp_path / "licenses/TEC-BSD-3-Clause.txt").exists()


def test_thermal_validation_and_parameter_measurements_have_distinct_attribution(tmp_path):
    report = write_evidence_attribution(tmp_path, ["tec_validation", "oregan2022_parameters"])
    validation, parameters = report["datasets"]
    manifest = json.loads((ROOT / "data/thermal-manifest.json").read_text())
    assert validation["authors"] == manifest["data_authors"]
    assert validation["doi"] == "10.5281/zenodo.4864437"
    assert validation["license"] == "BSD-3-Clause"
    assert validation["copyright"] == "Copyright (c) 2020, Ferran Brosa Planella"
    assert "other-open" in validation["license_basis"]
    assert parameters["doi"] == "10.5281/zenodo.5171874"
    assert parameters["license"] == "CC-BY-4.0"
    assert parameters["authors"] == [
        "O'Regan, Kieran",
        "Brosa-Planella, Ferran",
        "Widanage, W. Dhammika",
        "Kendrick, Emma",
    ]
    assert "does not replace this data license" in parameters["modifications"]


def test_full_tec_notice_is_preserved_in_all_bundle_formats(tmp_path):
    original = (ROOT / "data/licenses/TEC-BSD-3-Clause.txt").read_text()
    assert TEC_BSD_3_CLAUSE_NOTICE == original
    report = write_evidence_attribution(tmp_path, ["tec_validation"])
    assert report["datasets"][0]["license_notice"] == original
    assert (tmp_path / "licenses/TEC-BSD-3-Clause.txt").read_text() == original
    assert original in (tmp_path / "ATTRIBUTION.md").read_text()


def test_written_bundle_contains_authors_sources_and_change_disclosures(tmp_path):
    output = tmp_path / "nested" / "evidence"
    ids = ["chen2020", "tec_validation", "oregan2022_parameters"]
    report = write_evidence_attribution(str(output), iter(ids + ["chen2020"]))
    assert json.loads((output / "source-attribution.json").read_text()) == report
    assert [source["id"] for source in report["datasets"]] == ids
    markdown = (output / "ATTRIBUTION.md").read_text()
    for source in report["datasets"]:
        for author in source["authors"]:
            assert author in markdown
        for field in ("doi", "paper_doi", "license_url", "modifications"):
            assert source[field] in markdown
    assert "Celsius to Kelvin" in report["datasets"][0]["modifications"]
    assert "last row at duplicate timestamps" in report["datasets"][1]["modifications"]
    assert "not a blanket license" in markdown


@pytest.mark.parametrize("bad_id", ["unknown", "Chen2020", "", "../escape", None, 4032561, []])
def test_invalid_dataset_id_fails_before_creating_output(tmp_path, bad_id):
    output = tmp_path / "not-created"
    with pytest.raises(ValueError, match="Unknown attribution dataset ID"):
        write_evidence_attribution(output, ["chen2020", bad_id])
    assert not output.exists()


def test_single_string_is_rejected_without_writes(tmp_path):
    with pytest.raises(TypeError, match="not a single string"):
        write_evidence_attribution(tmp_path / "not-created", "chen2020")
    assert not (tmp_path / "not-created").exists()


def test_empty_sources_and_returned_metadata_do_not_mutate_packaged_constants(tmp_path):
    first = write_evidence_attribution(tmp_path / "first", ["chen2020"])
    first["datasets"][0]["authors"].clear()
    first["software"][0]["authors"].clear()
    second = write_evidence_attribution(tmp_path / "second", ["chen2020"])
    assert len(second["datasets"][0]["authors"]) == 6
    assert len(second["software"][0]["authors"]) == 5
    empty = write_evidence_attribution(tmp_path / "empty", [])
    assert empty["datasets"] == []
    assert empty["software"][0]["name"] == "PyBaMM"


def test_package_module_exports_without_repository_or_dependencies(tmp_path):
    # A minimal installed-package layout deliberately contains no data/ or docs/.
    install = tmp_path / "installed"
    package = install / "physical_fpv"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    shutil.copyfile(attribution.__file__, package / "attribution.py")
    output = tmp_path / "evidence"
    script = (
        "import sys; "
        f"sys.path.insert(0, {str(install)!r}); "
        "from physical_fpv.attribution import write_evidence_attribution; "
        f"write_evidence_attribution({str(output)!r}, "
        "['chen2020', 'tec_validation', 'oregan2022_parameters'])"
    )
    subprocess.run([sys.executable, "-I", "-S", "-c", script], cwd=tmp_path, check=True)
    assert (output / "licenses/TEC-BSD-3-Clause.txt").read_text() == TEC_BSD_3_CLAUSE_NOTICE
    report = json.loads((output / "source-attribution.json").read_text())
    assert len(report["datasets"]) == 3


def test_cli_simulation_export_keeps_code_and_dataset_licenses_separate(tmp_path):
    from physical_fpv.cli import main

    assert main(["simulate", "--model", "SPM", "--out", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "source-attribution.json").read_text())
    assert report["datasets"] == []
    assert report["software"][0]["license"] == "BSD-3-Clause"
    assert "No license" in report["original_project_code_license"]
