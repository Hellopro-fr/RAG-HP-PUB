#!/bin/bash
# Cron quotidien d'ingestion Solr (lance par crontab Linkbynet).
#
# 2026-04-30 : ajout core0 (V2 = text_fr) en parallele du V1 historique.
# Le V2 utilise un wrapper HTTP qui appelle 02_alimente_core_v2.php en mode
# CLI simule (full-reindex par defaut).
#
# Tant que le swap V2 -> V1 n'est pas fait (cf 04_swap_cores.sh), on alimente
# les 2 cores en parallele : V1 (hellopro_produit) reste actif pour le trafic
# par defaut, V2 (core0) est utilise par les requetes ?core_v2=1 et tests.

# === V1 (legacy, core hellopro_produit) ===
$LAUNCHER /usr/local/linkbynet/scripts/cron/wget https://script.hellopro.fr/script/annuaire/mt_solr/alimente_core_hellopro_produit.php&
$LAUNCHER /usr/local/linkbynet/scripts/cron/wget https://script.hellopro.fr/script/annuaire/mt_solr/alimente_core_hellopro_societe.php&
$LAUNCHER /usr/local/linkbynet/scripts/cron/wget https://script.hellopro.fr/script/annuaire/mt_solr/alimente_core_hellopro_di.php&

# === V2 (core0, text_fr stemmer) ===
# Wrapper HTTP qui execute 02_alimente_core_v2.php avec --full-reindex.
# Le wrapper est dans /script/annuaire/mt_solr/v2/ (avec les autres scripts V2).
# Token jetable hardcode dans le wrapper (a changer avant prod).
$LAUNCHER /usr/local/linkbynet/scripts/cron/wget "https://script.hellopro.fr/script/annuaire/mt_solr/v2/alimente_core_v2_http.php?token=hp_v2_2026_04_30_xZ7q"&

# === Sync Typesense quotidien (Milvus -> Typesense via API VM) ===
# Appelle l'API VM /sync/incremental qui :
#   1. Upsert produits Milvus modifies depuis 24h (NEW + UPDATED)
#   2. Supprime les orphelins Typesense (DELETED en Milvus)
# Email de notification a la fin (succes ou echec).
$LAUNCHER /usr/local/linkbynet/scripts/cron/wget "https://script.hellopro.fr/script/rag/sync_typesense_daily.php?token=hp_cron_2026_04_30_xZ7q"&

# === Synonymes Typesense ===
# Quotidien : sync_synonyms_daily.php pull le cache local depuis l'API VM.
# Hebdo (lundi) : auto_generate_synonyms_weekly.php regenere les synonymes
# depuis le catalogue Typesense. La logique daily/weekly est dans le script.
$LAUNCHER /usr/local/linkbynet/scripts/cron/wget "https://script.hellopro.fr/script/typesense/sync_synonyms_daily.php?token=hp_synsync_2026_04_30_xZ7q"&
if [ $(date +%u) -eq 1 ]; then
    $LAUNCHER /usr/local/linkbynet/scripts/cron/wget "https://script.hellopro.fr/script/typesense/auto_generate_synonyms_weekly.php?token=hp_syngen_2026_04_30_xZ7q"&
fi