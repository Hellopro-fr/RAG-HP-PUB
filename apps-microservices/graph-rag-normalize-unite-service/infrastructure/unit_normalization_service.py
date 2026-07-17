import logging
import re
from typing import Dict, Optional, Tuple, Any, List

from pint import UnitRegistry, UndefinedUnitError, DimensionalityError


class UnitNormalizationService:
    """
    A service to handle normalization of physical units to a canonical base unit.
    Implements a hybrid "unit-first, label-fallback" strategy to determine physical dimensions.
    Ported from 02.txt.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UnitNormalizationService, cls).__new__(cls)
            cls._instance.ureg = UnitRegistry()

            # --- FIX 1: Define missing units found in logs ---
            cls._instance.ureg.define("unité = count = unite = Nb = nb")
            cls._instance.ureg.define("pieds = foot = pied")

            # --- FIX 2: Define Sound/Acoustic Units ---
            cls._instance.ureg.define("decibel = [sound] = dB = dBA")

            # --- FIX 3: Define units found in DLQ ---
            cls._instance.ureg.define("cheval = 735.49875 * watt = ch")
            cls._instance.ureg.define("chevaux = count")
            cls._instance.ureg.define("segments = count = segment")
            cls._instance.ureg.define("mètres = meter")
            cls._instance.ureg.define("Litres = liter")
            cls._instance.ureg.define("Volts = volt")

            # --- FIX 4: Define units from new DLQ messages ---
            cls._instance.ureg.define(
                "sélections = count = selections = selection = sélection"
            )
            cls._instance.ureg.define("galettes = count = galette = Galettes = Galette")
            cls._instance.ureg.define("tasses_par_jour = count")
            cls._instance.ureg.define("Watts = watt")
            cls._instance.ureg.define("unités = count")

            # --- FIX 5: Define units from live service logs ---
            cls._instance.ureg.define("billets = count = billet")
            cls._instance.ureg.define("pièces = count = pièce")
            cls._instance.ureg.define("personnes = count = personne")

            # --- FIX 6: Define units from batch 3 log analysis ---
            cls._instance.ureg.define("degré = degree = degre = degrés = degres")
            cls._instance.ureg.define("Tonnes = tonne")
            cls._instance.ureg.define("démarrages = count = démarrage")

            # --- FIX 7: Define units from DLQ (graph_rag_normalization_manual_dlq) ---
            cls._instance.ureg.define("lignes = count = ligne")
            cls._instance.ureg.define("tours_par_minute_fr = revolutions_per_minute")
            cls._instance.ureg.define("pouces = 0.0254 * meter = pouce = inch_fr")

            # Base & Common
            cls._instance.ureg.define("tonne = 1000 * kilogram = t")
            cls._instance.ureg.define("mm = millimeter")
            cls._instance.ureg.define("cm = centimeter")
            cls._instance.ureg.define("m = meter")
            cls._instance.ureg.define("kg = kilogram")

            # Power
            cls._instance.ureg.define("KW = 1000 * watt")
            cls._instance.ureg.define("kw = 1000 * watt")
            cls._instance.ureg.define("cheval_vapeur = 735.49875 * watt = cv")
            cls._instance.ureg.define("CV = cheval_vapeur")

            # Electrical
            cls._instance.ureg.define("V = volt")
            cls._instance.ureg.define("A = ampere")

            # Time & Frequency
            cls._instance.ureg.define("sec = second")
            cls._instance.ureg.define("ph = hertz")
            cls._instance.ureg.define(
                "tours_par_minute = revolutions_per_minute = rpm = tr/min = trs/min"
            )

            # Pressure
            cls._instance.ureg.define("Pa = pascal")
            cls._instance.ureg.define("kPa = 1000 * pascal")

            # Flow Rate
            cls._instance.ureg.define("L_par_min = liter / minute = l/min")
            cls._instance.ureg.define("L_par_h = liter / hour = l/h")
            cls._instance.ureg.define("m3_par_h = meter**3 / hour")

            # Volume
            cls._instance.ureg.define("m3 = meter**3")
            cls._instance.ureg.define("litres = liter")
            cls._instance.ureg.define("L = liter")

            # Force & Torque
            cls._instance.ureg.define("N = newton")
            cls._instance.ureg.define("kgf = 9.80665 * newton")
            cls._instance.ureg.define("Nm = newton * meter")

            # Area Density / Surface Load
            cls._instance.ureg.define(
                "kg_par_m2 = kilogram / meter ** 2 = kg/m² = kg/m2"
            )

            # --- Unit-to-Dimension Mapping ---
            cls._instance.UNIT_TO_DIMENSION = {
                # Count / Dimensionless
                "unité": "count",
                "unités": "count",
                "unite": "count",
                "unites": "count",
                "nb": "count",
                "chevaux": "count",
                "segments": "count",
                "segment": "count",
                "sélections": "count",
                "selections": "count",
                "sélection": "count",
                "selection": "count",
                "galettes": "count",
                "galette": "count",
                "tasses/jour": "count",
                "tasses_par_jour": "count",
                "billets": "count",
                "billet": "count",
                "pièces": "count",
                "pièce": "count",
                "personnes": "count",
                "personne": "count",
                "lignes": "count",
                "ligne": "count",
                # Sound
                "db": "sound_level",
                "dba": "sound_level",
                "db(a)": "sound_level",
                "decibel": "sound_level",
                # Mass
                "kg": "mass",
                "g": "mass",
                "t": "mass",
                "tonne": "mass",
                "tonnes": "mass",
                # Length
                "mm": "length",
                "cm": "length",
                "m": "length",
                "km": "length",
                "pieds": "length",
                "pied": "length",
                "mètres": "length",
                "pouces": "length",
                "pouce": "length",
                # Density (mass per volume)
                "kg/m³": "density",
                "kg/m3": "density",
                # Power
                "w": "power",
                "watts": "power",
                "kw": "power",
                "cv": "power",
                "ch": "power",
                "hp": "power",
                # Electrical
                "v": "voltage",
                "volts": "voltage",
                "a": "current",
                # Rotational Speed
                "rpm": "[frequency]",
                "tr/min": "[frequency]",
                "trs/min": "[frequency]",
                "tours/min": "[frequency]",
                "tour/min": "[frequency]",
                "démarrages/heure": "[frequency]",
                # Frequency
                "hz": "frequency",
                # Volume
                "l": "volume",
                "litres": "volume",
                "ml": "volume",
                "m3": "volume",
                "m**3": "volume",
                # Temperature
                "°c": "temperature",
                "c": "temperature",
                "k": "temperature",
                # Pressure
                "bar": "pressure",
                "pa": "pressure",
                "kpa": "pressure",
                "psi": "pressure",
                # Time
                "s": "time",
                "sec": "time",
                "min": "time",
                "h": "time",
                # Flow Rate
                "l/min": "volume / time",
                "l/h": "volume / time",
                "m3/h": "volume / time",
                "m³/h": "volume / time",
                "débit": "volume / time",
                # Mass Flow Rate
                "g/min": "mass_flow",
                "kg/min": "mass_flow",
                "kg/h": "mass_flow",
                # Count Rate (items per second)
                "pièces/seconde": "count_rate",
                "pieces/seconde": "count_rate",
                "billets/seconde": "count_rate",
                # Force
                "n": "force",
                "kn": "force",
                "kgf": "force",
                "force": "force",
                "poussée": "force",
                "traction": "force",
                # Torque
                "nm": "torque",
                "couple": "torque",
                # Area Density
                "kg/m2": "area_density",
                "kg/m²": "area_density",
                # Volume labels used as units in some contexts
                "volume": "volume",
                "cuve": "volume",
                "contenance": "volume",
                # Data Size
                "mémoire": "information",
                "stockage": "information",
                # Energy
                "énergie": "energy",
                "kwh": "energy",
                "wh": "energy",
                "kwh/24h": "power",
                "consommation": "energy",
                "surface": "area",
                "superficie": "area",
                # Angle
                "°": "angle",
                "deg": "angle",
                "degré": "angle",
                "degrés": "angle",
                "degre": "angle",
                "degres": "angle",
                # Volume (per wash cycle = liters per cycle, dimensionless denominator)
                "l/cycle": "volume",
                # Signal count (e.g. Raccordement dosage liquide: number of signal ports)
                "signal": "count",
                "signaux": "count",
                # Shelves/trays count
                "plateaux": "count",
                "plateau": "count",
                # Luminous flux (lumen)
                "lm": "luminosity",
                # Luminous efficacy (lumen per watt)
                "lm/w": "luminous_efficacy",
                # Color Rendering Index (CRI/IRC) - dimensionless 0-100 scale
                "ra": "dimensionless",
                # Percentage / ratio (humidity, efficiency, etc.)
                "%": "ratio",
                # Speed (km/h, e.g. wind resistance)
                "km/h": "speed",
            }

            # --- Label-to-Dimension Mapping ---
            cls._instance.LABEL_TO_DIMENSION = {
                "charge au sol": "area_density",
                "charge admissible au sol": "area_density",
                "charge statique": "area_density",
                "classe climatique": "count",
                "régime": "[frequency]",
                "nombre": "count",
                "quantité": "count",
                "segment": "count",
                "segments": "count",
                "sélections": "count",
                "selections": "count",
                "capacité volumique": "volume",
                "capacité volumétrique": "volume",
                "capacité de stockage (masse)": "mass",
                "capacité de stockage": "count",
                "capacité totale de stockage": "count",
                "recycleur": "count",
                "cassette de délestage": "count",
                "bac de trop-plein": "count",
                "passagers": "count",
                "sonore": "sound_level",
                "acoustique": "sound_level",
                "bruit": "sound_level",
                "decibel": "sound_level",
                "poids": "mass",
                "charge": "mass",
                "capacité": "mass",
                "hauteur": "length",
                "largeur": "length",
                "longueur": "length",
                "profondeur": "length",
                "diamètre": "length",
                "dimension": "length",
                "distance": "length",
                "epaisseur": "length",
                "vitesse": "speed",
                "puissance": "power",
                "tension": "voltage",
                "courant": "current",
                "fusible": "current",
                "branchement": "voltage",
                "fréquence d'utilisation": "[frequency]",
                "fréquence": "frequency",
                "vitesse de rotation": "[frequency]",
                "tours/minute": "[frequency]",
                "vitesse d'acceptation": "count_rate",
                "vitesse de distribution": "count_rate",
                "volume": "volume",
                "cuve": "volume",
                "contenance": "volume",
                "température": "temperature",
                "pression": "pressure",
                "temps": "time",
                "duree": "time",
                "delai": "time",
                "mémoire": "information",
                "stockage": "information",
                "débit de vapeur": "mass_flow",
                "consommation d'eau": "volume",
                "consommation électrique": "power",
                "batterie": "energy",
                "consommation": "energy",
                "débit": "volume / time",
                "force": "force",
                "poussée": "force",
                "traction": "force",
                "couple": "torque",
                "énergie": "energy",
                "surface": "area",
                "superficie": "area",
                "angle": "angle",
                "rotation": "angle",
                "production horaire": "volume / time",
                "déverrouillage": "count",
            }

            cls._instance.CANONICAL_UNITS = {
                "count": "count",
                "sound_level": "decibel",
                "mass": "kilogram",
                "length": "meter",
                "speed": "meter / second",
                "power": "watt",
                "voltage": "volt",
                "current": "ampere",
                "frequency": "hertz",
                "[frequency]": "hertz",
                "volume": "liter",
                "temperature": "celsius",
                "pressure": "bar",
                "time": "second",
                "information": "gigabyte",
                "volume / time": "liter / minute",
                "force": "newton",
                "torque": "newton * meter",
                "energy": "joule",
                "area": "meter ** 2",
                "area_density": "kilogram / meter ** 2",
                "density": "kilogram / meter ** 3",
                "angle": "degree",
                "mass_flow": "gram / minute",
                "count_rate": "count / second",
                # Lighting
                "luminosity": "lumen",
                "luminous_efficacy": "lumen / watt",
                # Dimensionless / ratio (humidity %, CRI Ra index, etc.)
                "ratio": "count",
                "dimensionless": "count",
            }
        return cls._instance

    def _get_dimension(self, unit: Optional[str], label: str) -> Optional[str]:
        if unit:
            unit_lower = unit.strip().lower()
            if unit_lower in self.UNIT_TO_DIMENSION:
                return self.UNIT_TO_DIMENSION[unit_lower]

        if label:
            label_lower = label.strip().lower()
            for keyword, dimension in self.LABEL_TO_DIMENSION.items():
                if keyword in label_lower:
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
            elif unit_stripped in ("kg/m³", "kg/m3"):
                # Density unit: kilogram per cubic metre
                unit = "kilogram / meter ** 3"
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

        # --- FIX: 'G' (capital) is Pint's gauss. For 'Facteur G' (centrifuge G-factor)
        # it is a dimensionless ratio (multiples of g=9.81 m/s²). Bypass Pint entirely.
        if unit and unit.strip() == "G" and "facteur" in label.strip().lower():
            return {
                "valeur_canonique": float(value),
                "unite_canonique": "count",
            }

        dimension = self._get_dimension(original_unit, label)

        # --- FIX: For count-based dimensions, bypass Pint conversion and return value directly.
        # Pint cannot meaningfully convert between custom dimensionless units like
        # sélections → count or count / second, so we pass the value through as-is.
        if dimension in ("count", "count_rate") and dimension is not None:
            canonical_unit_str = self.CANONICAL_UNITS.get(dimension)
            if canonical_unit_str:
                return {
                    "valeur_canonique": float(value),
                    "unite_canonique": canonical_unit_str,
                }

        if not dimension:
            return {}

        canonical_unit = self.CANONICAL_UNITS.get(dimension)
        if not canonical_unit:
            return {}

        try:
            if unit and unit.lower() != "null":
                quantity = self.ureg.Quantity(value, unit)
                canonical_quantity = quantity.to(canonical_unit)
                return {
                    "valeur_canonique": round(canonical_quantity.magnitude, 4),
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

        # Normalize Min
        if min_val is not None:
            norm_min = self.normalize(label, unit, min_val, "numeric")
            if norm_min:
                result["valeur_min_canonique"] = norm_min["valeur_canonique"]
                result["unite_canonique"] = norm_min["unite_canonique"]

        # Normalize Max
        if max_val is not None:
            norm_max = self.normalize(label, unit, max_val, "numeric")
            if norm_max:
                result["valeur_max_canonique"] = norm_max["valeur_canonique"]
                if "unite_canonique" not in result:
                    result["unite_canonique"] = norm_max["unite_canonique"]

        return result


# Singleton instance
unit_normalizer = UnitNormalizationService()
