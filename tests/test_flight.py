"""Verification of the flight simulation (stage 6) and tuning analysis (stage 5)."""

import math
from dataclasses import replace

import numpy as np
import pytest
from scipy.signal import cont2discrete, lfilter

from fpvsim import flightanalysis as fa
from fpvsim.blackbox import FlightLog
from fpvsim.dynamics import Outputs, QuadModel
from fpvsim.filters import PT1, Biquad, PTn
from fpvsim.flightcontroller import AxisRates, FlightController, dump_fc_config, load_fc_config, quad_mixer
from fpvsim.performance import hover_point
from fpvsim.pilot import MANEUVERS
from fpvsim.sim import SimSettings, simulate
from fpvsim.tuning import Candidate, TuningStudy, ff_dominated, robust_alternative, select

from conftest import ROOT

FC_PATH = ROOT / "data" / "fc" / "acro-5in-baseline.toml"


@pytest.fixture(scope="module")
def fc_cfg():
    return load_fc_config(FC_PATH)


@pytest.fixture(scope="module")
def aircraft(reference_build):
    return reference_build.realize()


def model(ac, **extras):
    return QuadModel(ac, replace(ac.extras, **extras))


def run(m, state, duties, dt, seconds):
    for _ in range(int(round(seconds / dt))):
        state = m.step(state, duties, dt)
    return state


def out():
    return Outputs(0.0, 0.0, [], [], [], 0.0, False, 0.0)


# ------------------------------------------------------------------ dynamics


def test_free_fall_is_exact_without_drag(aircraft):
    m = model(aircraft, cda=(0.0, 0.0, 0.0))
    s = run(m, m.initial_state(position=(0, 0, -100.0)), [0.0] * 4, 1e-3, 1.0)
    g = aircraft.env.g
    assert s[2] == pytest.approx(-100.0 + 0.5 * g, abs=1e-9)  # RK4 is exact for constant acceleration
    assert s[5] == pytest.approx(g, abs=1e-9)


def test_terminal_velocity_matches_drag_balance(aircraft):
    m = model(aircraft)
    s = run(m, m.initial_state(position=(0, 0, -5000.0)), [0.0] * 4, 2e-3, 20.0)
    cda_z = aircraft.extras.cda[2]
    v_t = math.sqrt(2 * aircraft.mass_props.mass * aircraft.env.g / (aircraft.env.rho * cda_z))
    assert s[5] == pytest.approx(v_t, rel=2e-3)


def test_torque_free_rotation_conserves_momentum_and_energy(aircraft):
    m = model(aircraft, cda=(0.0, 0.0, 0.0))
    s = m.initial_state(position=(0, 0, -1000.0))
    s[10:13] = [3.0, -2.0, 5.0]
    I = np.array(m.inertia)

    def invariants(st):
        w, q = np.array(st[10:13]), st[6:10]
        qw, qx, qy, qz = q
        R = np.array([
            [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qw * qz), 2 * (qx * qz + qw * qy)],
            [2 * (qx * qy + qw * qz), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qw * qx)],
            [2 * (qx * qz - qw * qy), 2 * (qy * qz + qw * qx), 1 - 2 * (qx * qx + qy * qy)],
        ])
        return R @ (I @ w), 0.5 * w @ I @ w

    L0, E0 = invariants(s)
    s = run(m, s, [0.0] * 4, 1.0 / 8000, 2.0)
    L1, E1 = invariants(s)
    assert np.allclose(L1, L0, rtol=1e-7, atol=1e-12)
    assert E1 == pytest.approx(E0, rel=1e-7)


def test_intermediate_axis_is_unstable(aircraft):
    """Dzhanibekov effect: a spin about the intermediate principal axis flips."""
    m = model(aircraft, cda=(0.0, 0.0, 0.0))
    moments, axes = np.linalg.eigh(np.array(m.inertia))
    mid = axes[:, 1]
    s = m.initial_state(position=(0, 0, -1000.0))
    s[10:13] = list(10.0 * mid + 0.01 * axes[:, 0])
    flipped = False
    for _ in range(40):
        s = run(m, s, [0.0] * 4, 1e-3, 0.25)
        flipped |= float(np.dot(s[10:13], mid)) < 0.0
    assert flipped
    # spin about the major axis stays put
    s = m.initial_state(position=(0, 0, -1000.0))
    s[10:13] = list(10.0 * axes[:, 2] + 0.01 * axes[:, 0])
    s = run(m, s, [0.0] * 4, 1e-3, 5.0)
    assert float(np.dot(s[10:13], axes[:, 2])) > 9.9


