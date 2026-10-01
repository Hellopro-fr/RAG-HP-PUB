# Contract snapshots

Réponses de référence Express capturées en pré-cutover.
Utilisées par `tests/contract_smoke.sh` pour vérifier l'iso strict de la version Go post-cutover.

## Workflow

1. Avec Express toujours en marche (port 3001) :
   ```bash
   bash tests/capture_snapshots.sh http://localhost:3001 "$ADMIN_PASSWORD"
   ```

2. Commit les snapshots produits dans ce dossier.

3. Après cutover de la version Go :
   ```bash
   bash tests/contract_smoke.sh http://localhost:3002 "$ADMIN_PASSWORD"
   ```

   Exit 0 = parfait, exit N = N divergences à investiguer.

## Note

Les snapshots peuvent contenir des timestamps qui changent entre captures.
Le script utilise `jq -S` pour normaliser le tri des clés mais ne masque pas les valeurs dynamiques.
À enrichir avec un masking JSON si l'iso strict accroche sur ces champs.
