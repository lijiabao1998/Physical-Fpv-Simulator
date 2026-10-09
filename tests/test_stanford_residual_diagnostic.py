import importlib.util
from pathlib import Path

import numpy as np
import pybamm
import pytest

SPEC = importlib.util.spec_from_file_location(
    "stanford_residual_diagnostic",
    Path(__file__).resolve().parents[1] / "scripts/diagnose_stanford_residuals.py",
)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def test_linear_error_has_exact_time_integrals_on_clipped_window():
    # e(t)=t, available [1,2] inside requested [1,3]: integral(e^2)=7/3.
    result = diagnostic.residual_window(np.array([0.0, 2.0]), np.array([0.0, 2.0]), 1, 3)
    assert result["available_interval_s"] == [1.0, 2.0]
    assert result["coverage"] == 0.5
    assert result["voltage_rmse_v"] == pytest.approx(np.sqrt(7 / 3))
    assert result["signed_time_mean_error_v"] == 1.5
    assert result["squared_error_integral_v2_s"] == pytest.approx(7 / 3)


def test_unavailable_window_does_not_extrapolate():
    with pytest.raises(ValueError, match="no observed/model overlap"):
        diagnostic.residual_window(np.array([0.0, 2.0]), np.array([0.0, 2.0]), 3, 4)


def test_conditional_transfer_conserves_lithium_without_invoking_solver(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("A no-solve diagnostic must not create or execute a model")

    monkeypatch.setattr(pybamm, "Simulation", forbidden)
    monkeypatch.setattr(pybamm.lithium_ion, "DFN", forbidden)
    parameters = pybamm.ParameterValues("ORegan2022")
    initial = diagnostic.uniform_state(parameters, 0.0, 298.15)
    final = diagnostic.uniform_state(parameters, 4.7, 298.5)
    assert initial["solid_lithium_mol"] == pytest.approx(final["solid_lithium_mol"], abs=1e-14)
    for name, sign in (("negative", -1), ("positive", 1)):
        change = (
            final["electrodes"][name]["solid_lithium_mol"]
            - initial["electrodes"][name]["solid_lithium_mol"]
        )
        assert change == pytest.approx(sign * 4.7 * 3600 / float(pybamm.constants.F.value))
    assert final["uniform_ocv_v"] < initial["uniform_ocv_v"]
