from dataclasses import replace

import numpy as np
import pytest

from fpvsim.design import DesignError, check_sources, load_build
from fpvsim.performance import evaluate, hover_endurance, hover_point
from fpvsim.uncertainty import monte_carlo, tornado

from conftest import REFERENCE_BUILD


def test_reference_build_loads_with_complete_provenance(reference_build):
    assert check_sources(reference_build) == []
    assert len(reference_build.rotors) == 4
    assert all(p.source for p in reference_build.params)
    assert reference_build.prop_curves.ct[0] > 0


def test_hover_net_thrust_equals_weight(reference_build):
    ac = reference_build.realize()
    op = hover_point(ac)
    assert op.n_rotors * op.thrust * ac.thrust_interference == pytest.approx(ac.weight, rel=1e-12)


def test_endurance_converges_with_time_step(reference_build):
    ac = reference_build.realize()
    coarse = hover_endurance(ac, dt=1.0).endurance
    fine = hover_endurance(ac, dt=0.25).endurance
    assert coarse == pytest.approx(fine, rel=2e-3)


def test_endurance_charge_balance(reference_build):
    """Charge drawn during the run equals the charge between full and the end state."""
    ac = reference_build.realize()
    run = hover_endurance(ac, dt=1.0)
    drawn = np.sum(run.i_bus) * 1.0  # constant current per step
    assert drawn == pytest.approx((1.0 - run.soc[-1]) * ac.battery.capacity + run.i_bus[-1] * 1.0, rel=1e-9)
    if run.reason == "reserve_soc":
        assert run.endurance * np.mean(run.i_bus) == pytest.approx(
            (1.0 - ac.criteria.reserve_soc) * ac.battery.capacity, rel=0.02
        )


def test_heavier_aircraft_hovers_harder_and_shorter(reference_build):
    base = evaluate(reference_build.realize())
    heavy = evaluate(reference_build.realize({"battery_strap.mass": 0.056}))  # +50 g
    assert heavy["auw"] - base["auw"] == pytest.approx(0.050)
    assert heavy["hover_duty"] > base["hover_duty"]
    assert heavy["endurance"] < base["endurance"]
    assert heavy["thrust_to_weight"] < base["thrust_to_weight"]


def test_monte_carlo_is_reproducible(reference_build):
    a = monte_carlo(reference_build, n=20, seed=7)
    b = monte_carlo(reference_build, n=20, seed=7)
    c = monte_carlo(reference_build, n=20, seed=8)
    assert np.array_equal(a.outputs["endurance"], b.outputs["endurance"])
    assert not np.array_equal(a.outputs["endurance"], c.outputs["endurance"])


def test_monte_carlo_without_uncertainty_has_no_spread(reference_build):
    exact = replace(reference_build, params=_without_uncertainty(reference_build.params))
    result = monte_carlo(exact, n=5, seed=1)
    assert np.ptp(result.outputs["endurance"]) == 0.0


def _without_uncertainty(params):
    from fpvsim.params import ParamSet

    out = ParamSet()
    for p in params:
        out.add(replace(p, u=0.0))
    return out


def test_tornado_signs(reference_build):
    _, bars = tornado(reference_build, ["endurance", "auw"])
    by_key = {b.key: b for b in bars["endurance"]}
    assert by_key["battery.capacity"].high > by_key["battery.capacity"].low
    assert by_key["battery.mass"].high < by_key["battery.mass"].low
    assert bars["auw"][0].key == "battery.mass"  # the heaviest uncertain item dominates AUW


def test_compliance_probability(reference_build):
    result = monte_carlo(reference_build, n=50, seed=1)
    for req in reference_build.spec.requirements:
        p = result.probability_of_compliance(req)
        assert 0.0 <= p <= 1.0
        assert result.probability_stderr(p) <= 0.5 / np.sqrt(50) + 1e-12


def _write(path, text):
    path.write_text(text)
    return path


def test_misplaced_top_level_key_is_rejected(tmp_path):
    comp = _write(
        tmp_path / "fc.toml",
        'schema = "fpvsim.component/1"\n[meta]\nid = "x"\nmass = { value = 7, unit = "g", source = "estimate", u = 1 }\n',
    )
    build = REFERENCE_BUILD.read_text().replace(
        "../components/electronics/generic-fc-30x30.toml", str(comp)
    ).replace('"../', f'"{REFERENCE_BUILD.parent}/../')
    with pytest.raises(DesignError, match="inside \\[meta\\]"):
        load_build(_write(tmp_path / "build.toml", build))


def test_unknown_requirement_metric_is_rejected(tmp_path):
    spec_path = REFERENCE_BUILD.parent.parent / "specs" / "freestyle-5in-6s.toml"
    spec = _write(tmp_path / "spec.toml", spec_path.read_text().replace('metric = "auw"', 'metric = "awesomeness"'))
    build = REFERENCE_BUILD.read_text().replace('"../specs/freestyle-5in-6s.toml"', f'"{spec}"').replace(
        '"../', f'"{REFERENCE_BUILD.parent}/../'
    )
    with pytest.raises(DesignError, match="unknown metric"):
        load_build(_write(tmp_path / "build.toml", build))


def test_cli_summary_and_report(tmp_path, capsys):
    from fpvsim.cli import main

    assert main(["summary", str(REFERENCE_BUILD)]) == 0
    assert "Hover endurance" in capsys.readouterr().out
    assert main(["check", str(REFERENCE_BUILD)]) == 0
    assert main(["report", str(REFERENCE_BUILD), "--out", str(tmp_path), "--samples", "20"]) == 0
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    for section in ("## 1. 規格符合度", "## 3. 質量預算", "## 7. 設計點（最差工況）", "## 8. 不確定度與敏感度",
                    "## 10. 參數來源總表"):
        assert section in report
    for figure in ("stand.png", "endurance.png", "burst.png", "layout.png", "monte_carlo.png", "tornado_endurance.png"):
        assert (tmp_path / figure).stat().st_size > 0


def test_cli_fit_prop_round_trip(reference_build, tmp_path, capsys):
    from fpvsim.cli import main
    from fpvsim.stand import run_stand, write_csv

    ac = reference_build.realize()
    path = tmp_path / "stand.csv"
    write_csv(run_stand(ac, 25.2), path)
    assert main(["fit-prop", str(path), "--diameter", "5.1in", "--temperature", "15degC"]) == 0
    out = capsys.readouterr().out
    assert f"ct0 = {ac.powertrain.prop.ct0:.5f}" in out


def test_battery_must_be_placed_exactly_once(tmp_path):
    text = REFERENCE_BUILD.read_text().replace('"../', f'"{REFERENCE_BUILD.parent}/../')
    unplaced = text.replace('name = "battery"\nuses = "battery"', 'name = "battery"\nuses = "esc"')
    with pytest.raises(DesignError, match="exactly once"):
        load_build(_write(tmp_path / "build.toml", unplaced))
