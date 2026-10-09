"""Exact-rational algebra and domain tests for an unchanged-RMSE feasibility set."""

from fractions import Fraction

import numpy as np
import pytest

from physical_fpv.series_loss_compatibility import coefficients, feasible_set, intersect_sets


def exact_product(t, x, y):
    # Integrate polynomial coefficients in local u=t-t0, independently of endpoint formula.
    total = Fraction(0)
    for n in range(len(t) - 1):
        h = t[n + 1] - t[n]
        sx, sy = (x[n + 1] - x[n]) / h, (y[n + 1] - y[n]) / h
        total += x[n] * y[n] * h + (x[n] * sy + y[n] * sx) * h**2 / 2 + sx * sy * h**3 / 3
    return total / (t[-1] - t[0])


def test_exact_rational_oracle_nonuniform_current_and_time():
    t = list(map(Fraction, [0, 1, 3]))
    e = [Fraction(1, 100), Fraction(-2, 100), Fraction(4, 100)]
    i = list(map(Fraction, [1, 2, 3]))
    result = coefficients(t, e, i)
    assert result["A_a2"] == pytest.approx(float(exact_product(t, i, i)), abs=1e-14)
    assert result["B_v_a"] == pytest.approx(float(exact_product(t, e, i)), abs=1e-14)
    assert result["C_v2"] == pytest.approx(float(exact_product(t, e, e)), abs=1e-14)


def test_known_constant_trace_roots_and_no_parameter_identification():
    c = coefficients([0, 2, 5], [0.2, 0.2, 0.2], [1, 1, 1])
    result = feasible_set(c, 0.1)
    assert result["interval_ohm"] == pytest.approx([0.1, 0.3])
    assert not result["resistance_identified"]
    assert not result["physical_simulation_pass"]
    for root in result["interval_ohm"]:
        assert c["A_a2"] * root**2 - 2 * c["B_v_a"] * root + c["C_v2"] == pytest.approx(0.01)


def test_time_origin_and_units_laws():
    t, e, i = np.array([0, 1, 3]), np.array([0.12, 0.14, 0.11]), np.array([1, 2, 1])
    a = coefficients(t, e, i)
    b = coefficients(100 + 7 * t, e, i)
    assert [a[k] for k in ("A_a2", "B_v_a", "C_v2")] == pytest.approx(
        [b[k] for k in ("A_a2", "B_v_a", "C_v2")]
    )
    initial = feasible_set(a, 0.05)["interval_ohm"]
    doubled = feasible_set(coefficients(t, e, 2 * i), 0.05)["interval_ohm"]
    assert doubled == pytest.approx(np.array(initial) / 2)


def test_empty_after_nonnegative_clipping():
    result = feasible_set(coefficients([0, 1], [-0.2, -0.2], [1, 1]), 0.05)
    assert result["status"] == "empty"
    assert result["interval_ohm"] is None


def test_inequality_includes_zero_when_baseline_already_passes():
    result = feasible_set(coefficients([0, 1], [0.01, 0.01], [1, 1]), 0.05)
    assert result["interval_ohm"] == pytest.approx([0, 0.06])


def test_disjoint_and_touching_shared_sets():
    def interval(lo, hi):
        return {"status": "nonempty", "interval_ohm": [lo, hi]}

    assert intersect_sets([interval(0.1, 0.2), interval(0.3, 0.4)])["status"] == "empty"
    touch = intersect_sets([interval(0.1, 0.2), interval(0.2, 0.4)])
    assert touch["status"] == "numerically_unresolved"
    assert touch["candidate_singleton_ohm_if_exact_contact"] == 0.2
    assert intersect_sets([interval(0.1, 0.21), interval(0.2, 0.4)])["interval_ohm"] == [0.2, 0.21]


def test_roundoff_does_not_relax_gate():
    result = feasible_set({"A_a2": 1.0, "B_v_a": 1.0, "C_v2": 2.0}, 1.0)
    assert result["status"] == "numerically_unresolved"
    assert result["interval_ohm"] is None
    assert result["candidate_singleton_ohm_if_exact_zero"] == 1


def test_zero_excitation_is_not_resistance_identification():
    assert feasible_set(coefficients([0, 1], [0.01, 0.01], [0, 0]))["status"] == "all_nonnegative"
    assert feasible_set(coefficients([0, 1], [0.1, 0.1], [0, 0]))["status"] == "empty"


