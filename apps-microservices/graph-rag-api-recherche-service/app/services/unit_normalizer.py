import logging
import re
from typing import Dict, Optional, Tuple, Any

from pint import UnitRegistry, UndefinedUnitError, DimensionalityError


class UnitNormalizationService:
    """
    A service to handle normalization of physical units to a canonical base unit.
    Implements a hybrid "unit-first, label-fallback" strategy to determine physical dimensions.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UnitNormalizationService, cls).__new__(cls)
            cls._instance.ureg = UnitRegistry()

            # --- FIX 1: Define missing units found in logs ---
            # 'unité' is often used for counts. We define it as dimensionless (count).
            cls._instance.ureg.define("unité = count = unite")
            # 'pieds' is French for feet.
            cls._instance.ureg.define("pieds = foot = pied")

            # --- FIX 2: Define Sound/Acoustic Units ---
            # We define a custom dimension [sound] to handle decibels simply for normalization.
            # REMOVED 'dB(A)' from definition to avoid parser confusion with Amperes.
            cls._instance.ureg.define("decibel = [sound] = dB = dBA")

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
                "unite": "count",
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
                # Power
                "w": "power",
                "kw": "power",
                "cv": "power",
                "hp": "power",
                # Electrical
                "v": "voltage",
                "a": "current",
                # Rotational Speed
                "rpm": "[frequency]",
                "tr/min": "[frequency]",
                "trs/min": "[frequency]",
                # Frequency
                "hz": "frequency",
                # Volume
                "l": "volume",
                "litres": "volume",
                "ml": "volume",
                "m3": "volume",
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
                # Force
                "n": "force",
                "kn": "force",
                "kgf": "force",
                # Torque
                "nm": "torque",
                # Area Density
                "kg/m2": "area_density",
                "kg/m²": "area_density",
            }

            # --- Label-to-Dimension Mapping ---
            cls._instance.LABEL_TO_DIMENSION = {
                "charge au sol": "area_density",
                "charge admissible au sol": "area_density",
                "nombre": "count",
                "quantité": "count",
                # Sound
                "sonore": "sound_level",
                "acoustique": "sound_level",
                "bruit": "sound_level",
                "decibel": "sound_level",
                # Mass
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
                # Speed
                "vitesse": "speed",
                # Power
                "puissance": "power",
                # Electrical
                "tension": "voltage",
                "courant": "current",
                "fusible": "current",
                # Frequency & Rotational Speed
                "fréquence": "frequency",
                "branchement": "voltage",
                "vitesse de rotation": "[frequency]",
                "tours/minute": "[frequency]",
                # Volume
                "volume": "volume",
                "cuve": "volume",
                "contenance": "volume",
                # Temperature
                "température": "temperature",
                # Pressure
                "pression": "pressure",
                # Time
                "temps": "time",
                "duree": "time",
                "delai": "time",
                # Data Size
                "mémoire": "information",
                "stockage": "information",
                # Flow Rate
                "débit": "volume / time",
                # Force
                "force": "force",
                "poussée": "force",
                "traction": "force",
                # Torque
                "couple": "torque",
                # Energy
                "énergie": "energy",
                "consommation": "energy",
                # Area
                "surface": "area",
                "superficie": "area",
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
            }
        return cls._instance

    def _get_dimension(self, unit: Optional[str], label: str) -> Optional[str]:
        if unit:
            unit_lower = unit.lower()
            if unit_lower in self.UNIT_TO_DIMENSION:
                return self.UNIT_TO_DIMENSION[unit_lower]

        label_lower = label.lower()
        for keyword, dimension in self.LABEL_TO_DIMENSION.items():
            if keyword in label_lower:
                return dimension

        return None

    def _sanitize_unit_string(self, text: str) -> str:
        """
        Replaces problematic unit strings with safe aliases before parsing.
        Specifically handles 'dB(A)' which Pint parses as 'dB * Ampere'.
        """
        if not text:
            return text
        # Replace dB(A) or dB (A) with dBA
        text = text.replace("dB(A)", "dBA").replace("dB (A)", "dBA")
        return text

    def normalize(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalizes the unit of a characteristic.
        Returns a dictionary with the canonical value and unit, if conversion is possible.
        """
        label = properties.get("label")
        unit = properties.get("unite")
        value = properties.get("valeur")
        type_donnee = properties.get("type_donnee", None)

        if type_donnee not in ["numeric", "numeric_range"]:
            return {}

        if isinstance(value, (list, tuple)):
            if len(value) > 0:
                logging.warning(
                    f"UnitNormalizationService received a list for value: {value}. Using first element: {value[0]}"
                )
                value = value[0]
            else:
                return {}

        if not all([label, value is not None]):
            return {}

        try:
            value = float(value)
        except (ValueError, TypeError):
            pass

        dimension = self._get_dimension(unit, label)

        if not dimension:
            if unit:
                logging.debug(
                    f"No dimension mapping found for label '{label}' and unit '{unit}'."
                )
            return {}

        canonical_unit = self.CANONICAL_UNITS.get(dimension)
        if not canonical_unit:
            return {}

        try:
            if unit:
                quantity = self.ureg.Quantity(value, unit)
                canonical_quantity = quantity.to(canonical_unit)
                return {
                    "valeur_canonique": round(canonical_quantity.magnitude, 4),
                    "unite_canonique": str(canonical_quantity.units),
                }
            else:
                return {
                    "valeur_canonique": float(value),
                    "unite_canonique": canonical_unit,
                }

        except (
            UndefinedUnitError,
            DimensionalityError,
            AttributeError,
            ValueError,
            TypeError,
            AssertionError,  # Explicitly catch the error seen in logs
            Exception,  # Catch-all to prevent worker crash
        ) as e:
            logging.warning(
                f"Could not normalize unit for label '{label}': value='{value}', unit='{unit}'. Reason: {e}"
            )
            return {}

    def normalize_range(self, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Normalizes units for a numeric range."""
        min_val = properties.get("valeur_min")
        max_val = properties.get("valeur_max")

        result = {}

        # Normalize Min
        if min_val is not None:
            min_props = {**properties, "valeur": min_val}
            normalized_min = self.normalize(min_props)
            if normalized_min:
                result["valeur_min_canonique"] = normalized_min["valeur_canonique"]
                result["unite_canonique"] = normalized_min["unite_canonique"]

        # Normalize Max
        if max_val is not None:
            max_props = {**properties, "valeur": max_val}
            normalized_max = self.normalize(max_props)
            if normalized_max:
                result["valeur_max_canonique"] = normalized_max["valeur_canonique"]
                # If unit wasn't set by min (or if min was None), set it here
                if "unite_canonique" not in result:
                    result["unite_canonique"] = normalized_max["unite_canonique"]

        return result

    def normalize_from_string(
        self, text_value: str, label: str
    ) -> Optional[Tuple[float, str]]:
        """
        Parses a string (e.g., from user query), normalizes it, and returns the canonical value and unit.
        """
        try:
            # --- FIX: Sanitize text value before parsing ---
            text_value = self._sanitize_unit_string(text_value)

            quantity = self.ureg.parse_expression(text_value)

            dimension = self._get_dimension(
                str(quantity.units) if not isinstance(quantity, (int, float)) else None,
                label,
            )
            if not dimension:
                return None

            canonical_unit = self.CANONICAL_UNITS.get(dimension)
            if not canonical_unit:
                return None

            if isinstance(quantity, (int, float)):
                return float(quantity), canonical_unit

            canonical_quantity = quantity.to(canonical_unit)
            return round(canonical_quantity.magnitude, 4), str(canonical_quantity.units)

        except Exception as e:
            logging.warning(
                f"Could not parse or normalize value from string: '{text_value}'. Reason: {e}"
            )
            match = re.match(r"^\d+(\.\d+)?", text_value.strip())
            if match:
                dimension = self._get_dimension(None, label)
                if dimension:
                    return float(match.group(0)), self.CANONICAL_UNITS.get(dimension)
            return None


# Singleton instance
unit_normalizer = UnitNormalizationService()
