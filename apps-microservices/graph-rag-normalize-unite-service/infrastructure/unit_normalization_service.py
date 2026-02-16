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
            cls._instance.ureg.define("mètres = meter")
            cls._instance.ureg.define("Litres = liter")
            cls._instance.ureg.define("Volts = volt")

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
                "nb": "count",
                "chevaux": "count",
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
                # Power
                "w": "power",
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
                "m³/h": "volume / time",
                "débit": "volume / time",
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
                "consommation": "energy",
                # Area
                "surface": "area",
                "superficie": "area",
            }

            # --- Label-to-Dimension Mapping ---
            cls._instance.LABEL_TO_DIMENSION = {
                "charge au sol": "area_density",
                "charge admissible au sol": "area_density",
                "nombre": "count",
                "quantité": "count",
                "segment": "count",
                "segments": "count",
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
                "fréquence": "frequency",
                "vitesse de rotation": "[frequency]",
                "tours/minute": "[frequency]",
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
                "débit": "volume / time",
                "force": "force",
                "poussée": "force",
                "traction": "force",
                "couple": "torque",
                "énergie": "energy",
                "consommation": "energy",
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
                value = float(value)
            except ValueError:
                return {}

        if not all([label, value is not None]):
            return {}

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

        dimension = self._get_dimension(unit, label)

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