def test_dynamic_hover_matches_static_solution(aircraft):
    """At the static hover point the dynamic model is in force and torque balance
    (except the pitch moment from the CG offset, which must equal -x_cg W)."""
    m = model(aircraft)
    hp = hover_point(aircraft)
    s = m.initial_state(position=(0, 0, -50.0), omega=hp.omega)
    o = out()
    d = m.derivative(s, [hp.duty] * 4, out=o)
    assert d[5] == pytest.approx(0.0, abs=1e-9)  # vertical acceleration
    assert max(abs(x) for x in d[13:17]) < 1e-6 * hp.omega  # rotor speeds steady
    assert o.i_bus == pytest.approx(hp.i_bus, rel=1e-9)
    assert o.v_bus == pytest.approx(hp.v_bus, rel=1e-9)
    x_cg = aircraft.mass_props.cg[0] - aircraft.thrust_centroid[0]
    assert d[11] * m.inertia[1][1] == pytest.approx(-x_cg * aircraft.weight, rel=0.02)


def test_motor_time_constant_matches_linearisation(aircraft):
    m = model(aircraft)
    hp = hover_point(aircraft)
    s = m.initial_state(position=(0, 0, -50.0), omega=hp.omega)
    eps = 1e-3 * hp.omega
    s_plus = list(s)
    s_plus[13] += eps
    slope = (m.derivative(s_plus, [hp.duty] * 4)[13] - m.derivative(s, [hp.duty] * 4)[13]) / eps
    kq = aircraft.powertrain.prop.k_torque(aircraft.env.rho)
    expected = -(m.kt * m.ke / m.r_circuit + m.kt * m.i0_slope + 2 * kq * hp.omega) / m.j_rotor
    assert slope == pytest.approx(expected, rel=0.02)  # remainder: bus-voltage coupling through the battery
    assert 0.005 < -1 / slope < 0.1  # tens of milliseconds, as for real 5-inch motors


def test_control_moment_signs(aircraft):
    """Applying the mixer pattern of an axis for 30 ms rotates the body positively about it."""
    m = model(aircraft)
    hp = hover_point(aircraft)
    mixer = quad_mixer([r.position for r in aircraft.rotors], [r.spin for r in aircraft.rotors])
    s0 = m.initial_state(position=(0, 0, -50.0), omega=hp.omega)
    ref = run(m, s0, [hp.duty] * 4, 1e-4, 0.03)
    for axis in range(3):
        duties = [hp.duty + 0.03 * row[axis] for row in mixer]
        s = run(m, s0, duties, 1e-4, 0.03)
        assert s[10 + axis] - ref[10 + axis] > 0.05


def test_rotor_drag_opposes_motion(aircraft):
    m = model(aircraft, cda=(0.0, 0.0, 0.0))
    hp = hover_point(aircraft)
    s = m.initial_state(position=(0, 0, -50.0), omega=hp.omega)
    s[3] = 2.0  # 2 m/s north, level, nose north
    d = m.derivative(s, [hp.duty] * 4)
    expected = -m.k_rotor_drag * 4 * hp.omega * 2.0 / aircraft.mass_props.mass
    assert d[3] == pytest.approx(expected, rel=0.02)


def test_bus_power_balance(aircraft):
    m = model(aircraft)
    s = m.initial_state(position=(0, 0, -50.0), omega=900.0)
    o = out()
    duties = [0.3, 0.25, 0.35, 0.2]
    m.derivative(s, duties, out=o)
    motor_power = sum(d * o.v_bus * i for d, i in zip(duties, o.i_motor))
    assert o.v_bus * o.i_bus == pytest.approx(motor_power + m.p_aux, rel=1e-9)


def test_esc_current_limits(aircraft):
    m = model(aircraft)
    o = out()
    m.derivative(m.initial_state(position=(0, 0, -50.0), omega=300.0), [1.0] * 4, out=o)
    assert max(o.i_motor) == pytest.approx(aircraft.extras.drive_current_limit)
    m.derivative(m.initial_state(position=(0, 0, -50.0), omega=3000.0), [0.0] * 4, out=o)
    assert min(o.i_motor) == pytest.approx(-aircraft.extras.brake_current_limit)
    assert o.i_bus < 0.0  # braking returns energy to the battery


def test_ground_contact_catches_a_dropped_quad(aircraft):
    m = model(aircraft)
    lowest_point = max(c[2] for c in m.contacts)  # body z of the lowest contact, relative to the CG
    s = m.initial_state(position=(0, 0, -0.3))
    deepest = -1.0
    for _ in range(3000):
        s = m.step(s, [0.0] * 4, 1e-3)
        deepest = max(deepest, s[2] + lowest_point)
    assert abs(s[5]) < 0.01  # at rest
    assert 0.0 < deepest < 0.01  # small penetration, no tunnelling


