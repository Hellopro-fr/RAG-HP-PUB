"""pint normalization engine, moved from graph-rag-normalize-unite-service (plan Task 2).

The conversion logic was moved as is; the bundle plumbing was added around it: unit
tables now come from a RegistryBundle fetched ONCE per normalize() call (and once per
normalize_range()), so a concurrent swap never mixes two registries inside one call. Layer C
(LABEL_TO_DIMENSION) and the sanitize chain stay in code until P2 (spec §8).
"""
import logging
import re
import unicodedata
from typing import Any, Callable, Dict, Optional

from .bundle import RegistryBundle
from .legacy import LABEL_TO_DIMENSION


class Normalizer:
    LABEL_TO_DIMENSION = LABEL_TO_DIMENSION

    def __init__(self, bundle_provider: Callable[[], RegistryBundle]):
        self._bundle_provider = bundle_provider

    @staticmethod
    def _strip_accents(text: str) -> str:
        # Why: French labels reach this service with inconsistent accents (e.g. 'Durée'
        # vs 'duree'). Comparing accent-stripped forms on both sides removes the need
        # for explicit accented/unaccented duplicate dict keys.
        if not text:
            return text
        return "".join(
            c for c in unicodedata.normalize("NFKD", text)
            if not unicodedata.combining(c)
        )

    def _get_dimension(self, unit: Optional[str], label: str, bundle: RegistryBundle) -> Optional[str]:
        if unit:
            unit_lower = unit.strip().lower()
            # Disambiguate 'nm': nanometer (length) vs Newton-meter (torque).
            # Both collapse to 'nm' after .lower(). Default mapping is torque (legacy);
            # override to length when the label indicates ANY length-like measure.
            if unit_lower == "nm" and label:
                label_norm = self._strip_accents(label.strip().lower())
                length_indicators = (
                    "longueur d'onde",
                    "wavelength",
                    "epaisseur",
                    "diametre",
                    "rayon",
                    "distance",
                    "profondeur",
                    "largeur",
                    "hauteur",
                    "longueur",
                )
                if any(k in label_norm for k in length_indicators):
                    return "length"
            # Disambiguate 't/min': tours/min (rotation, default) vs tonnes/min (mass flow).
            # The letter 't' is overloaded: tour in rotation context, tonne in mass-flow context.
            if unit_lower == "t/min" and label:
                label_norm = self._strip_accents(label.strip().lower())
                mass_flow_indicators = (
                    "debit",
                    "capacite de production",
                    "production",
                    "consommation",
                    "tonnage",
                )
                if any(k in label_norm for k in mass_flow_indicators):
                    return "mass_flow"
            if unit_lower in bundle.unit_to_dimension:
                return bundle.unit_to_dimension[unit_lower]

        if label:
            label_norm = self._strip_accents(label.strip().lower())
            for keyword, dimension in self.LABEL_TO_DIMENSION.items():
                if self._strip_accents(keyword) in label_norm:
                    return dimension

        return None

    def normalize(
        self,
        label: str,
        unit: Optional[str],
        value: Any,
        data_type: Optional[str] = "numeric",
    ) -> Dict[str, Any]:
        """
        Normalizes a single value.
        """
        return self._normalize(self._bundle_provider(), label, unit, value, data_type)

    def _normalize(
        self,
        bundle: RegistryBundle,
        label: str,
        unit: Optional[str],
        value: Any,
        data_type: Optional[str] = "numeric",
    ) -> Dict[str, Any]:
        if data_type not in ["numeric", "numeric_range"]:
            return {}

        if isinstance(value, str):
            try:
                # Handle lists passed as strings if necessary, though proto should handle this
                # --- FIX: Strip '+/-' or '±' tolerance prefix (e.g. '+/- 2') before parsing ---
                value_clean = (
                    value.strip().lstrip("+").replace("/-", "").replace("±", "").strip()
                )
                value = float(value_clean)
            except ValueError:
                return {}

        if not all([label, value is not None]):
            return {}

        # --- FIX: Normalize Unicode compatibility forms (NFKC).
        # Collapses U+00B5 MICRO SIGN and U+03BC GREEK MU into the same codepoint
        # so 'µm' from copy-paste and 'μm' from LLM/OCR extraction both match.
        # Also normalizes other compatibility variants (e.g. fullwidth digits).
        if unit:
            unit = unicodedata.normalize("NFKC", unit)

        # --- FIX: Strip trailing parenthesized symbol annotations from unit names.
        # Producers occasionally emit French long-form names alongside the symbol:
        #   "Décibels (dB)", "Décibels (dBA)", "Kilogrammes (kg)", "Millimètres (mm)"
        # The dimension is carried by the long form; the symbol in parens is redundant.
        # Stripping it lets a single sanitize rule cover every compound form.
        if unit:
            stripped = re.sub(r"\s*\([^)]*\)\s*$", "", unit).strip()
            if stripped:
                unit = stripped

        # --- FIX 16: Normalize middle dot (·, U+00B7) to ASCII period.
        # SI units use middle dot as multiplication separator (Pa·s, m²·K/W, N·m).
        # ASCII period and middle dot are typographically interchangeable in unit
        # notation, so collapse both to '.' for uniform downstream matching.
        if unit:
            unit = unit.replace("·", ".")

        # --- FIX: Save original unit for dimension lookup before sanitization ---
        original_unit = unit

        # --- FIX: Sanitize units that Pint misinterprets ---
        # Specifically, dB(A) is interpreted as decibel * ampere because 'A' = ampere.
        if unit and unit.strip().lower() == "db(a)":
            unit = "dBA"

        # --- FIX: Pint interprets 'tr/min' as 'tr' divided by 'min', but 'tr' is undefined.
        # Replace with 'rpm' which Pint understands natively.
        if unit and unit.strip().lower() in ("tr/min", "trs/min"):
            unit = "rpm"

        # --- FIX: Normalize unicode superscripts ---
        if unit:
            unit = unit.replace("³", "3").replace("²", "2")

        # --- FIX: Pint doesn't understand shorthand like 'm2', 'm3', 'm3/h'.
        # Convert to Pint-compatible exponent syntax.
        if unit:
            unit_stripped = unit.strip().lower()
            if unit_stripped == "m3/h":
                unit = "m**3 / hour"
            elif unit_stripped == "m2":
                unit = "m**2"
            elif unit_stripped == "m3":
                unit = "m**3"
            elif unit_stripped == "kg/m2":
                # Area density: Pint can't parse 'kg/m2' (m2 is not a native Pint exponent)
                unit = "kilogram / meter ** 2"
            elif unit_stripped == "kg/m3":
                # Density: Pint can't parse 'kg/m3' (m3 is not a native Pint exponent)
                unit = "kilogram / meter ** 3"
            # --- FIX: Pint cannot handle French composite rate units directly.
            # Map them to Pint-safe equivalents for mass flow and count rate.
            elif unit_stripped == "g/min":
                unit = "gram / minute"
            elif unit_stripped in ("pièces/seconde", "pieces/seconde"):
                unit = "count / second"
            elif unit_stripped == "billets/seconde":
                unit = "count / second"
            elif unit_stripped in ("tasses/jour",):
                # cups/day is purely a count-formatted unit; pass as count
                unit = "count"
            elif unit_stripped == "watts":
                unit = "watt"
            elif unit_stripped == "kwh/24h":
                # Pint rejects '24h' as a scaling factor; convert to equivalent kWh/day.
                unit = "kilowatt_hour / day"
            elif unit_stripped == "l/cycle":
                # 'cycle' is dimensionless; L/cycle = liters per wash cycle = volume.
                unit = "liter"
            elif unit_stripped in ("tonnes",):
                # Pint only knows lowercase 'tonne'; 'Tonnes' (capital) fails.
                unit = "tonne"
            elif unit_stripped in ("pieds", "pied"):
                # Pint is case-sensitive; 'Pieds' (capital) fails the registry lookup.
                # Force lowercase canonical so the define `pieds = foot = pied` matches.
                unit = "pieds"
            elif unit_stripped == "démarrages/heure":
                # starts per hour = frequency; Pint can't parse 'démarrages'
                unit = "1 / hour"
            elif unit_stripped in ("tours/min", "tour/min"):
                # French singular/plural rotational speed; map to Pint-native rpm
                unit = "rpm"
            elif unit_stripped in ("lignes", "ligne"):
                # 'lignes' (lines) is a count unit
                unit = "count"
            elif unit_stripped in ("pouces", "pouce"):
                # French inch; Pint knows 'inch', use that
                unit = "inch"
            # Note: a previous duplicate `elif unit_stripped in ("kg/m³", "kg/m3")` block
            # was removed — unreachable because `³` is replaced by `3` earlier (line ~510),
            # and `kg/m3` is already caught by the earlier elif above.
            elif unit_stripped == "km/h":
                # Speed: Pint requires explicit slash notation
                unit = "kilometer / hour"
            elif unit_stripped == "lm/w":
                # Luminous efficacy: Pint-safe form
                unit = "lumen / watt"
            elif unit_stripped in ("%", "ra"):
                # Dimensionless/ratio units (humidity %, CRI Ra index) — bypass Pint entirely
                return {
                    "valeur_canonique": float(value),
                    "unite_canonique": "count",
                }
            # --- FIX 8: Sanitize new units found in DLQ batch (normalize-unite retry) ---
            elif unit_stripped == "minutes":
                # Pint accepts singular only
                unit = "minute"
            elif unit_stripped == "μm":  # Greek mu (U+03BC) — NFKC-normalized form
                # micro abbreviation not parsed by Pint; use canonical name
                unit = "micrometer"
            elif unit_stripped == "kg/24h":
                # Daily production capacity: 24h is not a valid Pint scaling token
                unit = "kilogram / day"
            elif unit_stripped == "m2/h":
                # After ² → 2 normalization: surface processing rate
                unit = "meter ** 2 / hour"
            elif unit_stripped == "w/m2.k":
                # Thermal transmittance (U-value) after ² → 2 normalization
                unit = "watt / (meter ** 2 * kelvin)"
            elif unit_stripped == "m2.k/w":
                # Thermal resistance (R-value) after ² → 2 normalization
                unit = "meter ** 2 * kelvin / watt"
            elif unit_stripped == "t/min":
                # 't' is overloaded: tour (rotation, default) vs tonne (mass flow).
                # Mirror the dimension disambiguation in _get_dimension to pick the right
                # Pint expression — otherwise mass-flow values get silently normalized as rpm.
                label_norm = self._strip_accents(label.strip().lower()) if label else ""
                mass_flow_indicators = (
                    "debit",
                    "capacite de production",
                    "production",
                    "consommation",
                    "tonnage",
                )
                if any(k in label_norm for k in mass_flow_indicators):
                    unit = "tonne / minute"
                else:
                    unit = "rpm"
            elif unit_stripped in ("coups/min", "coupes/min"):
                # Pumping/cutting rate — Pint cannot parse 'coups'/'coupes' as count,
                # so represent as inverse minute (frequency) to allow conversion to hertz.
                unit = "1 / minute"
            # --- FIX 10: Sanitize new units from 6th DLQ batch ---
            elif unit_stripped in ("heures", "heure"):
                # French plural; Pint accepts 'hour' canonical only
                unit = "hour"
            elif unit_stripped == "go":
                # French gigaoctet → Pint gigabyte
                unit = "gigabyte"
            elif unit_stripped == "mo":
                unit = "megabyte"
            elif unit_stripped == "ko":
                unit = "kilobyte"
            elif unit_stripped == "to":
                unit = "terabyte"
            elif unit_stripped == "mohs":
                # Mohs hardness scale (0-10) — dimensionless, pass value through
                return {
                    "valeur_canonique": float(value),
                    "unite_canonique": "count",
                }
            elif unit_stripped == "kn/m2":
                # Surface load after ² → 2 normalization (kilonewton per m² = kPa)
                unit = "kilonewton / meter ** 2"
            elif unit_stripped == "cd/m2":
                # Luminance after ² → 2 normalization (candela per m² = nits)
                unit = "candela / meter ** 2"
            # --- FIX 11: Ampere-hour (battery capacity)
            elif unit_stripped in (
                "ah", "a.h",
                "amperes-heures", "ampere-heure",
                "ampères-heures", "ampère-heure",  # accented forms: .lower() preserves accents
            ):
                # Pint case-sensitive ('Ah' is registered, 'ah'/'AH' may fail) — use canonical
                unit = "ampere_hour"
            elif unit_stripped == "mah":
                # milli-ampere-hour
                unit = "milliampere_hour"
            # --- FIX 13: French capitalized SI unit names — Pint case-sensitive, plural-rejecting
            elif unit_stripped in ("kilogrammes", "kilogramme"):
                unit = "kilogram"
            elif unit_stripped in ("grammes", "gramme"):
                unit = "gram"
            elif unit_stripped in ("millimètres", "millimètre"):
                unit = "millimeter"
            elif unit_stripped in ("centimètres", "centimètre"):
                unit = "centimeter"
            elif unit_stripped in ("décibels", "décibel", "decibels", "decibel"):
                # Accept both accented (Décibels) and unaccented (Decibels) forms —
                # .lower() preserves accents, and LLM/OCR extractors sometimes strip them.
                # Compound forms like 'Décibels (dB)' / 'Décibels (dBA)' are already
                # collapsed by the parenthesis-stripping pass above.
                unit = "decibel"
            # --- FIX 14: 12th DLQ batch
            elif unit_stripped in ("cycles/jour", "cycles / jour"):
                # Usage frequency — Pint can't parse 'cycles', so inverse-day for [frequency]
                unit = "1 / day"
            elif unit_stripped in ("kwh/kg", "kwh / kg"):
                # Specific energy — kilowatt-hour per kilogram (with or without spaces)
                unit = "kilowatt_hour / kilogram"
            elif unit_stripped == "kwc":
                # 'crête' (peak) suffix on kW for solar panels — same dimension as kW
                unit = "kilowatt"
            # --- FIX 16: 14th DLQ batch
            elif unit_stripped == "mpa.s":
                # Dynamic viscosity — millipascal-second (middle dot already → '.')
                unit = "millipascal * second"
            elif unit_stripped == "pa.s":
                # Dynamic viscosity — pascal-second
                unit = "pascal * second"
            elif unit_stripped == "cycles par jour":
                # French long-form of cycles/jour — usage frequency
                unit = "1 / day"
            # --- FIX 17: French time plural (seconde/secondes) → Pint canonical 'second'
            elif unit_stripped in ("secondes", "seconde"):
                unit = "second"

        # --- FIX: 'G' (capital) is Pint's gauss. For 'Facteur G' (centrifuge G-factor)
        # it is a dimensionless ratio (multiples of g=9.81 m/s²). Bypass Pint entirely.
        if unit and unit.strip() == "G" and "facteur" in label.strip().lower():
            return {
                "valeur_canonique": float(value),
                "unite_canonique": "count",
            }

        dimension = self._get_dimension(original_unit, label, bundle)

        # --- FIX: For count-based dimensions, bypass Pint conversion and return value directly.
        # Pint cannot meaningfully convert between custom dimensionless units like
        # sélections → count or count / second, so we pass the value through as-is.
        if dimension in ("count", "count_rate") and dimension is not None:
            canonical_unit_str = bundle.canonical_units.get(dimension)
            if canonical_unit_str:
                return {
                    "valeur_canonique": float(value),
                    "unite_canonique": canonical_unit_str,
                }

        if not dimension:
            return {}

        canonical_unit = bundle.canonical_units.get(dimension)
        if not canonical_unit:
            return {}

        try:
            if unit and unit.lower() != "null":
                quantity = bundle.ureg.Quantity(value, unit)
                canonical_quantity = quantity.to(canonical_unit)
                # Use 6 significant figures rather than 4 decimal places to preserve
                # sub-millimeter values: round(0.000025, 4) = 0.0 destroys µm/nm data,
                # but f"{0.000025:.6g}" = "2.5e-05" keeps the magnitude.
                magnitude = canonical_quantity.magnitude
                return {
                    "valeur_canonique": float(f"{magnitude:.6g}"),
                    "unite_canonique": str(canonical_quantity.units),
                }
            else:
                # Assume value is already in canonical unit or unitless
                return {
                    "valeur_canonique": float(value),
                    "unite_canonique": canonical_unit,
                }

        except Exception as e:
            logging.warning(
                f"Could not normalize unit for label '{label}': value='{value}', unit='{unit}'. Reason: {e}"
            )
            return {}

    def normalize_range(
        self, label: str, unit: Optional[str], min_val: float, max_val: float
    ) -> Dict[str, Any]:
        """Normalizes units for a numeric range."""
        result = {}
        bundle = self._bundle_provider()  # one bundle for the whole range

        # Normalize Min
        if min_val is not None:
            norm_min = self._normalize(bundle, label, unit, min_val, "numeric")
            if norm_min:
                result["valeur_min_canonique"] = norm_min["valeur_canonique"]
                result["unite_canonique"] = norm_min["unite_canonique"]

        # Normalize Max
        if max_val is not None:
            norm_max = self._normalize(bundle, label, unit, max_val, "numeric")
            if norm_max:
                result["valeur_max_canonique"] = norm_max["valeur_canonique"]
                if "unite_canonique" not in result:
                    result["unite_canonique"] = norm_max["unite_canonique"]

        return result
