import logging
import re
import unicodedata
from typing import Dict, Optional, Tuple, Any, List

from pint import UnitRegistry, UndefinedUnitError, DimensionalityError


class UnitNormalizationService:
    """
    A service to handle normalization of physical units to a canonical base unit.
    Implements a hybrid "unit-first, label-fallback" strategy to determine physical dimensions.
    Ported from 02.txt.
    """

    _instance = None

    # No threading.Lock needed: the module-level `unit_normalizer = UnitNormalizationService()`
    # at the bottom of this file eager-initialises the singleton at import time, before any
    # gRPC worker thread is spawned. Python's import lock guarantees single-threaded execution
    # of the module body, so the `is None` check below never races in practice.
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

            # --- FIX 8: Units from second DLQ batch (normalize-unite retry processor) ---
            cls._instance.ureg.define("semelles_unit = count = semelles = semelle")
            cls._instance.ureg.define("plots_unit = count = plots = plot")
            cls._instance.ureg.define("bacs_unit = count = bacs = bac")
            cls._instance.ureg.define("vehicules_unit = count = vehicules = vehicule")
            cls._instance.ureg.define("recettes_par_programme = count")
            cls._instance.ureg.define("coups_par_minute = count / minute")
            cls._instance.ureg.define("coupes_par_minute = count / minute")

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
                # --- FIX 8 additions: Count units from new DLQ batch ---
                "semelles": "count",
                "semelle": "count",
                "plots": "count",
                "plot": "count",
                "bacs": "count",
                "bac": "count",
                "véhicule(s)": "count",
                "véhicules": "count",
                "véhicule": "count",
                "vehicule(s)": "count",
                "vehicules": "count",
                "vehicule": "count",
                "recettes/programmes": "count",
                # Count rates expressed per minute — treat as frequency so Pint can convert
                # to hertz canonical (same approach as 'démarrages/heure')
                "coups/min": "[frequency]",
                "coupes/min": "[frequency]",
                # Length — thin coatings (µm). 'nm' is intentionally not listed here:
                # it collides with Newton-meter (torque) under case-insensitive lookup.
                # Disambiguation is handled by label context in _get_dimension.
                # Key uses explicit Greek mu (U+03BC) — input NFKC-normalizes U+00B5 → U+03BC.
                "μm": "length",
                "um": "length",
                # Time — explicit plural
                "minutes": "time",
                # Mass flow — production capacity per day
                "kg/24h": "mass_flow",
                # Surface processing rate (cleaning speed per area)
                "m²/h": "surface_rate",
                "m2/h": "surface_rate",
                # Thermal insulation properties
                "w/m².k": "thermal_transmittance",
                "w/m2.k": "thermal_transmittance",
                "m².k/w": "thermal_resistance",
                "m2.k/w": "thermal_resistance",
                # Rotational speed alias (French "tours/min" abbreviated as "t/min" — context: Régime PDF)
                "t/min": "[frequency]",
                # --- FIX 10 additions: 6th DLQ batch ---
                # Time — French plural/singular
                "heures": "time",
                "heure": "time",
                # Mass flow — tonnes per hour
                "t/h": "mass_flow",
                # Mohs hardness scale (0-10, dimensionless)
                "mohs": "dimensionless",
                # French data-size units (octets)
                "go": "information",
                "mo": "information",
                "ko": "information",
                "to": "information",
                # Screen resolution units (pixels are a count)
                "px": "count",
                "pixel": "count",
                "pixels": "count",
                # Surface pressure / load
                "kn/m²": "pressure",
                "kn/m2": "pressure",
                # Volume — Unicode variant of 'm3' (lookup uses original_unit pre-replace)
                "m³": "volume",
                # Luminance — candela per square meter (nits)
                "cd/m²": "luminance",
                "cd/m2": "luminance",
                # --- FIX 11: 7th DLQ batch ---
                # Ampere-hour = battery capacity (electric charge), 1 Ah = 3600 C
                # Include both accented and unaccented French forms — .lower() preserves accents
                "ah": "electric_charge",
                "a.h": "electric_charge",
                "amperes-heures": "electric_charge",
                "ampere-heure": "electric_charge",
                "ampères-heures": "electric_charge",
                "ampère-heure": "electric_charge",
                "mah": "electric_charge",
                # --- FIX 13: 11th DLQ batch — French capitalized full-name SI units ---
                # Pint only knows canonical English names; French plural forms fail without sanitize.
                "kilogrammes": "mass",
                "kilogramme": "mass",
                "grammes": "mass",
                "gramme": "mass",
                "millimètres": "length",
                "millimètre": "length",
                "centimètres": "length",
                "centimètre": "length",
                # Accented + unaccented variants ('.lower()' preserves é, LLM may strip it).
                # Compound 'Décibels (dB/dBA)' is collapsed to 'Décibels' by the
                # parenthesis-stripping pass in normalize() — no separate key needed.
                "décibels": "sound_level",
                "décibel": "sound_level",
                "decibels": "sound_level",
                "decibel": "sound_level",
                # --- FIX 14: 12th DLQ batch ---
                # Bare m² (area) — m²/h surface-rate was covered earlier but plain m² wasn't
                "m²": "area",
                "m2": "area",
                # Niveau(x) — paren-strip yields 'Niveau', plural-tolerant
                "niveau": "count",
                "niveaux": "count",
                # Usage frequency (cycles per day) — both spaced and unspaced forms
                "cycles/jour": "[frequency]",
                "cycles / jour": "[frequency]",
                # Specific energy (energy per mass) — both spaced and unspaced forms
                "kwh/kg": "specific_energy",
                "kwh / kg": "specific_energy",
                # Solar peak power (kilowatt-crête): same dimension as kW
                "kwc": "power",
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
                # Specific 'capacité …' labels MUST precede the bare 'capacité' fallback below
                "capacité d'accueil": "count",
                "capacité de la vitrine": "count",
                "capacité de production": "mass_flow",
                "capacité de la batterie": "electric_charge",
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
                # Specific 'vitesse …' labels MUST precede the bare 'vitesse' fallback below
                "vitesse de rotation": "[frequency]",
                "vitesse d'acceptation": "count_rate",
                "vitesse de distribution": "count_rate",
                "vitesse de nettoyage": "surface_rate",
                "vitesse": "speed",
                "puissance": "power",
                "tension": "voltage",
                "courant": "current",
                "fusible": "current",
                "branchement": "voltage",
                "fréquence d'utilisation": "[frequency]",
                "fréquence": "frequency",
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
                "débit de vapeur": "mass_flow",
                "consommation d'eau": "volume",
                "consommation électrique": "power",
                # Specific 'batterie' qualifier — autonomie is duration, not energy
                "autonomie de la batterie": "time",
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
                # --- FIX 8 additions: Labels for nodes with unit=null or new physical dimensions ---
                # Count labels (unit=null cases — value implicit count)
                "lignes hydrauliques": "count",
                "niveaux desservis": "count",
                "cylindres": "count",
                "plateaux": "count",
                "configuration de la base": "count",
                "catégorie cabine": "count",
                "mémorisation de programmes": "count",
                # Rate / cadence — pumping or cutting cycles per minute (frequency)
                "cadence": "[frequency]",
                # Thermal insulation properties
                "coefficient de transmission thermique": "thermal_transmittance",
                "résistance thermique": "thermal_resistance",
                # --- FIX 10 additions: labels for 6th DLQ batch ---
                "résolution de l'écran": "count",
                "luminosité de l'écran": "luminance",
                "dureté": "dimensionless",
                "mémoire vive": "information",
                # --- FIX 12: 9th DLQ batch — ratio labels
                # Specific physical ratios MUST precede the bare "ratio" fallback below
                # (substring matching is insertion-order dependent — same trap as 'capacité'/'vitesse').
                "ratio masse/volume": "density",
                "ratio puissance/poids": "power",
                "ratio de compression": "pressure",
                # Pure dimensionless ratios (reduction ratio, conversion ratio, etc.)
                # Use "ratio" dimension (already in CANONICAL_UNITS) rather than "dimensionless"
                # for semantic clarity — both canonicalize to "count" but the dim label differs.
                "ratio de réduction": "ratio",
                "ratio": "ratio",
                # Add specific 'ratio X' variants ABOVE this line — bare "ratio" catches any
                # future 'Ratio …' label, so physical ratios (density/power/pressure/...) must
                # be declared first or they will be silently misclassified to count.
                # Note: 'capacité d'accueil', 'capacité de la vitrine', 'capacité de production'
                # and 'vitesse de nettoyage' are placed ABOVE the bare 'capacité'/'vitesse'
                # fallbacks (substring matching is insertion-order dependent).
                # Note: 'durée' is intentionally omitted — the accent-insensitive lookup in
                # _get_dimension now lets the legacy 'duree' key match accented labels.
                # 'longueur d'onde' is also omitted — already covered by 'longueur'.
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
                # Thermal insulation — coefficient U (transmittance) and R (resistance)
                "thermal_transmittance": "watt / meter ** 2 / kelvin",
                "thermal_resistance": "meter ** 2 * kelvin / watt",
                # Surface processing rate (e.g. cleaning speed in m²/h)
                "surface_rate": "meter ** 2 / hour",
                # Luminance — candela per square meter (nits, used for screen brightness)
                "luminance": "candela / meter ** 2",
                # Electric charge — ampere-hour (battery capacity); 1 Ah = 3600 C
                "electric_charge": "ampere_hour",
                # Specific energy — energy per mass (e.g. drying/heating efficiency)
                "specific_energy": "joule / kilogram",
            }
        return cls._instance

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

    def _get_dimension(self, unit: Optional[str], label: str) -> Optional[str]:
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
            if unit_lower in self.UNIT_TO_DIMENSION:
                return self.UNIT_TO_DIMENSION[unit_lower]

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
