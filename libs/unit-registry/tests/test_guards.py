import pytest

from unit_registry.guards import find_dependents, validate_unit
from unit_registry.seed import build_seed_units
from unit_registry.types import RegressionSample, Unit, UnitSource


@pytest.fixture(scope="module")
def seed():
    return build_seed_units()


def sample(value="2", expected=50.0, unit_out="kilogram", label="Poids", **kw):
    return RegressionSample(label=label, value=value, expected_canonical_value=expected,
                            expected_canonical_unit=unit_out, **kw)


def candidate(**overrides) -> Unit:
    base = dict(id="new", token="sac_ciment", dimension="mass",
                pint_definition="sac_ciment = 25 * kilogram", source=UnitSource.MANUAL,
                sort_order=10_000, regression_sample=sample())
    base.update(overrides)
    return Unit(**base)


def by_guard(outcome):
    return {g.guard: g for g in outcome.guards}


def test_valid_unit_passes_all_guards(seed):
    outcome = validate_unit(candidate(), seed)
    assert outcome.ok, outcome.failures
    assert [g.guard for g in outcome.guards] == ["G1", "G2", "G3", "G4", "G5", "G6"]
    assert by_guard(outcome)["G5"].skipped
    assert outcome.dry_run.ok and outcome.dry_run.canonical_value == 50.0


def test_g1_catches_the_lazy_define_trap(seed):
    outcome = validate_unit(candidate(token="baz_x", pint_definition="baz_x = 3 * nonexistent_y"), seed)
    assert not by_guard(outcome)["G1"].ok
    assert "UndefinedUnitError" in by_guard(outcome)["G1"].message


@pytest.mark.parametrize("bad", ["z_u = (3", "q_only", "= meter"])
def test_g1_rejects_malformed_defines(seed, bad):
    outcome = validate_unit(candidate(token="weird", pint_definition=bad), seed)
    assert not by_guard(outcome)["G1"].ok


def test_g2_catches_a_dimensionless_define_that_g1_accepts(seed):
    # pint 0.24.4 evaluates "foo_u = = bar" to 1 dimensionless: only G2 stops it.
    outcome = validate_unit(candidate(token="foo_u", pint_definition="foo_u = = bar"), seed)
    assert by_guard(outcome)["G1"].ok and not by_guard(outcome)["G2"].ok


def test_g1_rejects_circular_definitions(seed):
    others = [*seed, Unit(id="c1", token="cyc_b", dimension=None,
                          pint_definition="cyc_b = 3 * cyc_a", sort_order=9_999)]
    outcome = validate_unit(candidate(token="cyc_a", pint_definition="cyc_a = 2 * cyc_b"), others)
    assert not by_guard(outcome)["G1"].ok


def test_g2_rejects_an_unknown_dimension(seed):
    outcome = validate_unit(candidate(dimension="weight"), seed)
    assert "unknown dimension 'weight'" in by_guard(outcome)["G2"].message


def test_g2_rejects_a_define_in_the_wrong_dimension(seed):
    outcome = validate_unit(candidate(dimension="volume"), seed)
    assert not by_guard(outcome)["G2"].ok


def test_g3_rejects_a_prefix_collision(seed):
    outcome = validate_unit(candidate(token="nmx", pint_definition="nm = newton * meter",
                                      dimension="torque"), seed)
    assert not by_guard(outcome)["G3"].ok


def test_g3_grandfathers_seed_names(seed):
    kg = next(u for u in seed if u.token == "kg")
    outcome = validate_unit(kg, seed)
    assert by_guard(outcome)["G3"].ok


def test_g4_requires_a_sample(seed):
    outcome = validate_unit(candidate(regression_sample=None), seed)
    assert "regression sample is required" in by_guard(outcome)["G4"].message


def test_g4_rejects_a_wrong_expected_value(seed):
    outcome = validate_unit(candidate(regression_sample=sample(expected=40.0)), seed)
    g4 = by_guard(outcome)["G4"]
    assert not g4.ok and "expected 40.0" in g4.message
    assert outcome.dry_run.canonical_value == 50.0


def test_g4_compares_at_six_significant_digits(seed):
    outcome = validate_unit(candidate(regression_sample=sample(expected=50.0000001)), seed)
    assert by_guard(outcome)["G4"].ok


def test_g4_runs_range_samples(seed):
    s = sample(value="1", value_max="3", expected=25.0, expected_canonical_max=75.0,
               data_type="numeric_range")
    assert validate_unit(candidate(regression_sample=s), seed).ok


def test_g6_rejects_an_existing_token(seed):
    outcome = validate_unit(candidate(token="kg", pint_definition=None), seed)
    assert not by_guard(outcome)["G6"].ok


def test_g6_rejects_an_alias_that_is_already_a_lookup_key(seed):
    outcome = validate_unit(candidate(aliases=("KG",)), seed)
    assert "lookup key 'kg'" in by_guard(outcome)["G6"].message


def test_update_of_itself_is_not_a_collision(seed):
    first = candidate(id="same")
    assert validate_unit(candidate(id="same", pint_definition="sac_ciment = 20 * kilogram",
                                   regression_sample=sample(expected=40.0)), [*seed, first]).ok


def test_find_dependents_reports_units_built_on_a_define(seed):
    cheval_vapeur = next(u for u in seed if u.token == "cheval_vapeur")
    tokens = {u.token for u in find_dependents(cheval_vapeur, seed)}
    assert "CV" in tokens


def test_find_dependents_is_empty_for_lookup_only_units(seed):
    galette = next(u for u in seed if u.token == "galette")
    assert find_dependents(galette, seed) == []
