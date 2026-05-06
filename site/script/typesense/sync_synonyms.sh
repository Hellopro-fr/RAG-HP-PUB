#!/bin/bash
# =============================================================================
# sync_synonyms.sh
# -----------------------------------------------------------------------------
# Wrapper Linkbynet pour le cron des synonymes Typesense.
#
# Quotidien : sync_synonyms_daily.php (pull cache depuis API VM)
# Hebdo (lundi) : auto_generate_synonyms_weekly.php (regenere depuis Typesense)
#
# Pattern : Ecritel -> API VM (comme moteur_solr.sh)
#
# Cron suggere :
#   0 3 * * *   /script/typesense/sync_synonyms.sh   # tous les jours 3h
#
# Le script gere lui-meme la logique daily/weekly via [ $(date +%u) -eq 1 ].
# =============================================================================

LAUNCHER=/usr/local/linkbynet/scripts/cron/launcher.sh

# === DAILY : Sync cache local PHP front depuis API VM ===
$LAUNCHER /usr/local/linkbynet/scripts/cron/wget "https://script.hellopro.fr/script/typesense/sync_synonyms_daily.php?token=hp_synsync_2026_04_30_xZ7q"&

# === WEEKLY (Lundi) : Auto-generate synonymes depuis catalogue Typesense ===
# Lance uniquement le lundi (jour 1 = lundi en POSIX). Si nouvelle ingestion
# en cours de semaine, lancer manuellement le script via curl.
if [ $(date +%u) -eq 1 ]; then
    $LAUNCHER /usr/local/linkbynet/scripts/cron/wget "https://script.hellopro.fr/script/typesense/auto_generate_synonyms_weekly.php?token=hp_syngen_2026_04_30_xZ7q"&
fi