# ------------------------------------------------------------ controller parts


def test_actual_rates_properties():
    for expo in (0.0, 0.5, 0.9):
        r = AxisRates(center=70.0, max=670.0, expo=expo)
        assert r.rate(1.0) == pytest.approx(670.0)
        assert r.rate(-0.4) == pytest.approx(-r.rate(0.4))
        assert (r.rate(1e-4) - r.rate(-1e-4)) / 2e-4 == pytest.approx(70.0, rel=1e-3)  # centre sensitivity
    # expo moves the curve between centre and max without touching either
    assert AxisRates(70, 670, 0.8).rate(0.5) < AxisRates(70, 670, 0.0).rate(0.5)


@pytest.mark.parametrize("flt", [PT1(100.0, 4000.0), PTn(2, 100.0, 4000.0), PTn(3, 100.0, 4000.0), Biquad.lowpass(100.0, 4000.0)])
def test_lowpass_is_minus_3db_at_cutoff(flt):
    assert abs(flt.response(np.array([100.0]), 4000.0)[0]) == pytest.approx(1 / math.sqrt(2), rel=0.03)


def test_filter_time_domain_matches_frequency_response():
    fs, f = 4000.0, 180.0
    for flt in (PTn(2, 120.0, fs), Biquad.notch(200.0, fs, 5.0)):
        t = np.arange(8000) / fs
        y = np.array([flt.update(x) for x in np.sin(2 * np.pi * f * t)])
        amplitude = np.sqrt(2) * np.std(y[4000:])
        assert amplitude == pytest.approx(abs(flt.response(np.array([f]), fs)[0]), rel=0.01)
    notch = Biquad.notch(200.0, fs, 5.0)
    assert abs(notch.response(np.array([200.0]), fs)[0]) < 1e-9
    assert abs(notch.response(np.array([1e-3]), fs)[0]) == pytest.approx(1.0, abs=1e-6)


def test_rpm_filter_removes_motor_line(fc_cfg):
    cfg = replace(fc_cfg, gyro_lowpass=(), dterm_lowpass=())
    mixer = quad_mixer([(-1, 1, 0), (1, 1, 0), (-1, -1, 0), (1, -1, 0)], ["cw", "ccw", "ccw", "cw"])
    rotor_hz = [150.0] * 4
    fc = FlightController(cfg, mixer, 0.055)
    fs = cfg.pid_rate
    out_sig = []
    for k in range(8000):
        fc.update((0.0, 0.0, 0.0, 0.3), [20.0 * math.sin(2 * math.pi * 150.0 * k / fs), 0.0, 0.0], rotor_hz)
        out_sig.append(fc.gyro_filtered[0])
    assert np.std(out_sig[4000:]) < 0.01 * 20.0 / math.sqrt(2)


def test_mixer_signs_and_airmode(fc_cfg):
    positions = [(-1, 1, 0), (1, 1, 0), (-1, -1, 0), (1, -1, 0)]  # Betaflight order: RR, FR, RL, FL
    mixer = quad_mixer(positions, ["cw", "ccw", "ccw", "cw"])
    assert [row[0] for row in mixer] == [-1, -1, 1, 1]  # roll right: left motors up
    assert [row[1] for row in mixer] == [-1, 1, -1, 1]  # pitch up: front motors up
    assert [row[2] for row in mixer] == [-1, 1, 1, -1]  # yaw right: CCW motors up
    fc = FlightController(fc_cfg, mixer, 0.055)
    out = None
    for _ in range(400):  # full right roll at zero throttle, quad not rotating yet
        out = fc.update((1.0, 0.0, 0.0, 0.0), [0.0, 0.0, 0.0], [200.0] * 4)
    assert all(0.055 <= m <= 1.0 for m in out)
    assert out[2] > out[0] and out[3] > out[1]  # airmode keeps roll authority at zero throttle
    assert max(out) - min(out) == pytest.approx(1.0 - 0.055)  # the full motor range is used


def test_fc_config_round_trip(fc_cfg, tmp_path):
    path = tmp_path / "fc.toml"
    path.write_text(dump_fc_config(fc_cfg, "copy", "copy"), encoding="utf-8")
    again = load_fc_config(path)
    assert again.pids == fc_cfg.pids and again.rates == fc_cfg.rates
    assert again.gyro_lowpass == fc_cfg.gyro_lowpass and again.rpm_harmonics == fc_cfg.rpm_harmonics


# ---------------------------------------------------------------- simulation


