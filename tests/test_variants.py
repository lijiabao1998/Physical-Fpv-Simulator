"""Stage 7: design versions (extends), drag buildup, paired comparison."""

import numpy as np
import pytest

from fpvsim.compare import analyse_version, design_changes, flight_summary
from fpvsim.design import DesignError, load_build
from fpvsim.pilot import MANEUVERS
from fpvsim.sim import SimSettings, simulate

from conftest import REFERENCE_BUILD, ROOT

BUILDS = ROOT / "data" / "builds"
VERSION_A = BUILDS / "ref-5in-6s-freestyle-actioncam-a.toml"
VERSION_B = BUILDS / "ref-5in-6s-freestyle-actioncam-b.toml"


@pytest.fixture(scope="module")
def builds(reference_build):
    return reference_build, load_build(VERSION_A), load_build(VERSION_B)


def test_variant_inherits_base_and_adds_parts(builds):
    base, a, _ = builds
    names_base = [p.name for p in base.parts]
    names_a = [p.name for p in a.parts]
    assert names_a[: len(names_base)] == names_base  # base parts kept, in order
    assert names_a[len(names_base) :] == ["action_camera", "camera_mount"]
    added = a.params["action_camera.mass"].value + a.params["camera_mount.mass"].value
    assert a.realize().mass_props.mass - base.realize().mass_props.mass == pytest.approx(added, rel=1e-12)
    assert [l["id"] for l in a.lineage] == [base.id, a.id]
    assert REFERENCE_BUILD.resolve() in a.files and VERSION_A.resolve() in a.files
    assert a.input_hash() != base.input_hash()


def test_variant_replaces_parts_by_name(builds):
    base, _, b = builds
    battery = {p.name: p for p in b.parts}["battery"]
    assert battery.position[0] == pytest.approx(-0.020)
    assert len(b.parts) == len(base.parts) + 2  # battery replaced, not duplicated


def test_drag_buildup_adds_part_areas(builds):
    base, a, _ = builds
    extra = [a.params[f"action_camera.cda_{axis}"].value for axis in "xyz"]
    for k in range(3):
        assert a.realize().extras.cda[k] == pytest.approx(base.realize().extras.cda[k] + extra[k], rel=1e-12)


def _variant(tmp_path, text, name="variant.toml"):
    path = tmp_path / name
    path.write_text('schema = "fpvsim.build/1"\n' + text, encoding="utf-8")
    return path


def test_extends_works_from_another_directory_and_removes_parts(tmp_path):
    path = _variant(tmp_path, f'[meta]\nextends = "{REFERENCE_BUILD}"\nid = "v"\nremove_parts = ["wiring"]\n')
    build = load_build(path)
    assert "wiring" not in [p.name for p in build.parts]
    assert "wiring.mass" not in build.params


def test_extends_errors(tmp_path):
    bad = _variant(tmp_path, f'[meta]\nextends = "{REFERENCE_BUILD}"\nremove_parts = ["no_such_part"]\n')
    with pytest.raises(DesignError, match="remove_parts"):
        load_build(bad)
    first = tmp_path / "first.toml"
    second = _variant(tmp_path, f'[meta]\nextends = "{first}"\n', "second.toml")
    _variant(tmp_path, f'[meta]\nextends = "{second}"\n', "first.toml")
    with pytest.raises(DesignError, match="circular"):
        load_build(first)


def test_design_changes_list(builds):
    base, a, b = builds
    kinds_a = {(c.kind, c.item) for c in design_changes(base, a)}
    assert kinds_a == {("added", "action_camera"), ("added", "camera_mount")}
    kinds_b = {(c.kind, c.item) for c in design_changes(base, b)}
    assert ("moved", "battery") in kinds_b and ("added", "action_camera") in kinds_b
    assert design_changes(base, base) == []


def test_paired_monte_carlo_isolates_the_change(builds):
    """With common random numbers, the AUW difference in every sample is exactly
    the sampled camera + mount mass: nothing else varies between versions."""
    base, a, _ = builds
    n = 40
    vb, va = analyse_version(base, n, seed=5), analyse_version(a, n, seed=5)
    delta = va.mc.outputs["auw"] - vb.mc.outputs["auw"]
    added = va.mc.inputs["action_camera.mass"] + va.mc.inputs["camera_mount.mass"]
    assert np.allclose(delta, added, rtol=0, atol=1e-12)
    # heavier with the same powertrain: shorter endurance and lower T/W in every sample
    assert np.all(va.mc.outputs["endurance"] < vb.mc.outputs["endurance"])
    assert np.all(va.mc.outputs["thrust_to_weight"] < vb.mc.outputs["thrust_to_weight"])


def test_flight_summary_reads_freestyle_elements(reference_build):
    from fpvsim.flightcontroller import load_fc_config

    cfg = load_fc_config(ROOT / "data" / "fc" / "acro-5in-baseline.toml")
    man = MANEUVERS["freestyle"]
    log = simulate(reference_build, cfg, man, SimSettings(log_rate=250), duration=8.5)
    summary = flight_summary(log, man, reference_build.battery_series)
    assert summary["forward_speed"] == pytest.approx(10.0, abs=1.0)
    assert summary["forward_pitch"] > 5.0  # nose down to fly forward
    assert summary["flip_alt_loss"] > 0.0  # a flip from a settled hover always loses height
    assert "punch_alt_gain" not in summary  # elements after the end of the log are skipped
    assert not summary["crashed"]


def test_compare_report_without_flights(tmp_path):
    from fpvsim.cli import main

    out = tmp_path / "cmp"
    assert main(["compare", str(REFERENCE_BUILD), str(VERSION_A), str(VERSION_B),
                 "--fc", str(ROOT / "data" / "fc" / "acro-5in-baseline.toml"),
                 "--samples", "30", "--no-fly", "--no-tune", "--out", str(out)]) == 0
    report = (out / "report.md").read_text(encoding="utf-8")
    for section in ("## 1. 設計變更", "## 2. 規格符合度", "## 3. 性能對照", "## 4. 質量、重心與慣性"):
        assert section in report
    assert "`action_camera`" in report and "`battery`" in report
    for figure in ("deltas.png", "side_views.png", "endurance.png"):
        assert (out / figure).stat().st_size > 0
