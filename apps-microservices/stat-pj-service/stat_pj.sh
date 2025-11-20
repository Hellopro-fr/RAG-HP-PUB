#!/bin/bash

# Plage d'années à traiter
START_YEAR=2018
END_YEAR=2025

# Créer un dossier pour les logs
LOG_DIR="~/RAG-HP-PUB/apps-microservices/stat-pj-service/logs"
mkdir -p $LOG_DIR

# Boucle sur chaque année
for YEAR in $(seq $START_YEAR $END_YEAR); do
    echo "📄 Lancement du script pour l'année $YEAR..."
    cd $LOG_DIR
    python3 verif_nb_caractere_pj.py $YEAR > "$LOG_DIR/output_$YEAR.log" 2>&1
    echo "✅ Script pour l'année $YEAR terminé. Log : $LOG_DIR/output_$YEAR.log"
done

echo "🎉 Tous les scripts sont terminés."
