"""Frozen copy of the hard-coded unit tables (layers A, B, C, D of [J] §1.1).

Moved verbatim from graph-rag-normalize-unite-service/infrastructure/unit_normalization_service.py
(plan Task 2). Roles: seed source (seed.py), boot-time fallback floor (bundle.legacy_bundle),
and parity oracle input. Do NOT edit to add a unit: units are managed by unit-registry-service.
LABEL_TO_DIMENSION (layer C) is still read by the engine directly until P2.
"""

LEGACY_DEFINES: tuple[str, ...] = (
    'unité = count = unite = Nb = nb',
    'pieds = foot = pied',
    'decibel = [sound] = dB = dBA',
    'cheval = 735.49875 * watt = ch',
    'chevaux = count',
    'segments = count = segment',
    'mètres = meter',
    'Litres = liter',
    'Volts = volt',
    'sélections = count = selections = selection = sélection',
    'galettes = count = galette = Galettes = Galette',
    'tasses_par_jour = count',
    'Watts = watt',
    'unités = count',
    'billets = count = billet',
    'pièces = count = pièce',
    'personnes = count = personne',
    'degré = degree = degre = degrés = degres',
    'Tonnes = tonne',
    'démarrages = count = démarrage',
    'lignes = count = ligne',
    'tours_par_minute_fr = revolutions_per_minute',
    'pouces = 0.0254 * meter = pouce = inch_fr',
    'semelles_unit = count = semelles = semelle',
    'plots_unit = count = plots = plot',
    'bacs_unit = count = bacs = bac',
    'vehicules_unit = count = vehicules = vehicule',
    'recettes_par_programme = count',
    'coups_par_minute = count / minute',
    'coupes_par_minute = count / minute',
    'tonne = 1000 * kilogram = t',
    'mm = millimeter',
    'cm = centimeter',
    'm = meter',
    'kg = kilogram',
    'KW = 1000 * watt',
    'kw = 1000 * watt',
    'cheval_vapeur = 735.49875 * watt = cv',
    'CV = cheval_vapeur',
    'V = volt',
    'A = ampere',
    'sec = second',
    'ph = hertz',
    'tours_par_minute = revolutions_per_minute = rpm = tr/min = trs/min',
    'Pa = pascal',
    'kPa = 1000 * pascal',
    'L_par_min = liter / minute = l/min',
    'L_par_h = liter / hour = l/h',
    'm3_par_h = meter**3 / hour',
    'm3 = meter**3',
    'litres = liter',
    'L = liter',
    'N = newton',
    'kgf = 9.80665 * newton',
    'Nm = newton * meter',
    'kg_par_m2 = kilogram / meter ** 2 = kg/m² = kg/m2',
)

LEGACY_UNIT_TO_DIMENSION: dict[str, str] = {
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
    # --- FIX 15: 13th DLQ batch — bare 'cycles' (count, e.g. MCBF reliability) ---
    # Distinct from 'cycles/jour' which is a frequency (count per time).
    "cycles": "count",
    "cycle": "count",
    # --- FIX 16: 14th DLQ batch ---
    # Dynamic viscosity (Pa·s, mPa·s) — middle dot already normalized to '.'
    "mpa.s": "viscosity",
    "pa.s": "viscosity",
    # 'cycles par jour' (French long form of cycles/jour)
    "cycles par jour": "[frequency]",
    # --- FIX 17: French time plural (seconde/secondes) ---
    # Mirrors FIX 8 'minutes' and FIX 10 'heures' patterns.
    "secondes": "time",
    "seconde": "time",
    # --- FIX 18: 15th DLQ batch ---
    # 'mesures' = number of readings stored in device memory
    # ("Capacité de mémoire interne : 6000 mesures") — a count, NOT
    # an information size: the value counts records, not bytes.
    # Required here (not just as a pint define) because the bare
    # 'capacité' label fallback resolves to mass before 'mémoire'
    # can match, so unit lookup must win first.
    "mesures": "count",
    "mesure": "count",
}

LABEL_TO_DIMENSION: dict[str, str] = {
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

CANONICAL_UNITS: dict[str, str] = {
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
    # Dynamic viscosity — pascal-second
    "viscosity": "pascal * second",
}
