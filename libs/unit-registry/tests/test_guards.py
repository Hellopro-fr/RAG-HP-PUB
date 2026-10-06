from dataclasses import replace

import pytest

from unit_registry.guards import collateral_changes, find_dependents, validate_unit
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


# --- final review C1/I1/I2: every pint name is guarded, collateral changes, aliases ---

def test_a_pint_alias_cannot_redefine_an_existing_seed_unit(seed):
    outcome = validate_unit(candidate(token="sac", pint_definition="sac = 25 * kilogram = kg"), seed)
    g = by_guard(outcome)
    assert not outcome.ok and (not g["G3"].ok or not g["G6"].ok)
    assert not g["G6"].ok and "'kg'" in g["G6"].message


def test_a_pint_alias_cannot_shadow_a_pint_builtin(seed):
    outcome = validate_unit(candidate(token="sac", pint_definition="sac = 25 * kilogram = g"), seed)
    assert not by_guard(outcome)["G3"].ok


def test_grandfathering_is_by_exact_definition_not_by_name(seed):
    without_kg = [u for u in seed if u.token != "kg"]
    outcome = validate_unit(candidate(token="kg", pint_definition="kg = 25 * kilogram"), without_kg)
    assert not by_guard(outcome)["G3"].ok


def test_renaming_a_define_that_others_build_on_is_a_collateral_change(seed):
    cv = next(u for u in seed if u.token == "cheval_vapeur")
    # Without "= cv": since R2, "cv" as a pint alias already fails G6 (spelling of unit CV).
    renamed = replace(cv, dimension="power", pint_definition="cheval_vap2 = 735.49875 * watt",
                      regression_sample=sample(value="2", expected=1470.9975, unit_out="watt",
                                               label="Puissance", unit="cheval_vap2"))
    outcome = validate_unit(renamed, seed)
    g4 = by_guard(outcome)["G4"]
    assert not g4.ok and "would change" in g4.message and "'CV'" in g4.message


def test_a_plain_new_unit_has_no_collateral_change(seed):
    assert by_guard(validate_unit(candidate(), seed))["G4"].ok


def test_an_alias_that_hijacks_a_pint_name_is_rejected(seed):
    bidon = candidate(token="bidon", dimension="volume", pint_definition="bidon = 20 * liter",
                      aliases=("gram",),
                      regression_sample=sample(value="1", expected=20.0, unit_out="liter", label="Volume"))
    assert not validate_unit(bidon, seed).ok


def test_an_alias_pint_does_not_know_is_rejected(seed):
    outcome = validate_unit(candidate(aliases=("sc",)), seed)
    g2 = by_guard(outcome)["G2"]
    assert not g2.ok and "alias 'sc' does not normalize like the token" in g2.message


def test_an_alias_declared_in_the_pint_definition_passes(seed):
    outcome = validate_unit(candidate(aliases=("sc",), pint_definition="sac_ciment = 25 * kilogram = sc"), seed)
    assert outcome.ok, outcome.failures


def test_collateral_changes_reports_a_removed_pint_alias(seed):
    pieds = next(u for u in seed if u.token == "pieds")
    remaining = [u for u in seed if u.id != pieds.id]
    changes = collateral_changes(seed, remaining, {pieds.id})
    assert any(c.startswith("'pied'") for c in changes)
    assert collateral_changes(seed, seed, set()) == []


# --- residual review: multi-line defines (R1), case-only pint aliases (R2) ---

@pytest.mark.parametrize("multi", ["zz_q = 3*gram\nounce = zz_q", "zz_q = 3*gram\nkilogram = zz_q",
                                   "zz_q = 3*gram\r\nounce = zz_q", "zz_q = 3*gram\rounce = zz_q"])
def test_g1_rejects_a_multi_line_definition(seed, multi):
    outcome = validate_unit(candidate(token="zz_q", pint_definition=multi), seed)
    g1 = by_guard(outcome)["G1"]
    assert not outcome.ok and not g1.ok and "one definition" in g1.message


@pytest.mark.parametrize("alias", ["KG", "Kg", "Kilogram"])
def test_a_case_variant_pint_alias_of_an_existing_spelling_is_rejected(seed, alias):
    outcome = validate_unit(candidate(pint_definition=f"sac_ciment = 25 * kilogram = {alias}"), seed)
    assert not outcome.ok


def test_g6_compares_pint_names_case_insensitively(seed):
    g6 = by_guard(validate_unit(candidate(pint_definition="sac_ciment = 25 * kilogram = KG"), seed))["G6"]
    assert not g6.ok and "'KG'" in g6.message


def test_collateral_replays_the_candidates_new_pint_names(seed):
    # Bypass G6 to prove the replay alone catches a new pint name that alters an existing spelling.
    sac = candidate(pint_definition="sac_ciment = 25 * kilogram = KG")
    changes = collateral_changes(seed, [*seed, sac], {sac.id}, extra_keys=["KG"])
    assert any(c.startswith("'KG'") for c in changes)


def test_seed_definitions_still_pass_g6(seed):
    for token in ("CV", "cheval_vapeur", "kg", "kg_par_m2", "pieds", "unité"):
        unit = next(u for u in seed if u.token == token)
        assert by_guard(validate_unit(unit, seed))["G6"].ok, token


def test_renaming_with_the_old_pint_alias_is_caught_by_g6(seed):
    cv = next(u for u in seed if u.token == "cheval_vapeur")
    renamed = replace(cv, dimension="power", pint_definition="cheval_vap2 = 735.49875 * watt = cv")
    assert "'cv'" in by_guard(validate_unit(renamed, seed))["G6"].message