def test_closed_loop_hover_holds_station(reference_build, fc_cfg, aircraft):
    log = simulate(reference_build, fc_cfg, MANEUVERS["hover"], SimSettings(log_rate=500), duration=1.0)
    assert np.ptp(log["alt"]) < 0.02
    assert np.max(np.abs(log["att_pitch"])) < 0.5
    assert np.mean(log["current"]) == pytest.approx(hover_point(aircraft).i_bus, rel=0.02)


def test_simulation_is_deterministic(reference_build, fc_cfg):
    a = simulate(reference_build, fc_cfg, MANEUVERS["hover"], SimSettings(log_rate=500, seed=3), duration=0.3)
    b = simulate(reference_build, fc_cfg, MANEUVERS["hover"], SimSettings(log_rate=500, seed=3), duration=0.3)
    c = simulate(reference_build, fc_cfg, MANEUVERS["hover"], SimSettings(log_rate=500, seed=4), duration=0.3)
    assert a.columns["gyro_raw_roll"] == b.columns["gyro_raw_roll"]
    assert a.columns["gyro_raw_roll"] != c.columns["gyro_raw_roll"]


def test_flip_recovers_level(reference_build, fc_cfg):
    log = simulate(reference_build, fc_cfg, MANEUVERS["flip"], SimSettings(log_rate=250))
    assert np.max(np.abs(log["att_roll"])) > 170.0  # went inverted
    assert abs(log["att_roll"][-1]) < 5.0 and abs(log["att_pitch"][-1]) < 5.0
    assert not log.meta["crashed"]


def test_log_csv_round_trip(reference_build, fc_cfg, tmp_path):
    log = simulate(reference_build, fc_cfg, MANEUVERS["hover"], SimSettings(log_rate=500), duration=0.1)
    log.write_csv(tmp_path / "log.csv")
    again = FlightLog.read_csv(tmp_path / "log.csv")
    assert again.rate == 500.0 and again.meta["fc"] == fc_cfg.id
    assert np.allclose(again["vbat"], log["vbat"], rtol=1e-5)
    assert again.si("gyro_raw_roll")[0] == pytest.approx(math.radians(log["gyro_raw_roll"][0]), rel=1e-5)


# ------------------------------------------------------------------ analysis


def _second_order(fs, wn=60.0, zeta=0.5, delay=0.008):
    b, a, _ = cont2discrete(([wn**2], [1, 2 * zeta * wn, wn**2]), 1 / fs, method="bilinear")
    return b.ravel(), a, int(delay * fs)


def test_deconvolution_recovers_known_step_response():
    fs = 2000.0
    b, a, delay = _second_order(fs)
    rng = np.random.default_rng(0)
    n = int(30 * fs)
    sp = np.zeros(n)
    k = 0
    while k < n:
        length = int(rng.uniform(0.1, 0.6) * fs)
        sp[k : k + length] = rng.choice([0, 1]) * rng.uniform(-500, 500)
        k += length
    sp = lfilter([1 - np.exp(-2 * np.pi * 30 / fs)], [1, -np.exp(-2 * np.pi * 30 / fs)], sp)
    gyro = lfilter(b, a, np.concatenate([np.zeros(delay), sp])[:n]) + rng.normal(0, 2.0, n)
    sr = fa.step_response(sp, gyro, fs)
    truth = lfilter(b, a, np.concatenate([np.zeros(delay), np.ones(len(sr.t))])[: len(sr.t)])
    est, true = fa.step_metrics(sr.t, sr.mean), fa.step_metrics(sr.t, truth)
    assert est["overshoot"] == pytest.approx(true["overshoot"], abs=0.02)
    assert est["rise_time"] == pytest.approx(true["rise_time"], abs=0.003)
    assert est["peak_time"] == pytest.approx(true["peak_time"], abs=0.005)


def test_step_metrics_on_analytic_response():
    fs = 4000.0
    b, a, _ = _second_order(fs, delay=0.0)
    t = np.arange(int(0.6 * fs)) / fs
    y = lfilter(b, a, np.ones(len(t)))
    m = fa.step_metrics(t, y)
    assert m["overshoot"] == pytest.approx(math.exp(-0.5 * math.pi / math.sqrt(1 - 0.25)), abs=0.005)


