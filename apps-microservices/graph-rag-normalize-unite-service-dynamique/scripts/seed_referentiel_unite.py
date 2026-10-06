"""
Seed du référentiel d'unités : extrait les données du service HISTORIQUE et
génère deux artefacts (zéro perte des FIX 1→17) :

  1. sql/03_seed_referentiel.sql   — INSERT directs (seed DBA)
  2. tests/fixtures/referentiel_seed.json — payload BO v2 (debug / fixture)

Usage :
  python -m scripts.seed_referentiel_unite

⚠ N'écrit PAS en base et n'appelle PAS le BO : l'écriture passe par l'endpoint
PHP `normalisation/referentiel/save` (Lot 1) ou par le SQL généré, validés par l'équipe.
"""

import json
from pathlib import Path

from scripts.legacy_referentiel import build_legacy_payload

ROOT = Path(__file__).resolve().parents[1]
SQL_OUT = ROOT / "sql" / "03_seed_referentiel.sql"
JSON_OUT = ROOT / "tests" / "fixtures" / "referentiel_seed.json"


def _sql_str(value) -> str:
    """Échappe une valeur pour un littéral SQL (quotes simples)."""
    if value is None:
        return "NULL"
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def _build_sql(payload: dict) -> str:
    lines = [
        "-- Seed généré depuis graph-rag-normalize-unite-service (origine='seed').",
        "-- Régénérer via: python -m scripts.seed_referentiel_unite",
        "",
    ]

    lines.append("-- unite_definition_ia")
    for row in payload["definitions"]:
        lines.append(
            "INSERT INTO unite_definition_ia (definition_udfi, ordre_udfi, origine_udfi) "
            f"VALUES ({_sql_str(row['definition'])}, {int(row['ordre'])}, 'seed');"
        )

    lines.append("")
    lines.append("-- unite_dimension_ia")
    for row in payload["unite_dimension"]:
        lines.append(
            "INSERT INTO unite_dimension_ia (unite_udi, dimension_udi, origine_udi) "
            f"VALUES ({_sql_str(row['unite'])}, {_sql_str(row['dimension'])}, 'seed');"
        )

    lines.append("")
    lines.append("-- label_dimension_ia")
    for row in payload["label_dimension"]:
        lines.append(
            "INSERT INTO label_dimension_ia (label_ldi, dimension_ldi, priorite_ldi, origine_ldi) "
            f"VALUES ({_sql_str(row['label'])}, {_sql_str(row['dimension'])}, {int(row['priorite'])}, 'seed');"
        )

    lines.append("")
    lines.append("-- dimension_canonique_ia")
    for row in payload["dimension_canonique"]:
        lines.append(
            "INSERT INTO dimension_canonique_ia (dimension_dci, unite_canonique_dci, origine_dci) "
            f"VALUES ({_sql_str(row['dimension'])}, {_sql_str(row['unite_canonique'])}, 'seed');"
        )

    lines.append("")
    lines.append("-- unite_preprocessing_ia")
    for row in payload["preprocessing"]:
        lines.append(
            "INSERT INTO unite_preprocessing_ia (type_upi, phase_upi, pattern_upi, remplacement_upi, ordre_upi, origine_upi) "
            f"VALUES ({_sql_str(row['type'])}, {_sql_str(row['phase'])}, {_sql_str(row.get('pattern'))}, "
            f"{_sql_str(row.get('remplacement', ''))}, {int(row['ordre'])}, 'seed');"
        )

    lines.append("")
    lines.append("-- unite_reecriture_ia")
    for row in payload["reecriture"]:
        lines.append(
            "INSERT INTO unite_reecriture_ia (unite_source_uri, kind_uri, value_uri, origine_uri) "
            f"VALUES ({_sql_str(row['unite_source'])}, {_sql_str(row['kind'])}, {_sql_str(row['value'])}, 'seed');"
        )

    return "\n".join(lines) + "\n"


def main():
    payload = build_legacy_payload()

    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    SQL_OUT.write_text(_build_sql(payload), encoding="utf-8")

    print(f"definitions:         {len(payload['definitions'])}")
    print(f"unite_dimension:     {len(payload['unite_dimension'])}")
    print(f"label_dimension:     {len(payload['label_dimension'])}")
    print(f"dimension_canonique: {len(payload['dimension_canonique'])}")
    print(f"-> {SQL_OUT}")
    print(f"-> {JSON_OUT}")


if __name__ == "__main__":
    main()
