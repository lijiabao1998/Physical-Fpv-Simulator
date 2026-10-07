from pathlib import Path

import pytest

from physical_fpv.data import CHECKSUMS, download_data, load_discharges, verify_raw


@pytest.mark.parametrize("cell", CHECKSUMS)
def test_reject_corrupted_data(cell):
    with pytest.raises(ValueError, match="Checksum mismatch"):
        verify_raw(b"not real measurements", cell)


def test_reject_unknown_cell():
    with pytest.raises(ValueError, match="Only benchmark"):
        verify_raw(b"", "99")


@pytest.mark.data
@pytest.mark.parametrize("cell", CHECKSUMS)
def test_real_protocol_selection(cell):
    path = Path(f"data/raw/LGM50_cell{cell}.csv")
    if not path.exists():
        pytest.skip("Run physical-fpv fetch-data to obtain real public benchmark")
    traces = load_discharges(path, cell)
    assert [t.step for t in traces] == [7, 12, 17, 22]
    assert [t.nominal_current_a for t in traces] == [0.5, 2.5, 5, 7.5]
    assert all(abs(t.measured_capacity_ah - t.reported_capacity_ah) < 1e-4 for t in traces)
    assert all(4.8 < t.measured_capacity_ah < 5.1 for t in traces)
    assert all(t.time_s[0] < 0.05 and t.time_s[-1] > 2000 for t in traces)


def test_existing_corrupt_download_is_never_overwritten(tmp_path):
    path = tmp_path / "LGM50_cell02.csv"
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        download_data(tmp_path)
    assert path.read_bytes() == b"corrupted"