def test_latency_band_rms_and_throttle_map():
    fs = 2000.0
    rng = np.random.default_rng(1)
    x = rng.normal(size=20000)
    assert fa.latency(x, np.roll(x, 24), fs) == pytest.approx(0.012)
    t = np.arange(20000) / fs
    assert fa.band_rms(3.0 * np.sin(2 * np.pi * 300 * t), fs, 100, 1000) == pytest.approx(3.0 / math.sqrt(2), rel=0.02)
    throttle = np.linspace(10, 90, len(t))
    freq = 2.0 * throttle + 100.0  # a noise line that rises with throttle
    signal = np.sin(2 * np.pi * np.cumsum(freq) / fs)
    tm = fa.throttle_map(signal, throttle, fs)
    rows = np.nonzero(tm.frames)[0]
    peaks = tm.freqs[np.nanargmax(tm.power_db[rows], axis=1)]
    assert np.all(np.diff(peaks) >= -tm.freqs[1])  # the peak moves up with throttle


def _candidate(label, pd, d, overshoot, noise, tracking, crashed=False):
    return Candidate(label, pd, d, None, {"crashed": crashed, "overshoot_max_rp": overshoot, "motor_noise": noise, "tracking_rp": tracking})


def test_recommendation_rule():
    cands = [
        _candidate("base", 1.0, 1.0, 0.12, 0.04, 50.0),
        _candidate("fast but overshoots", 1.3, 0.8, 0.30, 0.04, 45.0),
        _candidate("fast but noisy", 1.3, 1.25, 0.10, 0.07, 46.0),
        _candidate("good", 1.15, 1.25, 0.10, 0.05, 48.0),
        _candidate("crashed", 0.7, 0.8, 0.05, 0.01, 40.0, crashed=True),
    ]
    rec, rule = select(cands)
    assert rec.label == "good"
    assert [c.feasible for c in cands] == [True, False, False, True, False]
    assert "15%" in rule


def test_robust_alternative_offers_margin_only_within_tracking_tie():
    cands = [
        _candidate("edge of limit", 1.3, 1.0, 0.149, 0.060, 8.60),
        _candidate("margin, similar tracking", 1.0, 1.25, 0.095, 0.055, 8.90),
        _candidate("more margin, much worse tracking", 0.7, 1.25, 0.05, 0.041, 9.50),
        _candidate("infeasible", 1.3, 1.25, 0.09, 0.193, 8.50),
    ]
    for c in cands:
        c.feasible = c.label != "infeasible"
    assert robust_alternative(cands, cands[0]).label == "margin, similar tracking"
    assert robust_alternative(cands[:1], cands[0]) is None


def test_ff_dominated_names_axes_whose_overshoot_feedforward_causes():
    def axes(roll, pitch, yaw):
        return {"axes": {a: {"overshoot": o, "rise_time": 0.01} for a, o in zip(("roll", "pitch", "yaw"), (roll, pitch, yaw))}}

    base = Candidate("PD×1 D×1", 1.0, 1.0, None, axes(0.20, 0.14, 0.33))
    study = TuningStudy(None, [], [base], None, "", 1, ff_off=axes(0.15, 0.10, 0.02))
    assert [a[0] for a in ff_dominated(study)] == ["yaw"]  # roll exceeds the limit but F is not the main cause
    assert ff_dominated(TuningStudy(None, [], [base], None, "", 1)) == []


def test_edge_steps_read_known_response_exactly():
    """Scripted steps with known timing: overshoot is read directly per edge."""
    fs = 2000.0
    b, a, _ = _second_order(fs, delay=0.004)
    t = np.arange(int(6 * fs)) / fs
    sp = np.zeros_like(t)
    edges = []
    for k, value in enumerate([200.0, -200.0, 0.0, 300.0, -300.0, 0.0]):
        t0 = 0.5 + 0.8 * k
        sp[t >= t0] = value
        edges.append((t0, t0 + 0.8))
    gyro = lfilter(b, a, np.concatenate([np.zeros(8), sp])[: len(sp)])
    es = fa.edge_steps(t, sp, gyro, edges)
    expected = math.exp(-0.5 * math.pi / math.sqrt(1 - 0.25))
    assert es.response.segments == 6
    assert np.allclose(es.overshoot, expected, atol=0.005)  # independent of step size and direction
    assert np.all(np.isfinite(es.settling_time))


def test_step_test_blocks_cover_each_axis():
    from fpvsim.pilot import step_test
    from fpvsim.tuning import sweep_maneuver

    segments, end = step_test(amplitudes=(0.3,), cycles=1)
    assert [s.tag for s in segments] == ["step:roll"] * 3 + ["step:pitch"] * 3 + ["step:yaw"] * 3
    assert [s.sticks for s in segments[:3]] == [{"roll": 0.3}, {"roll": -0.3}, {"roll": 0.0}]
    man, window = sweep_maneuver()
    assert len(man.step_edges("roll")) == 12 and window[0] > man.step_edges("yaw")[-1][1]
