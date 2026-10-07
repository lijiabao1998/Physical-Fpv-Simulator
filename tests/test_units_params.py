import math

import numpy as np
import pytest

from fpvsim import units
from fpvsim.params import ParamError, ParamSet, Source, parse_param, parse_vector


def test_conversions_round_trip():
    for unit in units._UNITS:
        assert units.from_si(units.to_si(12.5, unit), unit) == pytest.approx(12.5)


def test_known_conversions():
    assert units.to_si(1300, "mAh") == pytest.approx(4680.0)
    assert units.to_si(5.1, "in") == pytest.approx(0.12954)
    assert units.to_si(1, "kgf") == pytest.approx(9.80665)
    assert units.to_si(15, "degC") == pytest.approx(288.15)
    assert units.to_si(1750, "rpm/V") == pytest.approx(1750 * 2 * math.pi / 60)
    assert units.scale("degC") == 1.0  # temperature differences are not offset


def test_unknown_unit_fails_loudly():
    with pytest.raises(units.UnitError):
        units.to_si(1.0, "furlong")


def test_parse_relative_uncertainty_to_si():
    p = parse_param("m", {"value": 32, "unit": "g", "source": "estimate", "u_rel": 0.05})
    assert p.value == pytest.approx(0.032)
    assert p.u == pytest.approx(0.0016)
    assert p.source is Source.ESTIMATE
    assert p.display_value == pytest.approx(32)


def test_parse_absolute_uncertainty_in_file_unit():
    p = parse_param("r", {"value": 80, "unit": "mohm", "source": "measured", "u": 2, "ref": "lab log 1"})
    assert p.u == pytest.approx(0.002)
    assert p.display_u == pytest.approx(2)


@pytest.mark.parametrize(
    "entry",
    [
        32.0,  # bare number: no provenance
        {"value": 32, "unit": "g"},  # missing source
        {"value": 32, "unit": "grams", "source": "estimate"},
        {"value": 32, "unit": "g", "source": "guess"},
        {"value": 32, "unit": "g", "source": "estimate", "u": 1, "u_rel": 0.1},
        {"value": 32, "unit": "g", "source": "estimate", "dist": "cauchy"},
        {"value": 32, "unit": "g", "source": "estimate", "typo": 1},
        {"value": "32", "unit": "g", "source": "estimate"},
    ],
)
def test_parse_rejects_incomplete_or_invalid(entry):
    with pytest.raises(ParamError):
        parse_param("x", entry)


def test_parse_vector():
    v = parse_vector("p", {"value": [1, -2, 3], "unit": "mm"})
    assert np.allclose(v, [0.001, -0.002, 0.003])
    with pytest.raises(ParamError):
        parse_vector("p", {"value": [1, 2], "unit": "mm"})


def test_normal_sampling_statistics():
    p = parse_param("x", {"value": 10, "unit": "1", "source": "estimate", "u": 0.5})
    s = p.sample(np.random.default_rng(0), 200_000)
    assert abs(s.mean() - 10) < 4 * 0.5 / math.sqrt(len(s))
    assert s.std(ddof=1) == pytest.approx(0.5, rel=0.01)


def test_uniform_sampling_uses_standard_uncertainty():
    u = 0.2887
    p = parse_param("f", {"value": 0.5, "unit": "1", "source": "estimate", "u": u, "dist": "uniform"})
    s = p.sample(np.random.default_rng(0), 200_000)
    half = math.sqrt(3) * u
    assert s.min() >= 0.5 - half and s.max() <= 0.5 + half
    assert s.std(ddof=1) == pytest.approx(u, rel=0.01)


def test_positive_parameters_stay_positive():
    p = parse_param("m", {"value": 1.0, "unit": "g", "source": "estimate", "u_rel": 0.6})
    assert (p.sample(np.random.default_rng(0), 50_000) > 0).all()


def test_paramset_sampling_is_reproducible():
    ps = ParamSet()
    ps.add(parse_param("a", {"value": 1, "unit": "1", "source": "estimate", "u": 0.1}))
    ps.add(parse_param("b", {"value": 2, "unit": "1", "source": "nominal"}))
    s1 = ps.sample(np.random.default_rng(42), 10)
    s2 = ps.sample(np.random.default_rng(42), 10)
    assert set(s1) == {"a"}  # only uncertain parameters are sampled
    assert np.array_equal(s1["a"], s2["a"])
    with pytest.raises(ParamError):
        ps.add(parse_param("a", {"value": 1, "unit": "1", "source": "nominal"}))
