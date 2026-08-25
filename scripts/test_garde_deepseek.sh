#!/usr/bin/env bash
# Lance toutes les suites touchees par la garde tarifaire DeepSeek, et rend UN verdict.
#
# Pourquoi ce script : il n'existe aucune CI Python dans ce depot (4 workflows, tous Go /
# Node / TypeScript), donc ces tests ne tournent nulle part automatiquement. Deux
# workflows sont fournis a cote, volontairement DESARMES (`workflow_dispatch` seul), sur
# le modele des workflows graphify du depot -- l'equipe decommente leurs declencheurs le
# jour ou elle le decide. En attendant, c'est ce script qui sert.
#
# Usage :
#   bash scripts/test_garde_deepseek.sh                 # unitaires seuls
#   RABBITMQ_URL_TEST=amqp://guest:guest@localhost:5672/ bash scripts/test_garde_deepseek.sh
#
#   PYTHON=/chemin/vers/python bash scripts/test_garde_deepseek.sh   # venv particulier
#
# Prerequis : pytest, et `aio-pika==9.6.2` (la version de production) pour l'integration.
# Un RabbitMQ jetable suffit -- WSL ou `docker run --rm -p 5672:5672 rabbitmq:3.12`.

set -uo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python}"
ROUGE=0
LIGNES=()

lancer() {
  local etiquette="$1"; shift
  local repertoire="$1"; shift
  local pythonpath="$1"; shift

  printf '\n\033[1m=== %s ===\033[0m\n' "$etiquette"
  local sortie
  sortie="$(cd "$repertoire" && PYTHONPATH="$pythonpath" "$PYTHON" -m pytest "$@" -q 2>&1)"
  local code=$?
  echo "$sortie" | tail -6
  local resume
  resume="$(echo "$sortie" | grep -E '^[0-9]+ (passed|failed)|passed|failed|error' | tail -1)"
  if [ $code -ne 0 ]; then
    ROUGE=1
    LIGNES+=("ECHEC  $etiquette : ${resume:-code $code}")
  else
    LIGNES+=("ok     $etiquette : ${resume:-vert}")
  fi
}

echo "Racine du depot : $RACINE"
echo "Interpreteur    : $("$PYTHON" --version 2>&1)"
if [ -n "${RABBITMQ_URL_TEST:-}" ]; then
  echo "Broker de test  : defini -> les tests d'integration vont TOURNER"
else
  echo "Broker de test  : absent -> les tests d'integration seront SAUTES"
  echo "                  (poser RABBITMQ_URL_TEST pour les lancer)"
fi

# 1) la garde elle-meme : bornes, surcharge, innocuite de l'import
lancer "libs/common-utils -- garde tarifaire" \
       "$RACINE" "$RACINE/libs/common-utils/src" \
       libs/common-utils/tests/test_fenetre_tarifaire.py

# 2) les 4 services consommateurs
lancer "QC-caracterisation" \
       "$RACINE/apps-microservices/QC-caracterisation" "." tests/
lancer "QC-fabricant-reference" \
       "$RACINE/apps-microservices/QC-fabricant-reference" "." tests/
lancer "template-llm-service" \
       "$RACINE/apps-microservices/template-llm-service" "." tests/
lancer "nettoyage-bruit-ocr-service" \
       "$RACINE/apps-microservices/nettoyage-bruit-ocr-service" "." tests/

# --- verdict unique ---
printf '\n%s\n' "------------------------------------------------------------------"
for l in "${LIGNES[@]}"; do echo "  $l"; done
printf '%s\n' "------------------------------------------------------------------"

if [ $ROUGE -ne 0 ]; then
  echo "VERDICT : ECHEC"
  exit 1
fi
if [ -z "${RABBITMQ_URL_TEST:-}" ]; then
  echo "VERDICT : vert (unitaires seuls -- l'integration n'a PAS ete exercee)"
else
  echo "VERDICT : vert, integration comprise"
fi
