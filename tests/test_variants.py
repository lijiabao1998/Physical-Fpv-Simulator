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


def test_part_drag_acts_at_the_part(builds):
    base, a, _ = builds
    ea = a.realize().extras
    assert ea.cda == base.realize().extras.cda  # the frame's own drag is unchanged
    (position, areas), = ea.drag_points  # only the camera brings its own drag
    assert areas == tuple(a.params[f"action_camera.cda_{axis}"].value for axis in "xyz")
    assert position == pytest.approx((0.030, 0.0, -0.0985))


def test_drag_above_the_cg_pitches_the_nose_up_in_forward_flight(builds):
    """Camera drag acts above the CG and points backwards: a nose-up moment."""
    from dataclasses import replace
    from fpvsim.dynamics import QuadModel

    _, a, _ = builds
    ac = a.realize()
    no_points = QuadModel(ac, replace(ac.extras, drag_points=()))
    with_points = QuadModel(ac, ac.extras)
    s = with_points.initial_state(position=(0, 0, -50.0))
    s[3] = 15.0  # flying north, level, motors stopped
    gain = with_points.derivative(s, [0.0] * 4)[11] - no_points.derivative(s, [0.0] * 4)[11]
    assert gain > 0.0
    lever = ac.mass_props.cg[2] - (-0.0985)  # camera is above the CG (smaller z)
    drag = 0.5 * ac.env.rho * 15.0**2 * ac.extras.drag_points[0][1][0]
    assert gain * with_points.inertia[1][1] == pytest.approx(lever * drag, rel=0.05)


def test_frame_drag_acts_at_a_fixed_point_of_the_airframe(builds):
    """The frame's drag centre does not move with the payload: with the CG raised by
    the camera, frame drag acts below the CG and pitches the nose down in forward flight."""
    from dataclasses import replace
    from fpvsim.dynamics import QuadModel

    base, a, _ = builds
    ac = a.realize()
    assert ac.extras.cda_center == base.realize().extras.cda_center
    clean = QuadModel(ac, replace(ac.extras, drag_points=(), cda=(0.0, 0.0, 0.0)))
    frame = QuadModel(ac, replace(ac.extras, drag_points=()))
    s = frame.initial_state(position=(0, 0, -50.0))
    s[3] = 15.0  # flying north, level, motors stopped
    gain = frame.derivative(s, [0.0] * 4)[11] - clean.derivative(s, [0.0] * 4)[11]
    lever = ac.extras.cda_center[2] - ac.mass_props.cg[2]  # > 0: drag centre below the CG
    assert lever > 0.01
    drag = 0.5 * ac.env.rho * 15.0**2 * ac.extras.cda[0]
    assert gain < 0.0
    assert -gain * frame.inertia[1][1] == pytest.approx(lever * drag, rel=0.05)


def test_trimmed_thrust_to_weight(builds):
    from fpvsim.performance import full_throttle_point, trim_factor

    _, a, _ = builds
    ac = a.realize()
    offset = ac.mass_props.cg - ac.thrust_centroid
    arm = 0.07955
    assert trim_factor(ac) == pytest.approx(arm / (arm + abs(offset[0])) * arm / (arm + abs(offset[1])), rel=1e-9)
    full = full_throttle_point(ac)
    untrimmed = 4 * full.thrust * ac.thrust_interference / ac.weight
    from fpvsim.performance import evaluate
    assert evaluate(ac)["thrust_to_weight"] == pytest.approx(untrimmed * trim_factor(ac), rel=1e-12)


def test_placement_uncertainty_moves_the_cg(builds):
    base, _, _ = builds
    assert base.params["battery.offset_x"].u == pytest.approx(0.004)
    nominal = base.realize().mass_props.cg[0]
    shifted = base.realize({"battery.offset_x": 0.004}).mass_props.cg[0]
    battery = base.params["battery.mass"].value
    assert shifted - nominal == pytest.approx(0.004 * battery / base.realize().mass_props.mass, rel=1e-9)


def test_reserved_part_names_are_rejected(tmp_path):
    bad = _variant(tmp_path, f'[meta]\nextends = "{REFERENCE_BUILD}"\n[[parts]]\nname = "frame"\n'
                   'mass = {{ value = 1, unit = "g", source = "estimate", u = 0.1 }}\n'
                   'position = {{ value = [0, 0, 0], unit = "mm" }}\n'.replace("{{", "{").replace("}}", "}"))
    with pytest.raises(DesignError, match="reserved"):
        load_build(bad)


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


def test_swapped_component_gets_independent_errors(tmp_path):
    """A different physical part must not inherit the replaced part's random error,
    while the parts both versions share stay paired."""
    battery = ROOT / "data" / "components" / "batteries" / "generic-6s-1300mah.toml"
    other = tmp_path / "other-6s-1300mah.toml"
    other.write_text(battery.read_text(encoding="utf-8").replace('id = "generic-6s-1300mah"', 'id = "other-6s-1300mah"'),
                     encoding="utf-8")
    variant = _variant(tmp_path, f'[meta]\nextends = "{REFERENCE_BUILD}"\nid = "swap"\n[components]\nbattery = "{other}"\n')
    base, swapped = load_build(REFERENCE_BUILD), load_build(variant)
    a, b = base.params.sample(3, 400), swapped.params.sample(3, 400)
    assert not np.allclose(a["battery.mass"], b["battery.mass"])  # independent parts
    assert np.std(b["battery.mass"] - a["battery.mass"]) == pytest.approx(np.sqrt(2) * base.params["battery.mass"].u, rel=0.15)
    assert np.array_equal(a["motor.kv"], b["motor.kv"])  # the unchanged motor stays paired


