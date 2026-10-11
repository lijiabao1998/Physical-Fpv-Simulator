"""Run local GUI, deterministic FPV demo, material bridge, and replay verifier."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def write_json(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def replay(payload):
    from physical_fpv.fpv.simulator import Simulator

    clean = dict(payload)
    digest = clean.pop("sha256", None)
    if hashlib.sha256(json.dumps(clean, sort_keys=True).encode()).hexdigest() != digest:
        raise ValueError("Replay checksum mismatch")
    if payload.get("schema") != "fpv-control-replay-v1" or len(payload["inputs"]) > 20000:
        raise ValueError("Unsupported or oversized replay")
    sim = Simulator(
        frame_density_kg_m3=payload["frame_density_kg_m3"], substep_s=payload["substep_s"]
    )
    if sim.replay_bundle()["flight_config"] != payload["flight_config"]:
        # JSON roundtrip changes tuple to list; compare canonical serialized values.
        if json.dumps(sim.replay_bundle()["flight_config"], sort_keys=True) != json.dumps(
            payload["flight_config"], sort_keys=True
        ):
            raise ValueError("Flight configuration changed")
    if sim.replay_bundle()["powertrain_config"] != payload["powertrain_config"]:
        raise ValueError("Powertrain configuration changed")
    for row in payload["inputs"]:
        sim.advance(row["controls"], row["duration_s"])
    if json.dumps(sim.telemetry(), sort_keys=True) != json.dumps(
        payload["final_state"], sort_keys=True
    ):
        raise ValueError("Replay final state differs; no false passing claim")
    return {
        "passed": True,
        "requests": len(payload["inputs"]),
        "time_s": sim.flight.state.time_s,
        "claim": "exact same-environment replay; not validation",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["demo", "replay", "material", "atom"])
    p.add_argument("--out", default="results/fpv-demo.json")
    p.add_argument("--input")
    args = p.parse_args()
    if args.command == "demo":
        from physical_fpv.fpv.simulator import Simulator

        sim = Simulator()
        for index in range(200):
            sim.advance(
                {
                    "armed": True,
                    "throttle": sim.hover_duty + (0.025 if index < 50 else 0),
                    "pitch": 0.06 if 70 <= index < 100 else 0.0,
                    "roll": 0.0,
                    "yaw": 0.0,
                },
                0.05,
            )
        result = sim.replay_bundle()
    elif args.command == "replay":
        if not args.input:
            p.error("--input required for replay")
        result = replay(json.loads(Path(args.input).read_text()))
    elif args.command == "material":
        from physical_fpv.fpv.material_bridge import solve_material_spm

        curves = {n: solve_material_spm(mesh_points=n) for n in [20, 40, 80]}
        errors = {
            f"{a}-{b}": float(
                np.max(abs(np.array(curves[a]["voltage_v"]) - curves[b]["voltage_v"]))
            )
            for a, b in [(20, 40), (40, 80)]
        }
        result = {
            "curves": curves,
            "max_voltage_difference_v": errors,
            "gate_v": 0.001,
            "gates": {k: "PASS" if v < 0.001 else "FAIL" for k, v in errors.items()},
            "empirical_gate": "NOT ESTABLISHED",
        }
    else:
        from physical_fpv.fpv.atomistic import aluminum_eos

        result = aluminum_eos()
    write_json(args.out, result)
    print(args.out)


if __name__ == "__main__":
    main()
