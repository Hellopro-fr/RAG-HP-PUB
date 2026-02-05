import json
import random

zones = [
    {
        "id_zone": "1",
        "nom_zone": "Grand Est",
        "list_dept": ["67", "68", "08", "10", "51", "52", "54", "55", "57", "88"],
    },
    {
        "id_zone": "2",
        "nom_zone": "Nouvelle-Aquitaine",
        "list_dept": [
            "24",
            "33",
            "40",
            "47",
            "64",
            "19",
            "23",
            "87",
            "16",
            "17",
            "79",
            "86",
        ],
    },
    {
        "id_zone": "3",
        "nom_zone": "Auvergne-Rhône-Alpes",
        "list_dept": [
            "01",
            "07",
            "26",
            "38",
            "42",
            "69",
            "73",
            "74",
            "03",
            "15",
            "43",
            "63",
        ],
    },
    {
        "id_zone": "4",
        "nom_zone": "Normandie",
        "list_dept": ["14", "50", "61", "27", "76"],
    },
    {
        "id_zone": "5",
        "nom_zone": "Bourgogne-Franche-Comté",
        "list_dept": ["21", "58", "71", "89", "25", "39", "70", "90"],
    },
    {"id_zone": "6", "nom_zone": "Bretagne", "list_dept": ["22", "29", "35", "56"]},
    {
        "id_zone": "7",
        "nom_zone": "Centre-Val de Loire",
        "list_dept": ["18", "28", "36", "37", "41", "45"],
    },
    {"id_zone": "8", "nom_zone": "Corse", "list_dept": ["20"]},
    {
        "id_zone": "9",
        "nom_zone": "Ile-de-France",
        "list_dept": ["75", "77", "78", "91", "92", "93", "94", "95"],
    },
    {
        "id_zone": "10",
        "nom_zone": "Occitanie",
        "list_dept": [
            "11",
            "30",
            "34",
            "48",
            "66",
            "09",
            "12",
            "31",
            "32",
            "46",
            "65",
            "81",
            "82",
        ],
    },
    {
        "id_zone": "11",
        "nom_zone": "Hauts-de-France",
        "list_dept": ["59", "62", "02", "60", "80"],
    },
    {
        "id_zone": "12",
        "nom_zone": "Pays de la Loire",
        "list_dept": ["44", "49", "53", "72", "85"],
    },
    {
        "id_zone": "13",
        "nom_zone": "Provence-Alpes-Côte-d'Azur",
        "list_dept": ["04", "05", "06", "13", "83", "84"],
    },
]

pays_list = [
    {"id_pays": "FR", "nom_pays": "France", "code_iso": "FRA"},
    {"id_pays": "BE", "nom_pays": "Belgique", "code_iso": "BEL"},
    {"id_pays": "DE", "nom_pays": "Allemagne", "code_iso": "DEU"},
    {"id_pays": "ES", "nom_pays": "Espagne", "code_iso": "ESP"},
    {"id_pays": "IT", "nom_pays": "Italie", "code_iso": "ITA"},
    {"id_pays": "CH", "nom_pays": "Suisse", "code_iso": "CHE"},
]

suppliers = []
for i in range(1, 21):
    # Determine if supplier has zones (France regions), pays (Countries), or both
    has_zones = random.choice([True, True, False])  # 66% chance of having zones
    has_pays = random.choice([True, True, False])  # 66% chance of having pays

    # Ensure at least one is present
    if not has_zones and not has_pays:
        has_zones = True

    data = {
        "id_fournisseur": f"F{i:03d}",
        "nom": f"Fournisseur {i}",
        "email": f"contact@fournisseur{i}.com",
    }

    if has_zones:
        # Pick 1 to 3 random zones
        num_zones = random.randint(1, 3)
        data["dept"] = random.sample(zones, num_zones)

    if has_pays:
        # Pick 1 to 2 random pays
        num_pays = random.randint(1, 2)
        selected_pays = random.sample(pays_list, num_pays)
        # Add random 'partiel' boolean
        for p in selected_pays:
            p["partiel"] = random.choice([True, False])
        data["pays"] = selected_pays

    supplier = {
        "data": data,
        "collection": "fournisseurs",
        "database": "neo4j",
        "origin": "generated_script_v2",
    }
    suppliers.append(supplier)

json_output = json.dumps(suppliers, indent=2, ensure_ascii=False)
print(json_output)
