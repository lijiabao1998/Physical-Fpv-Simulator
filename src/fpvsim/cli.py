"""Command-line entry point: ``fpvsim <command> ...``."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import units
from .atmosphere import Environment
from .design import DesignError, check_sources, load_build
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

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (DesignError, ParamError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
