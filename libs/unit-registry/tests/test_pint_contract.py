"""Pins the pint 0.24.4 behaviours the registry design relies on (spec §2, [J] D12)."""
import pint
import pytest


def test_pint_is_pinned():
    assert pint.__version__ == "0.24.4"


def test_redefinition_overrides_with_a_warning_not_ignored():
    # Measured on 0.24.4: the LAST define wins and pint only logs a warning (the plan assumed "ignored").
    # Registry-side duplicate-name detection must therefore be explicit (guards), not left to pint.
    ureg = pint.UnitRegistry()
    ureg.define("galette = count")
    ureg.define("galette = 2 * count")
    assert ureg.Quantity(3, "galette").to("count").magnitude == 6


def test_define_is_lazy_so_validation_must_force_evaluation():
    ureg = pint.UnitRegistry()
    ureg.define("baz = 3 * nonexistent")  # accepted
    with pytest.raises(pint.errors.UndefinedUnitError):
        (1 * ureg["baz"]).to_base_units()


def test_prefix_forms_count_as_existing_names():
    assert "nm" in pint.UnitRegistry()  # nano + meter: the G3 trap


def test_there_is_no_public_unit_removal():
    names = dir(pint.UnitRegistry())
    assert "undefine" not in names and "remove_unit" not in names


def test_circular_definitions_raise_instead_of_hanging():
    ureg = pint.UnitRegistry()
    ureg.define("cyc_a = 2 * cyc_b")
    ureg.define("cyc_b = 3 * cyc_a")
    with pytest.raises(RecursionError):
        (1 * ureg["cyc_a"]).to_base_units()
