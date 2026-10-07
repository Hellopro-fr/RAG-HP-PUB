from types import MappingProxyType

import pytest

from unit_registry.bundle import (
    BundleBuildError,
    active_defines,
    build_bundle,
    bundle_from_units,
    explode_lookup_keys,
)
from unit_registry.types import Unit, UnitStatus


def unit(token, dimension=None, define=None, aliases=(), sort_order=0, status=UnitStatus.ACTIVE):
    return Unit(id=f"id-{token}", token=token, dimension=dimension, pint_definition=define,
                aliases=tuple(aliases), sort_order=sort_order, status=status)


def test_explode_maps_token_and_aliases_lowercased():
    index = explode_lookup_keys([unit("Sac", "mass", aliases=["SACS"]), unit("KW")])
    assert index == {"sac": "mass", "sacs": "mass"}


def test_explode_skips_disabled_units():
    assert explode_lookup_keys([unit("sac", "mass", status=UnitStatus.DISABLED)]) == {}


def test_explode_rejects_one_key_with_two_dimensions():
    with pytest.raises(BundleBuildError, match="'sac'"):
        explode_lookup_keys([unit("sac", "mass"), unit("x", "volume", aliases=["sac"])])


def test_active_defines_follow_sort_order():
    units = [unit("b", define="b_u = 2 * meter", sort_order=2), unit("a", define="a_u = meter", sort_order=1)]
    assert active_defines(units) == ["a_u = meter", "b_u = 2 * meter"]


def test_build_bundle_wraps_pint_errors():
    with pytest.raises(BundleBuildError, match="z = \\(3"):
        build_bundle(["z = (3"], {})


def test_bundle_tables_are_read_only():
    bundle = bundle_from_units([unit("sac", "mass", define="sac = 25 * kilogram")])
    assert isinstance(bundle.unit_to_dimension, MappingProxyType)
    with pytest.raises(TypeError):
        bundle.unit_to_dimension["x"] = "mass"  # type: ignore[index]
    assert bundle.ureg.Quantity(2, "sac").to("kilogram").magnitude == 50