@pytest.mark.parametrize(
    "t,e,i", [([0, 0], [1, 1], [1, 1]), ([0, 1], [1, np.nan], [1, 1]), ([0, 1], [1, 1], [-1, -1])]
)
def test_invalid_inputs_fail_closed(t, e, i):
    with pytest.raises(ValueError):
        coefficients(t, e, i)


def test_cannot_extrapolate_or_use_inconsistent_coefficients():
    with pytest.raises(ValueError):
        coefficients([0, 1], [1, 1], [1, 1], 0, 2)
    with pytest.raises(ValueError):
        feasible_set({"A_a2": 1, "B_v_a": 2, "C_v2": 1})


def test_archived_identity_preserves_distinct_sources_and_coverage(tmp_path):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("screen", "scripts/check_stanford_series_loss.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wrong = tmp_path / "bad.gz"
    wrong.write_bytes(b"not an input")
    with pytest.raises(ValueError, match="identity"):
        module.load_inputs(wrong)
    cells = module.load_inputs(Path("docs/benchmarks/stanford-series-loss-inputs.json.gz"))["cells"]
    assert cells["k1"]["provenance"]["historical_evidence_only"] is False
    assert cells["k2"]["provenance"]["historical_evidence_only"] is True
    assert cells["k1"]["common_interval_s"] != cells["k2"]["common_interval_s"]
    assert all(c["observed_tail_beyond_model_s"] > 0 for c in cells.values())
    assert all(not c["voltage_correction_or_physical_parameter_update"] for c in cells.values())


def test_shared_sets_propagate_individual_root_guards():
    a = {"status": "nonempty", "interval_ohm": [0.1, 0.2], "root_roundoff_guard_ohm": 1e-5}
    b = {"status": "nonempty", "interval_ohm": [0.200001, 0.3], "root_roundoff_guard_ohm": 1e-5}
    assert intersect_sets([a, b])["status"] == "numerically_unresolved"
    b["interval_ohm"][0] = 0.201
    assert intersect_sets([a, b])["status"] == "empty"


def test_small_positive_discriminant_amplifies_root_guard():
    result = feasible_set({"A_a2": 1.0, "B_v_a": 1.0, "C_v2": 2.0 - 1e-12}, 1.0)
    assert result["status"] == "nonempty"
    assert result["root_roundoff_guard_ohm"] > 1e-9


def test_nonlimiting_set_can_change_limiting_endpoint_within_guard():
    sets = [
        {"status": "nonempty", "interval_ohm": [0, 0.2], "root_roundoff_guard_ohm": 1e-8},
        {"status": "nonempty", "interval_ohm": [0.19, 0.4], "root_roundoff_guard_ohm": 1e-8},
        {"status": "nonempty", "interval_ohm": [0.18, 0.45], "root_roundoff_guard_ohm": 0.1},
    ]
    assert intersect_sets(sets)["status"] == "numerically_unresolved"


def test_saved_screen_reproduces_without_solve_or_download(tmp_path, monkeypatch):
    import hashlib
    import importlib.util
    import json
    import urllib.request

    import pybamm

    def forbidden(*args, **kwargs):
        raise AssertionError("Fixed-trajectory screen cannot solve or acquire data")

    monkeypatch.setattr(pybamm.Simulation, "solve", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    spec = importlib.util.spec_from_file_location("screen", "scripts/check_stanford_series_loss.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = module.ROOT / "docs/benchmarks/stanford-series-loss-inputs.json.gz"
    expected = json.loads(
        (module.ROOT / "docs/benchmarks/stanford-series-loss-compatibility.json").read_text()
    )
    actual = module.run(source, tmp_path)
    assert actual["cases"] == expected["cases"]
    assert actual["shared_feasible_set"] == expected["shared_feasible_set"]
    assert actual["shared_feasible_set"]["status"] == "empty"
    assert actual["selected_resistance_ohm"] is None
    assert not actual["corrected_electrical_validation_pass"]
    normalizer = module.ROOT / "scripts/prepare_stanford_series_loss_inputs.py"
    assert hashlib.sha256(normalizer.read_bytes()).hexdigest() == actual["normalizer_sha256"]
