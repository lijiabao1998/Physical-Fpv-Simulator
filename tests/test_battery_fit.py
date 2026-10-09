"""Battery identification: virtual HPPC bench and in-flight fit recover known parameters."""

import numpy as np
import pytest

from fpvsim.battery import BatteryState
from fpvsim.battery_fit import fit_arrhenius, fit_flight, fit_hppc
from fpvsim.battery_test import HppcProtocol, run_hppc
from fpvsim.design import load_build

from conftest import REFERENCE_BUILD

QUICK = HppcProtocol(soc_step=0.3, rest_before_s=150.0)


@pytest.fixture(scope="module")
def battery():
    return load_build(REFERENCE_BUILD).realize().battery


def test_hppc_fit_recovers_the_pack(battery):
    fit = fit_hppc(run_hppc(battery, 298.15, QUICK, seed=3), battery.series, battery.capacity)
    assert len(fit.pulses) == 4
    for est, true in ((fit.r0_cell, battery.r0_cell), (fit.r1_cell, battery.r1_cell), (fit.tau1, battery.tau1)):
        assert abs(est.value - true) < 3 * est.u + 0.005 * true
    # the relaxed voltage before each pulse is the open-circuit voltage
    expected = np.interp(fit.ocv_soc, battery.ocv_soc, battery.ocv_cell)
    assert np.allclose(fit.ocv_cell, expected, atol=0.003)


def test_arrhenius_from_two_chamber_temperatures(battery):
    fits = [fit_hppc(run_hppc(battery, t, QUICK, seed=s), battery.series, battery.capacity)
            for t, s in ((298.15, 1), (273.15, 2))]
    arr = fit_arrhenius(fits)
    assert abs(arr.activation_energy.value - battery.activation_energy) < 3 * arr.activation_energy.u + 300.0
    with pytest.raises(ValueError, match="two or more temperatures"):
        fit_arrhenius(fits[:1])


def test_flight_fit_recovers_pack_plus_wiring(battery):
    """A synthetic flight: random punches and hover, voltage measured behind extra wiring, with noise."""
    rng = np.random.default_rng(5)
    dt, harness = 0.01, 0.0025
    t = np.arange(0, 60, dt)
    current = 4.0 + 60.0 * (np.sin(t / 3.0) > 0.7) + rng.normal(0, 0.5, len(t)).clip(-3, 3)
    state = BatteryState(1.0, 0.0, battery.r_ref_temperature)
    v = []
    for i in current:
        v.append(state.source_voltage(battery) - i * (battery.r0 + harness))
        state = state.step(battery, i, dt)
    vbat = np.array(v) + rng.normal(0, 0.01, len(t))
    fit = fit_flight(t, vbat, current, battery.ocv_soc, battery.ocv_cell * battery.series, battery.capacity)
    assert fit.r_total.value == pytest.approx(battery.r0 + harness, rel=0.03)
    assert fit.r1.value == pytest.approx(battery.r1, rel=0.15)


def test_cli_hppc_and_fit_battery(tmp_path, capsys):
    from fpvsim.cli import main

    csv = tmp_path / "hppc.csv"
    assert main(["hppc", str(REFERENCE_BUILD), "--csv", str(csv), "--soc-step", "0.3", "--rate", "5"]) == 0
    assert main(["fit-battery", str(csv), "--build", str(REFERENCE_BUILD), "--out", str(tmp_path / "fit")]) == 0
    report = (tmp_path / "fit" / "report.md").read_text(encoding="utf-8")
    assert "寫回零件檔" in report and 'source = "measured"' in report
    assert (tmp_path / "fit" / "pulses.png").stat().st_size > 0
