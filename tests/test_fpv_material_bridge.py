import numpy as np
import pytest

from physical_fpv.fpv.atomistic import aluminum_eos, frame_mass_kg
from physical_fpv.fpv.material_bridge import (
    ElectrodeMapping,
    chemical_from_tracer,
    solve_material_spm,
)
from physical_fpv.materials import PropertyEstimate, analytic_material_example


def test_geometry_transport_mapping():
    m = ElectrodeMapping(0.3, 2, 0.65, 0.9, "synthetic microgeometry fixture")
    assert m.effective_electrolyte_transport(2) == pytest.approx(0.3)
    assert m.active_volume_fraction() == pytest.approx(0.585)
    with pytest.raises(ValueError):
        ElectrodeMapping(0.5, 2, 0.6, 0.9, "source").validate()
    with pytest.raises(ValueError):
        chemical_from_tracer(1, 1, 1, source="")
    assert (
        chemical_from_tracer(1e-14, 2, 0.5, source="synthetic factors")["chemical_diffusivity_m2_s"]
        == 1e-14
    )


def test_bridge_rejects_unqualified_and_high_current():
    p = PropertyEstimate(**analytic_material_example()["estimate"])
    with pytest.raises(ValueError):
        solve_material_spm(estimates=(("negative", p.phase, p),))
    with pytest.raises(ValueError):
        solve_material_spm(current_a=8)
    with pytest.raises(ValueError):
        solve_material_spm(duration_s=61)


def test_actual_spm_identity_and_numerical_refinement():
    a = solve_material_spm(duration_s=30, mesh_points=40)
    b = solve_material_spm(duration_s=30, mesh_points=80)
    assert a["physical_audit"]["passed"] and b["physical_audit"]["passed"]
    assert np.max(abs(np.array(a["voltage_v"]) - b["voltage_v"])) < 0.001
    assert a["parameters_used"]["Negative particle diffusivity [m2.s-1]"] == 3.3e-14
    assert a["empirical_gate"] == "NOT ESTABLISHED"
    assert a["voltage_v"][-1] < a["voltage_v"][0]


def test_real_emt_supercell_and_sampling():
    pytest.importorskip("ase")
    a = aluminum_eos(points=7, repeats=1)
    b = aluminum_eos(points=11, repeats=2)
    assert a["battery_mapping_allowed"] is False
    assert a["max_force_ev_a"] < 1e-9
    assert abs(a["density_kg_m3"] / b["density_kg_m3"] - 1) < 1e-4
    assert abs(a["bulk_modulus_gpa"] / b["bulk_modulus_gpa"] - 1) < 0.005
    assert 2000 < a["density_kg_m3"] < 3500
    assert 30 < a["bulk_modulus_gpa"] < 150
    assert frame_mass_kg(a, 5e-5) == pytest.approx(a["density_kg_m3"] * 5e-5)
    with pytest.raises(ValueError):
        aluminum_eos(repeats=4)
