"""Command-line entry point: ``fpvsim <command> ...``."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import units
from .atmosphere import Environment
from .design import DesignError, check_sources, load_build
from .flightcontroller import FcConfigError
from .params import ParamError
from .performance import METRICS, evaluate


def _quantity(text: str) -> float:
    """Parse '5.1in', '20degC', '0 m' into SI."""
    match = re.fullmatch(r"\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*([A-Za-z%/*^0-9]+)\s*", text)
    if not match:
        raise argparse.ArgumentTypeError(f"expected a number with a unit, e.g. 5.1in, got {text!r}")
    try:
        return units.to_si(float(match.group(1)), match.group(2))
    except units.UnitError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


def cmd_summary(args) -> int:
    build = load_build(args.build)
    metrics = evaluate(build.realize())
    print(build.name)
    for key, m in METRICS.items():
        value = units.from_si(metrics[key], m.unit)
        print(f"  {m.label:32s} {value:{m.fmt}} {'' if m.unit == '1' else m.unit}")
    return 0


def cmd_check(args) -> int:
    build = load_build(args.build)
    by_source: dict[str, int] = {}
    for p in build.params:
        by_source[p.source.value] = by_source.get(p.source.value, 0) + 1
    print(f"{build.name}: {len(build.params)} parameters, {len(build.params.uncertain())} with uncertainty")
    for source, n in sorted(by_source.items(), key=lambda kv: -kv[1]):
        print(f"  {source:10s} {n}")
    warnings = check_sources(build)
    for w in warnings:
        print(f"warning: {w}")
    return 1 if warnings else 0


def cmd_stand(args) -> int:
    from .stand import COLUMNS, run_stand, write_csv

    build = load_build(args.build)
    ac = build.realize()
    voltage = args.voltage if args.voltage else 4.2 * ac.battery.series
    rows = run_stand(ac, voltage)
    if args.csv:
        write_csv(rows, Path(args.csv))
        print(f"wrote {args.csv}")
    else:
        print("  ".join(name for name, _ in COLUMNS))
        for row in rows:
            print("  ".join(f"{fn(row):10.4g}" for _, fn in COLUMNS))
    return 0


def cmd_report(args) -> int:
    from .report import generate

    build = load_build(args.build)
    out = Path(args.out) if args.out else Path("out") / build.id
    result = generate(build, out, n_samples=args.samples, seed=args.seed)
    print(f"wrote {result.path}")
    return 0


def cmd_fit_prop(args) -> int:
    from .sysid import fit_prop_static, read_csv

    data = read_csv(args.csv)
    missing = {"rpm", "thrust", "torque"} - set(data)
    if missing:
        print(f"error: CSV needs columns {sorted(missing)} (with units, e.g. 'thrust [gf]')", file=sys.stderr)
        return 2
    env = Environment(args.altitude, args.temperature)
    fits = fit_prop_static(data["rpm"], data["thrust"], data["torque"], env.rho, args.diameter)
    print(f"air density {env.rho:.4f} kg/m^3, {fits['ct0'].n} points")
    for key in ("ct0", "cp0"):
        fit = fits[key]
        print(f"  {key} = {fit.values[key]:.5f} +/- {fit.stderr[key]:.5f} (1 sigma, HC3)   R^2 = {fit.r2:.5f}")
    print("\nFor a prop component file (static point only; add more J values from wind-tunnel data):")
    print("[coefficients]")
    print('source = "measured"')
    print(f'ref = "{Path(args.csv).name}"')
    print("J = [0.0]")
    print(f"ct = [{fits['ct0'].values['ct0']:.5f}]")
    print(f"cp = [{fits['cp0'].values['cp0']:.5f}]")
    print(f"ct_u_rel = {fits['ct0'].u_rel('ct0'):.4f}")
    print(f"cp_u_rel = {fits['cp0'].u_rel('cp0'):.4f}")
    return 0


def cmd_hppc(args) -> int:
    from .battery_test import HppcProtocol, run_hppc, write_csv

    build = load_build(args.build)
    battery = build.realize().battery
    protocol = HppcProtocol(pulse_c=args.pulse_c, soc_step=args.soc_step, sample_rate=args.rate)
    data = run_hppc(battery, args.temperature, protocol, seed=args.seed)
    write_csv(data, Path(args.csv))
    print(f"wrote {args.csv}: {len(data['time'])} samples, {data['time'][-1] / 3600:.2f} h at "
          f"{args.temperature - 273.15:.1f} degC")
    return 0


def cmd_fit_battery(args) -> int:
    from .battery_fit import fit_arrhenius, fit_flight, fit_hppc
    from .battery_report import generate
    from .blackbox import FlightLog
    from .sysid import read_csv

    design = None
    battery = None
    if args.build:
        build = load_build(args.build)
        battery = build.realize().battery
        design = {"r0_cell": battery.r0_cell, "r1_cell": battery.r1_cell, "tau1": battery.tau1,
                  "activation_energy": battery.activation_energy, "ocv_soc": battery.ocv_soc,
                  "ocv_cell": battery.ocv_cell, "name": build.name}
    series = args.series or (battery.series if battery else None)
    capacity = args.capacity or (battery.capacity if battery else None)
    if series is None or capacity is None:
        print("error: give --build, or both --series and --capacity", file=sys.stderr)
        return 2
    if not args.csv and not args.log:
        print("error: give HPPC CSV files and/or --log", file=sys.stderr)
        return 2
    fits = []
    for path in args.csv:
        data = read_csv(path)
        missing = {"time", "current", "voltage"} - set(data)
        if missing:
            print(f"error: {path} needs columns {sorted(missing)} (with units, e.g. 'voltage [V]')", file=sys.stderr)
            return 2
        fits.append(fit_hppc(data, series, capacity))
    arrhenius = None
    if len({round(f.temperature, 1) for f in fits}) >= 2:
        arrhenius = fit_arrhenius(fits)
    flight = None
    if args.log:
        if battery is None:
            print("error: --log needs --build (for the OCV curve)", file=sys.stderr)
            return 2
        log = FlightLog.read_csv(Path(args.log))
        flight = fit_flight(log.time, log["vbat"], log["current"], battery.ocv_soc, battery.ocv_cell * battery.series,
                            capacity)
    out = Path(args.out) if args.out else Path("out") / "battery-fit"
    sources = [str(Path(p)) for p in args.csv]
    path = generate(out, sources, fits, arrhenius, flight, args.log, series, design)
    print(f"wrote {path}")
    for src, f in zip(sources, fits):
        print(f"  {src}: r0_cell {1000 * f.r0_cell.value:.3f} +/- {1000 * f.r0_cell.u:.3f} mohm, "
              f"r1_cell {1000 * f.r1_cell.value:.3f} +/- {1000 * f.r1_cell.u:.3f} mohm, tau1 {f.tau1.value:.2f} s")
    if arrhenius:
        print(f"  activation energy {arrhenius.activation_energy.value / 1000:.2f} +/- "
              f"{arrhenius.activation_energy.u / 1000:.2f} kJ/mol")
    return 0


def cmd_maneuvers(args) -> int:
    from .pilot import MANEUVERS

    for m in MANEUVERS.values():
        print(f"  {m.name:15s} {m.duration:5.1f} s  {m.title}")
    return 0


def cmd_fly(args) -> int:
    from .flight_report import generate
    from .flightcontroller import load_fc_config
    from .pilot import MANEUVERS, StickFile
    from .sim import SimSettings, simulate

    build = load_build(args.build)
    cfg = load_fc_config(args.fc)
    if args.sticks:
        source, title = StickFile(args.sticks), f"搖桿輸入檔 {Path(args.sticks).name}"
    else:
        if args.maneuver not in MANEUVERS:
            print(f"error: unknown maneuver {args.maneuver!r}; see `fpvsim maneuvers`", file=sys.stderr)
            return 2
        source = MANEUVERS[args.maneuver]
        title = f"{source.title}（`{source.name}`）"
    settings = SimSettings(log_rate=args.log_rate, seed=args.seed, start_altitude=args.altitude, wind=_wind_settings(args),
                           ground_effect=not args.no_ground_effect)
    log = simulate(build, cfg, source, settings, duration=args.duration)
    out = Path(args.out) if args.out else Path("out") / f"fly-{getattr(source, 'name', 'sticks')}"
    path = generate(build, cfg, log, title, out, float(build.prop_curves.J[-1]))
    print(f"wrote {path}")
    return 0


def _wind_arguments(p) -> None:
    p.add_argument("--wind", type=float, default=0.0, help="mean wind at the reference height, m/s (default calm)")
    p.add_argument("--wind-from", type=float, default=0.0, help="direction the wind comes from, deg clockwise from north")
    p.add_argument("--wind-height", type=float, default=10.0, help="reference height of --wind, m (default 10, weather reports)")
    p.add_argument("--roughness", type=float, default=0.03,
                   help="terrain roughness length z0, m (0.03 open flat, 0.1 farmland, 0.5 suburbs)")
    p.add_argument("--no-turbulence", action="store_true", help="mean wind only, no Dryden turbulence")
    p.add_argument("--no-ground-effect", action="store_true", help="switch off the rotors' ground effect")


def _wind_settings(args):
    import math

    from .wind import WindSettings

    if args.wind < 0.0 or args.wind_height <= args.roughness or args.roughness <= 0.0:
        raise SystemExit("error: need --wind >= 0 and 0 < --roughness < --wind-height")
    return WindSettings(speed=args.wind, direction_from=math.radians(args.wind_from), ref_height=args.wind_height,
                        roughness=args.roughness, turbulence=not args.no_turbulence)


def cmd_tune(args) -> int:
    from .flightcontroller import load_fc_config
    from .tuning import run_study
    from .tuning_report import generate

    build = load_build(args.build)
    cfg = load_fc_config(args.fc)
    study = run_study(args.build, cfg, seed=args.seed, workers=args.workers)
    out = Path(args.out) if args.out else Path("out") / f"tune-{cfg.id}"
    path = generate(build, study, out)
    print(f"wrote {path}")
    if study.recommended:
        print(f"recommended: {study.recommended.label} -> {out / 'recommended_fc.toml'}")
    return 0


def cmd_compare(args) -> int:
    from .compare import compare
    from .compare_report import generate
    from .flightcontroller import load_fc_config

    cfg = load_fc_config(args.fc)
    try:
        cmp = compare([args.base, *args.variants], cfg, samples=args.samples, seed=args.seed,
                      maneuver=None if args.no_fly else args.maneuver, tune=not args.no_tune, workers=args.workers)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else Path("out") / "compare"
    print(f"wrote {generate(cmp, out)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fpvsim", description="Physics-first FPV design and simulation tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("summary", help="nominal design metrics")
    p.add_argument("build")
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("check", help="check parameter provenance")
    p.add_argument("build")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("stand", help="virtual thrust-stand sweep of one motor and prop")
    p.add_argument("build")
    p.add_argument("--voltage", type=_quantity, help="supply voltage, e.g. 25.2V (default: full charge)")
    p.add_argument("--csv", help="write the sweep to this CSV file")
    p.set_defaults(func=cmd_stand)

    p = sub.add_parser("report", help="full design report with uncertainty analysis")
    p.add_argument("build")
    p.add_argument("--out", help="output directory (default: out/<build id>)")
    p.add_argument("--samples", type=int, default=1000, help="Monte Carlo samples (default 1000)")
    p.add_argument("--seed", type=int, default=1, help="random seed (default 1)")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("fit-prop", help="identify static Ct and Cp from thrust-stand CSV")
    p.add_argument("csv")
    p.add_argument("--diameter", type=_quantity, required=True, help="prop diameter, e.g. 5.1in")
    p.add_argument("--temperature", type=_quantity, default=288.15, help="air temperature, e.g. 20degC")
    p.add_argument("--altitude", type=_quantity, default=0.0, help="pressure altitude, e.g. 150m")
    p.set_defaults(func=cmd_fit_prop)

    p = sub.add_parser("hppc", help="virtual battery bench: hybrid pulse test in a thermal chamber")
    p.add_argument("build")
    p.add_argument("--csv", required=True, help="output CSV")
    p.add_argument("--temperature", type=_quantity, default=298.15, help="chamber temperature, e.g. 0degC")
    p.add_argument("--pulse-c", type=float, default=5.0, help="pulse current as C-rate (default 5)")
    p.add_argument("--soc-step", type=float, default=0.1, help="state-of-charge step between pulses (default 0.1)")
    p.add_argument("--rate", type=float, default=10.0, help="logging rate, Hz (default 10)")
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(func=cmd_hppc)

    p = sub.add_parser("fit-battery", help="identify battery R0, R1, tau1, OCV (and Ea) from HPPC CSVs or a flight log")
    p.add_argument("csv", nargs="*", help="HPPC test CSV files (time, current, voltage[, temperature])")
    p.add_argument("--log", help="flight log CSV (time, vbat, current) for an in-flight check")
    p.add_argument("--build", help="build whose battery is tested (series, capacity, OCV curve, design values)")
    p.add_argument("--series", type=int, help="cells in series (default: from --build)")
    p.add_argument("--capacity", type=_quantity, help="capacity for state of charge, e.g. 1300mAh (default: from --build)")
    p.add_argument("--out", help="output directory")
    p.set_defaults(func=cmd_fit_battery)

    p = sub.add_parser("maneuvers", help="list the built-in flight-test maneuvers")
    p.set_defaults(func=cmd_maneuvers)

    p = sub.add_parser("fly", help="stage 6: simulate a test flight and write a flight report")
    p.add_argument("build")
    p.add_argument("--fc", required=True, help="flight-controller config (TOML)")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--maneuver", default="freestyle", help="built-in maneuver (default freestyle)")
    group.add_argument("--sticks", help="CSV of recorded stick inputs instead of a maneuver")
    p.add_argument("--duration", type=float, help="override the flight duration, s")
    p.add_argument("--altitude", type=float, default=20.0, help="start altitude in trimmed hover, m")
    p.add_argument("--log-rate", type=float, default=1000.0, help="log rate, Hz (default 1000)")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--out", help="output directory")
    _wind_arguments(p)
    p.set_defaults(func=cmd_fly)

    p = sub.add_parser("tune", help="stage 5: noise survey, filter check and PID gain sweep")
    p.add_argument("build")
    p.add_argument("--fc", required=True, help="baseline flight-controller config (TOML)")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--workers", type=int, help="parallel flights (default: CPU count)")
    p.add_argument("--out", help="output directory")
    p.set_defaults(func=cmd_tune)

    p = sub.add_parser("compare", help="stage 7: compare design versions (base first)")
    p.add_argument("base")
    p.add_argument("variants", nargs="+")
    p.add_argument("--fc", required=True, help="flight-controller config used for every version")
    p.add_argument("--samples", type=int, default=1000, help="paired Monte Carlo samples per version")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--maneuver", default="freestyle", help="flight-test maneuver flown by every version")
    p.add_argument("--no-fly", action="store_true", help="skip the flight test")
    p.add_argument("--no-tune", action="store_true", help="skip the tuning study per version")
    p.add_argument("--workers", type=int, help="parallel flights in tuning studies")
    p.add_argument("--out", help="output directory")
    p.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (DesignError, ParamError, FcConfigError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
