"""Smoke tests: every CLI command runs end to end on tiny settings and writes its report.

They check that the command-line paths and the report generators work, not the
numbers (those are verified in the model tests). `fpvsim tune` is left out: even
its smallest study flies 19 tuning flights (several minutes).
"""

import pytest

from fpvsim.cli import main

from conftest import REFERENCE_BUILD, ROOT

FC = str(ROOT / "data" / "fc" / "acro-5in-baseline.toml")
BUILD = str(REFERENCE_BUILD)


def _report(path):
    text = (path / "report.md").read_text(encoding="utf-8")
    assert text.startswith("# ")
    assert "程式版本" in text and "numpy" in text  # provenance row with library versions
    return text


def test_fly_calm_and_windy(tmp_path):
    assert main(["fly", BUILD, "--fc", FC, "--maneuver", "hover", "--duration", "0.5", "--log-rate", "200",
                 "--out", str(tmp_path / "calm")]) == 0
    text = _report(tmp_path / "calm")
    assert "無風" in text and "斜向氣流係數表" in text
    assert main(["fly", BUILD, "--fc", FC, "--maneuver", "hover", "--duration", "0.5", "--log-rate", "200",
                 "--wind", "6", "--wind-from", "270", "--out", str(tmp_path / "wind")]) == 0
    text = _report(tmp_path / "wind")
    assert "Dryden" in text and (tmp_path / "wind" / "wind.png").exists()


def test_tunnel_and_fit_tunnel(tmp_path):
    csv = tmp_path / "balance.csv"
    assert main(["tunnel", BUILD, "--samples", "2", "--synthetic", str(csv), "--out", str(tmp_path / "tunnel")]) == 0
    text = _report(tmp_path / "tunnel")
    for section in ("## 2. 機身阻力極曲線", "## 4. 配平曲線", "## 5. 功率曲線與最佳巡航速度"):
        assert section in text
    assert csv.read_text(encoding="utf-8").startswith("# fpvsim synthetic data")
    assert main(["fit-tunnel", str(csv), "--build", BUILD, "--out", str(tmp_path / "fit")]) == 0
    text = _report(tmp_path / "fit")
    assert 'source = "synthetic"' in text and 'source = "measured"' not in text


def test_battery_sweep(tmp_path):
    assert main(["battery-sweep", BUILD, "--capacities", "1050,1300", "--samples", "5",
                 "--out", str(tmp_path / "sweep")]) == 0
    text = _report(tmp_path / "sweep")
    assert "建議容量" in text and (tmp_path / "sweep" / "sweep.png").exists()


def test_mission(tmp_path, capsys):
    # a 4 % pack: the mission ends at the reserve within one lap
    assert main(["mission", BUILD, "--fc", FC, "--set", "battery.capacity=187", "--max-laps", "1",
                 "--out", str(tmp_path / "mission")]) == 0
    text = _report(tmp_path / "mission")
    assert "結束原因" in text and (tmp_path / "mission" / "mission_log.csv").exists()
    assert "reserve_soc" in capsys.readouterr().out


def test_mission_rejects_bad_override(tmp_path):
    with pytest.raises(SystemExit):
        main(["mission", BUILD, "--fc", FC, "--set", "battery.capacity", "--out", str(tmp_path / "m")])


def test_compare_without_flights(tmp_path):
    variant = str(ROOT / "data" / "builds" / "ref-5in-6s-freestyle-actioncam-a.toml")
    assert main(["compare", BUILD, variant, "--fc", FC, "--samples", "10", "--no-fly", "--no-tune",
                 "--out", str(tmp_path / "compare")]) == 0
    _report(tmp_path / "compare")


def test_validate_prop(tmp_path):
    data = str(ROOT / "data" / "validation" / "props-5in-tri.toml")
    assert main(["validate-prop", BUILD, "--data", data, "--out", str(tmp_path / "pv")]) == 0
    text = _report(tmp_path / "pv")
    assert "零件檔與擬合一致" in text and (tmp_path / "pv" / "validation.png").exists()


def test_code_version_ignores_rewritten_reports(tmp_path):
    """A report run rewrites tracked report files; only edits to the code mark the commit as modified."""
    import shutil
    import subprocess

    from fpvsim.report import git_version

    if shutil.which("git") is None:
        pytest.skip("git not installed")
    run = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)  # noqa: E731
    (tmp_path / "pkg").mkdir()
    (tmp_path / "reports").mkdir()
    (tmp_path / "pkg" / "code.py").write_text("x = 1\n")
    (tmp_path / "reports" / "report.md").write_text("old\n")
    run("init", "-q")
    run("add", ".")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    clean = git_version(tmp_path / "pkg")
    (tmp_path / "reports" / "report.md").write_text("new\n")
    assert git_version(tmp_path / "pkg") == clean and "未提交" not in clean
    (tmp_path / "pkg" / "code.py").write_text("x = 2\n")
    assert "未提交" in git_version(tmp_path / "pkg")
