# Physical FPV executable candidate

The newly implemented FPV modules live in `src/physical_fpv/fpv/` and preserve all
prior research source, pins and gates byte for byte. They are an isolated,
conservation-tested engineering candidate, not a hardware-qualified simulator.

[Start here: install, run, covered blocks and limitations](docs/fpv-completion.md).

Quick start after the existing editable installation:

```sh
python -m physical_fpv.fpv.server
```

Optional bounded atomistic reference:

```sh
pip install -r requirements-fpv-optional.txt
python -m physical_fpv.fpv.server --emt-frame
```

The GUI is served only on localhost and needs no third-party account or service.