def test_copied_component_file_with_edited_values_is_a_different_item(tmp_path):
    """A part file copied and edited without changing its id must not share the original's errors."""
    battery = ROOT / "data" / "components" / "batteries" / "generic-6s-1300mah.toml"
    text = battery.read_text(encoding="utf-8")
    bigger = tmp_path / "bigger-6s.toml"  # same id, edited capacity
    bigger.write_text(text.replace("value = 1300", "value = 1500", 1), encoding="utf-8")
    assert "value = 1500" in bigger.read_text(encoding="utf-8")
    variant = _variant(tmp_path, f'[meta]\nextends = "{REFERENCE_BUILD}"\nid = "bigger"\n[components]\nbattery = "{bigger}"\n')
    base, changed = load_build(REFERENCE_BUILD), load_build(variant)
    assert base.params["battery.capacity"].stream != changed.params["battery.capacity"].stream
    assert base.params["battery.r0_cell"].stream != changed.params["battery.r0_cell"].stream  # the whole pack is new
    assert base.params["motor.kv"].stream == changed.params["motor.kv"].stream


def test_revalued_inline_parameter_gets_its_own_stream(tmp_path):
    text = REFERENCE_BUILD.read_text(encoding="utf-8").replace('"../', f'"{REFERENCE_BUILD.parent}/../')
    heavier = tmp_path / "heavier.toml"
    heavier.write_text(text.replace('name = "wiring"\nmass = { value = 6,', 'name = "wiring"\nmass = { value = 9,'), encoding="utf-8")
    base, changed = load_build(REFERENCE_BUILD), load_build(heavier)
    assert base.params["wiring.mass"].stream != changed.params["wiring.mass"].stream
    assert base.params["capacitor.mass"].stream == changed.params["capacitor.mass"].stream


def test_variant_has_its_own_identity(tmp_path):
    build = load_build(_variant(tmp_path, f'[meta]\nextends = "{REFERENCE_BUILD}"\n', "nameless.toml"))
    base = load_build(REFERENCE_BUILD)
    assert build.id == "nameless" and build.name == "nameless" and build.description == ""
    assert build.id != base.id


def test_compare_rejects_a_different_spec(tmp_path):
    from fpvsim.compare import compare
    from fpvsim.flightcontroller import load_fc_config

    spec = ROOT / "data" / "specs" / "freestyle-5in-6s.toml"
    relaxed = tmp_path / "relaxed.toml"
    relaxed.write_text(spec.read_text(encoding="utf-8").replace("max = 600", "max = 750"), encoding="utf-8")
    variant = _variant(tmp_path, f'[meta]\nextends = "{VERSION_A}"\nid = "relaxed"\nspec = "{relaxed}"\n')
    with pytest.raises(ValueError, match="different spec"):
        compare([REFERENCE_BUILD, variant], load_fc_config(ROOT / "data" / "fc" / "acro-5in-baseline.toml"),
                samples=5, maneuver=None, tune=False)
    with pytest.raises(ValueError, match="unknown maneuver"):
        compare([REFERENCE_BUILD, VERSION_A], load_fc_config(ROOT / "data" / "fc" / "acro-5in-baseline.toml"),
                samples=5, maneuver="loop-de-loop", tune=False)


def test_design_changes_list_parameters_of_one_version_only(builds):
    base, a, b = builds
    kinds = {(c.kind, c.item) for c in design_changes(base, a)}
    # the camera's own parameters belong to the added part row, not separate rows
    assert not any(k == "param_added" and item.startswith("action_camera.") for k, item in kinds)
    assert ("value", "battery.offset_x") not in kinds  # unchanged placement uncertainty
    kinds_b = {(c.kind, c.item) for c in design_changes(base, b)}
    assert ("moved", "battery") in kinds_b


def test_delta_sensitivity_scopes(builds):
    from fpvsim.compare import delta_sensitivity

    base, a, _ = builds
    bars = delta_sensitivity(base, a, ("auw", "endurance"))
    by_key = {bar.key: bar for bar in bars["auw"]}
    assert by_key["action_camera.mass"].scope == "variant"
    assert by_key["motor.kv"].scope == "shared"
    # AUW difference depends only on the added parts' masses
    assert by_key["motor.mass"].span == pytest.approx(0.0, abs=1e-12)
    assert by_key["action_camera.mass"].span == pytest.approx(2 * a.params["action_camera.mass"].u, rel=1e-9)
    # endurance difference also depends on shared powertrain parameters
    assert {bar.key for bar in bars["endurance"][:6]} & {"prop.cp_scale", "prop.ct_scale", "motor.i0_speed_fraction"}


def test_compare_report_signs_a_lighter_version(tmp_path):
    from fpvsim.cli import main

    lighter = _variant(tmp_path, f'[meta]\nextends = "{REFERENCE_BUILD}"\nid = "light"\nname = "輕量版"\n'
                       'change = "拿掉線材"\nremove_parts = ["wiring"]\n', "light.toml")
    out = tmp_path / "cmp"
    assert main(["compare", str(REFERENCE_BUILD), str(lighter), "--fc", str(ROOT / "data" / "fc" / "acro-5in-baseline.toml"),
                 "--samples", "20", "--no-fly", "--no-tune", "--out", str(out)]) == 0
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "全備重量 -6 g" in report and "+-" not in report
    assert "拿掉線材" in report


def test_delta_bar_effect_is_one_sided():
    """A placement error that pushes the CG off-centre either way acts one-sidedly;
    the ranking uses the larger side, not half the span."""
    from fpvsim.compare import DeltaBar

    bar = DeltaBar("battery.offset_x", "shared", low=-2.906, high=-3.439, nominal=-2.896)
    assert bar.effect == pytest.approx(0.543)
    assert bar.span / 2 == pytest.approx(0.2665)
