"""Run unchanged acquisition entrypoints, logging only recognized public input labels."""

import argparse
import runpy
import sys

from verified_raw_cache import specification


def request_logger(spec, output):
    labels = {entry["source"]: entry["path"] for entry in spec["files"]}

    def audit(event, args):
        if event == "urllib.Request":
            # Never print URL/query/headers/body, including temporary redirect credentials.
            label = labels.get(args[0])
            if label is not None:
                print(f"Pinned source request: {label}", file=output, flush=True)

    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=("chen", "thermal", "stanford"))
    args = parser.parse_args()
    sys.addaudithook(request_logger(specification(), sys.stderr))
    if args.source == "stanford":
        sys.argv = ["scripts/inspect_stanford_pilot.py", "--fetch"]
        runpy.run_path("scripts/inspect_stanford_pilot.py", run_name="__main__")
        return 0
    from physical_fpv.cli import main as original_main

    return original_main(["fetch-data" if args.source == "chen" else "thermal-fetch-data"])


if __name__ == "__main__":
    raise SystemExit(main())
