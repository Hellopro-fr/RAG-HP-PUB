# Lot V2-a3-bis — classification, ingestion, rest-milvus : reportés avec correctifs DSO

> **Vague 2 · lot créé le 09/10** à partir de V2-a3 (décision user 09/10 10h05) · **⏸️ DIFFÉRÉ**.
> V2-a3 est clos à 2 routes sur Cloud Run (recherche, prix-traitement : GO définitif le 09/10). Les 3 services ci-dessous
> ont été basculés le 08/10, puis **remis sur la VM** après des échecs mesurés en prod ; chacun a une cause identifiée
> ou probable et un **correctif de code DSO** à préparer. Critère de reprise : la réduction de la VM le rend utile
> (aucun gain de coût tant que la VM reste) — cf. [`../reports-et-decisions-vague-2.md`](../reports-et-decisions-vague-2.md).
> Procédure : [`../procedure-bascule-route-http.md`](../procedure-bascule-route-http.md) · historique détaillé : [`V2-a3.md`](V2-a3.md) et [`../suivi-vague-2.md`](../suivi-vague-2.md) (08-09/10).

## Composition et état

| Service | Route `.env.url` (actuelle, VM) | Cloud Run | Pourquoi revenu sur la VM | Correctif DSO à préparer |
|---|---|---|---|---|
| `api-rest-milvus` | `SERVICE_REST_MILVUS=http://api-rest-milvus-lb:8517` | `api-rest-milvus` (`min=0`, Redis ✅ #877) | 2e bascule 08/10 14:44 : rafale servie (8 505 × `200`), mais `POST /global-stats` en `503` hors rafale (13:05 : Cloud Run `503` à l'arrêt d'une instance ; 13:10 : réponse en 19 s, appelant parti à ~10 s). Hypothèse : rafraîchissement du cache en tâche de fond privé de CPU hors requête. **CPU toujours alloué refusé (FinOps, +35-40 €/mois)** | `stats.py:181-252` : rafraîchir le cache dans la requête (ou à la demande avec délai borné) au lieu d'`asyncio.create_task` ; `main.py` : `logging.basicConfig(level=INFO)` (les logs `INFO` ne sortent pas) |
| `api-classification` | `SERVICE_CLASSIFICATION=http://api-classification-service:8577` (10 réplicas VM) | `api-classification` (`min=0`, `SERVICE_NAME` ✅ #876) | nuit du 08 au 09/10 : ≈ 485 appels de 20h à 02h UTC (1,3/min) → **7 × `200`, 459 × `503`, 19 × `504`** : requêtes extrêmement lentes (pas la capacité) | profiler une requête sur Cloud Run (temps par étape) ; pistes : client HTTP `max_connections=1` (`classification.py:669`), appels gRPC embedding (priorité MOYENNE depuis #876), dépendances lentes ; puis correctif et parité chronométrée |
| `api-ingestion` | `SERVICE_INGESTION=http://api-ingestion-service:8509` | `api-ingestion` (`min=0`) | lot de 02h UTC : **84 × `413`** (corps > 32 Mio, limite Cloud Run en HTTP/1.1) ; lot de 18h UTC OK | servir en HTTP/2 de bout en bout (`hypercorn` à la place d'`uvicorn` + `use_http2` sur Cloud Run, sans surcoût) **ou** maintien définitif sur la VM ; au passage : fuite de connexions AMQP (`publisher.py:37-41`) |

## Check-list du jour J (reprise du lot)

1. Correctif DSO mergé dans `prod` (PR), CD vert ; **drift** `drift_lot.sh` ; `SERVICE_NAME` et noms des variables = VM.
2. `min=1` remis juste avant (`set_min_instances.py`), CD, `v2a_verif_deploy.sh`.
3. Référence 24 h + profil horaire (`bascule_route.sh check SINCE=24h`, `gw_fenetre.sh`) ; **seuils fixés avant**.
4. Parité chronométrée (`parite_rest_milvus.sh`, équivalent à écrire pour classification / ingestion).
5. Bascule une route à la fois (`apply`, `rescan`, `preuve`), relevés 15/30/60 min **et à la prochaine rafale** (rest-milvus 14h-16h, classification 23h-5h, ingestion lot de 5h).
6. Coût : estimation mensuelle Cloud Run face au gain VM (règle FinOps du 09/10).

## Feuille de lot

| Étape | Heure | Résultat | Par |
|---|---|---|---|
| Création du lot (report depuis V2-a3) | 09/10 10:05 | décision user : V2-a3 clos à 2 routes ; classification, ingestion, rest-milvus reportés avec correctifs DSO ; `min=0` sur les Cloud Run inutilisés (#879) | user · DSO |
| Correctifs DSO | | ⬜ | DSO |
| Reprise (check-list du jour J) | | ⬜ | DSO |
