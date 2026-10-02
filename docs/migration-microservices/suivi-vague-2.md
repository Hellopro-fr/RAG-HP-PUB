# Suivi de la vague 2 — actions, adresses, demandes externes

> Tableau de bord vivant de la vague 2. Le **pourquoi** et le **comment détaillé** sont dans [`plan-vague-2.md`](plan-vague-2.md) ;
> ici, on coche. Mis à jour par le DSO après chaque action, relu à chaque point d'équipe.
> Les numéros d'action (0.1, a.2…) sont ceux du plan.

## Légende

⬜ à faire · 🔄 en cours · ✅ fait · ❌ bloqué · ⏭️ reporté / sans objet · ↩️ rollback joué

---

## 1. État des adresses publiques

Une ligne par adresse. C'est la vue « où en est chaque aiguillage ».

| Adresse | Aujourd'hui | Cible | Aiguillage | Sous-vague | TTL 300 s | Certificat | Basculée le | Validée (J+1) | Jumeau VM |
|---|---|---|---|---|:--:|:--:|---|---|---|
| `api.hellopro.eu` | VM `:8500` | `api-gateway-go` (GKE) | A Gandi | V2-c | ⬜ | ⬜ | | | à arrêter au geste |
| `mcp.hellopro.eu` | VM `:8581` | front MCP (à créer) | A Gandi | V2-c / V2-d | ⬜ | ⬜ | | | |
| `rag.hellopro.eu` | VM `:8550` | Cloud Run `api-html-recherche` | A Gandi | V2-d | ⬜ | ⬜ | | | laissé up |
| `login.hellopro.eu` | VM `:8601` | Cloud Run `account-service-frontend` | A Gandi | V2-d | ⬜ | ⬜ | | | laissé up |
| `cmf.hellopro.eu` | VM `:3002` | front à créer | A Gandi | V2-d | ⬜ | ⬜ | | | laissé up |
| `formulaire.hellopro.eu` | VM `:8579` | Cloud Run `nextjs-formulaire-hp` (shadow) | — | ⏭️ hors vague 2 (décision 3) | — | — | | | reste seul |
| `nextjs-conseils.hellopro.eu` (derrière `conseils.hellopro.fr`) | VM `:8610` | Cloud Run `nextjs-conseils-hp` | A Gandi (± règle Ecritel) | V2-d (après GO PROD) | ⬜ | ⬜ | | | laissé up |
| `dlq.hellopro.eu` | VM `:8585` (`dlq-manager-service`, **UP**) — **restreint aux IP Hellopro depuis le 30/09** (F-HP-SEC-028 atténué) | à décider (décision 5) | — | — | — | — | | | |
| `mep.hellopro.eu` | VM `:8321` | hors migration applicative | — | à qualifier | — | — | | | |

## 2. Routes internes

### Routes de la gateway VM (`.env.url`) — V2-a

| Route | Service | Cible Cloud Run | P0 (URL en dur, secrets, capacité) | Dev testeur | Basculée le | Validée (J+1) |
|---|---|---|:--:|---|---|---|
| `SERVICE_DETECTION_SITE_FR` | détection de langue | `api-detection-langue-fr` (rév. 00005, code rapatrié) | ✅ 02/10 | | | |
| `SERVICE_COMPARAISON_TEXTE` | comparaison de texte | `api-comparaison-texte` (rév. 00008) | ✅ 02/10 | | | |
| `SERVICE_EXTRACTOR` | content-extractor | `content-extractor-api-service` (rév. 00010, code + `common_utils` rapatriés) | ✅ 02/10 | | | |
| `SERVICE_OPTIMIZE` | optimize | `optimize-service` (rév. 00006) | ✅ 02/10 | | | |
| | chat-llm | `api-chat-llm` | ⬜ | | | |
| | embedding HTTP | `api-embedding-service` | ⬜ | | | |
| | graph-rag recherche | `graph-rag-api-recherche-service` | ⬜ | | | |
| | graph-rag recherche optim | `graph-rag-api-recherche-optim-service` | ⬜ | | | |
| | graph-rag recherche rust | `graph-rag-api-recherche-rust-service` | ⬜ | | | |
| `SERVICE_SEARCH` | recherche | `api-recherche` | ⬜ | | | |
| | classification | `api-classification` | ⬜ | | | |
| | rest-milvus | `api-rest-milvus` | ⬜ | | | |
| | ingestion | `api-ingestion` | ⬜ | | | |
| | prix-traitement | `prix-traitement` | ⬜ | | | |

### Serveurs MCP (`mcp_servers`) — V2-b

| Serveur MCP | Cible Cloud Run | Clés / quotas IP `35.233.35.8` | Dev testeur | Basculé le | Validé |
|---|---|:--:|---|---|---|
| mcp-api-recherche | `mcp-api-recherche-service` | ⬜ | | | |
| mcp-classification-produit | `mcp-classification-produit-service` | ⬜ | | | |
| mcp-google-analytics | `mcp-google-analytics-service` | ⬜ | | | |
| mcp-google-analytics-minisite | `mcp-google-analytics-minisite-service` | ⬜ | | | |
| mcp-google-search-console | `mcp-google-search-console-service` | ⬜ | | | |
| mcp-semrush | `mcp-semrush-service` | ⬜ | | | |
| mcp-ringover | `mcp-ringover-service` | ⬜ | | | |
| mcp-leexi | `mcp-leexi-service` | ⬜ | | | |
| mcp-neo4j | — (F-HP-SEC-020, reste sur la VM) | ⏭️ | | | |

---

## 3. Actions par sous-vague

### V2-0 — Prérequis (jeu 1/10 → ven 2/10)

| # | Action | Qui | Échéance | Statut | Preuve / commentaire |
|---|---|---|---|:--:|---|
| 0.1 | Revue du plan, décisions, un dev nommé par service | CTO, LEAD, DSO, PROD | jeu 1/10 matin | ✅ | 01/10 : plan validé, devs disponibles à partir du 5/10 |
| 0.2 | Mesures VM : trafic horaire nginx, `dlq.hellopro.eu`, taille des volumes | DSO | jeu 1/10 | ✅ | log `data/cutover/carte-v2-0.log` : `api.` pic 10h-17h UTC, nuit non nulle ; `rag.`, `login.` plats sur 24 h (sondes probables) ; volumes **370 Go** images / **205 Go** crawler ; vhosts publics hors plan : `grafana.`, `n8n-dev.`, `pmyadm.` (phpMyAdmin), `neo4j1.`, `mep.` → 0.16 |
| 0.3 | Load balancer HTTPS prod (back-ends Cloud Run) | DSO | ven 2/10 (`plan`) → `apply` dès les certificats prêts | ⬜ | IP du LB : |
| 0.4 | Certificats par validation DNS (CNAME `_acme-challenge` chez Gandi) | DSO | ven 2/10 (autorisations TF) → CNAME **dès le jeton** (ven 2/10, sinon lun 5/10 après-midi) | ⬜ | |
| 0.5 | NEG GKE pour `api.` et `mcp.` rattachés au LB | DSO | ven 2/10 | ⬜ | |
| 0.6 | TTL 300 s sur les 6 adresses | DSO | **dès le jeton** (ven 2/10, sinon lun 5/10 après-midi) | ⬜ | ≥ 48 h avant V2-c / V2-d (sem. du 12/10) ; voir journal Gandi |
| 0.7 | Cloud Armor en observation sur le LB prod | DSO | ven 2/10 | ⬜ | |
| 0.8 | Liste des URL en dur par service → tickets devs | DSO (liste 1-2/10) → devs (à partir du 5/10) | ven 2/10 (tickets prêts) | ⬜ | conditionne l'ordre de V2-a |
| 0.9 | Test VM → Cloud Run (entrée, authentification) | DSO | jeu 1/10 | ✅ | 01/10 : **OUI** — `api-detection-langue-fr` et `api-comparaison-texte` répondent `200` depuis la VM (démarrage à froid 5-7 s, puis 0,55 s) → **V2-a depuis la gateway VM, comme prévu** ; ⚠️ mais ils répondent aussi **sans authentification**, entrée `all` → audit de tous les Cloud Run avant d'y envoyer du trafic (action 0.18) ; `min instances ≥ 1` nécessaire |
| 0.10 | Runbook HTTP + scripts P1 / bascule / relevés | DSO | ven 2/10 | ⬜ | |
| 0.11 | Message à Ecritel | DSO | jeu 1/10 | ⬜ | voir § 4 |
| 0.13 | Usage réel des services P9 sur la VM (logs 7 jours, appelants, routes `.env.url`) | DSO | jeu 1/10 | ✅ | `api-gateway-service`, `api-model`, `api-chatbot` : **aucun conteneur** sur la VM (rien à faire) ; `graph-rag-api-recherche-service-debug` **UP depuis 4 mois**, appelé seulement par **`api-catalog-service`** (`172.20.0.148`, sondage `/openapi.json`) → aucun usage fonctionnel → **arrêt en réserve** (décision 4), après contrôle de `.env.url` ; `SERVICE_CRAWLING=reverse-proxy:8050/crawler` (VM), `SERVICE_OPTIMOTEUR=10.0.1.240:8570` (**déjà sur GKE**, IP interne) ; **02/10 08:08 UTC : `…-service-debug-1` arrêté en réserve** (`vm_reserve.sh`, route `SERVICE_GRAPHDEBUG` gardée dans `.env.url` jusqu'à V2-c, seuls appels = lecture de documentation) |
| 0.14 | **F-HP-SEC-028** : journal d'accès `dlq.hellopro.eu`, puis fermeture de l'accès public (nginx) | DSO | **30/09 – 1/10, prioritaire** | ✅ | 30/09 12:44 UTC : allowlist 8 IP Hellopro + `deny all` ; `403` hors liste, accès bureau / télétravail / Ecritel OK ; aucune modification ni lecture de messages externe dans le journal |
| 0.16 | Vhosts publics hors plan : `pmyadm.hellopro.eu` (phpMyAdmin), `grafana.`, `n8n-dev.`, `neo4j1.`, `mep.` — contrôle d'accès nginx et journal (même méthode que F-HP-SEC-028) | DSO | jeu 1/10 | ✅ | 01/10 : **aucun contrôle d'accès nginx** sur les 5 ; IP hors liste : pmyadm 97, grafana 128, n8n-dev 169, neo4j1 13, mep 130 ; phpMyAdmin 5.2.3 consulté par des robots (pages de doc, scans `.env`/`.git`) → allowlist `vhost_allowlist.sh` (F-HP-SEC-029) : ✅ **phpMyAdmin fermé 01/10 10:48 UTC** (aucune connexion réussie hors liste dans le journal ; 18 tentatives échouées) ; ✅ **grafana et neo4j1 fermés 01/10 11:53 UTC** ; **mep** : appels `launch_mep` / `claim_mep` **légitimes** (confirmé 01/10 : actions depuis des mobiles) → pas d'allowlist ; ✅ **durci 01/10 14:49 UTC** (`api.php` exige une session : 401 sans session ; 429 après 10 connexions/min/IP) ; ✅ **n8n-dev durci 01/10 12:15 UTC** (option A : 404 sur chemins sensibles, 429 après 10 `POST /rest/login`/min/IP) |
| 0.17 | Dépendances VM ↔ cloud : inventaire des appelants restés sur la VM pour chaque service qui migre (compose, `.env.url`, `mcp_servers`, code) ; règle « jumeau arrêté seulement sans appelant VM » | DSO | ven 2/10 | 🔄 | inventaire initial du compose : plan § 7bis |
| 0.18 | **Audit des Cloud Run** : entrée (`all` / `internal`), appel anonyme possible ou non, pour les ~31 services ; un service appelable sans authentification contourne le contrôle de la gateway | DSO | ven 2/10 | ✅ | 01/10 : **29/31 publics et anonymes** (`all` + `allUsers`, fixés par les wrappers CD), tous à 0 instance minimale → **F-HP-SEC-030** ; trafic 7 j (métrique) : **0 requête sur 27 services**, `image-comparison-service` **9 659** (appelant à identifier) ; ✅ **confinement 01/10 17:28 UTC** : `allUsers` retiré des 24 services sans trafic (audit relu) ; image-comparison = robots (rafales de 404) ; ✅ **lot 2 17:55 UTC** (image-comparison + 4 fronts) → **`allUsers` = 0 sur les 31 services** ; reste : correction des wrappers CD à chaque bascule (sinon le CD rouvre), test d'entrée interne VM / GKE (0.19), journaux Cloud Run absents |
| 0.19 | Test d'entrée **interne** (`internal-and-cloud-load-balancing`) sur un Cloud Run sans trafic, appelé depuis la VM, depuis un pod GKE et depuis internet → cible d'entrée des API de V2-a ; et authentification (jeton) côté gateway si besoin | DSO | ven 2/10 | ✅ | 02/10 07:18 UTC (`cr_test_entree_interne.sh`, `api-detection-langue-fr`) : **internet 404 (fermé), VM 200, pod GKE 200** → **cible A validée** : entrée `internal-and-cloud-load-balancing` + appel anonyme, service remis en état (`all`, `allUsers=0`) ; prérequis : le smoke test du CD doit ignorer toute entrée ≠ `all` (`deploy-cloud-run.yml`) |
| 0.20 | Smoke test du CD Cloud Run : ignorer toute entrée ≠ `all` (`deploy-cloud-run.yml`), prérequis des wrappers V2-a | DSO | ven 2/10 | ✅ | PR `fix/cd-smoke-internal-ingress` mergée 02/10 (gate verte) |
| 0.21 | **Rapatriement `poc` → `prod`** des correctifs urgents (plan § 7quater), **assuré par le DSO** (02/10) : PR detection-langue, PR content-extractor + `common_utils`, avec les réglages cible des wrappers ; information aux devs ([message](demande-rapatriement-poc-prod.md)) | DSO | PR prêtes ven 2/10, merge lun 5/10 matin | ✅ (lot 1) | prérequis de la bascule de ces 2 routes ; comparaison-texte et optimize : rien à rapatrier ; 02/10 : PR detection-langue, content-extractor + `common_utils`, wrappers comparaison / optimize **mergées**, déployées |
| 0.15 | Clé SSH ajoutée aux métadonnées **du projet** par `gcloud compute scp` (30/09, utilisateur `deploy`) : décider de la garder ou la retirer (accès à toutes les VM qui acceptent les clés projet) | DSO | fin de vague | ⬜ | |
| 0.12 | Jeton Gandi LiveDNS temporaire (`hellopro.eu` seul, expiration ≈ 23/10) → Secret Manager `gandi-livedns-pat` ; scripts `GET`/`PUT`/`GET` | titulaire Gandi (création), DSO | **ven 2/10 si possible, sinon lun 5/10 après-midi** — [procédure](procedure-jeton-gandi.md) | ⬜ | révocation prévue en fin de vague |

### V2-a — Routes gateway (lun 5 → mar 6/10)

| # | Action | Qui | Échéance | Statut | Preuve / commentaire |
|---|---|---|---|:--:|---|
| a.1 | P0 de chaque service (fiche verte) | DSO | veille | ✅ (lot 1) | 02/10 (`p0_route.sh`, `p0_code.sh`, `p0_diff.sh`) : **comparaison-texte** et **optimize** : code VM = Cloud Run = prod ✅ ; **detection-langue** : `scraper.py` de la VM = `features/poc` (correctif PROD du 24/09 : fuite du pool de navigateurs), **absent de prod** ; **content-extractor** : `config.py` VM = `features/poc` (`RESULT_CACHE_VERSION` v2, 30/09), absent de prod → **rapatriement poc → prod avant bascule** ; Redis absent sur Cloud Run (detection, extractor) ; `min_instances` 0 → 1 ; bibliothèques à comparer ; **02/10 : 4 services prêts** — PR de rapatriement + wrappers mergées, CD vert (smoke ignoré, entrée interne), vérifié : entrée interne, `allUsers`=1, `min`=1, internet 404, VM 200 (0,6 s), code VM = image Cloud Run (detection 60/60, extractor 18/18), Redis prod joint depuis Cloud Run |
| a.2 | Bascule des routes une à une (tableau § 2) | DSO | lun 5 → mar 6/10 | ⬜ | script `bascule_route.sh` (plan / apply / check / revert, écriture en place de `.env.url`, sauvegarde horodatée) |
| a.3 | Test du parcours réel après chaque route | devs | au fil de l'eau | ⬜ | |
| a.4 | Relevés midi / 17h / nuit ; décision J+1 | DSO, LEAD | mer 7/10 9h30 | ⬜ | |

### V2-b — MCP (mer 7/10)

| # | Action | Qui | Échéance | Statut | Preuve / commentaire |
|---|---|---|---|:--:|---|
| b.1 | Dump `mcp_servers` | DSO | mer 7/10 9h | ⬜ | fichier : |
| b.2 | Une ligne `mcp_servers` à la fois (tableau § 2) | DSO | mer 7/10 | ⬜ | |
| b.3 | Test d'un outil par serveur MCP | dev MCP | mer 7/10 | ⬜ | |
| b.4 | Clés tierces et quotas depuis `35.233.35.8` | DSO | mar 6/10 | ⬜ | |

### V2-c — Bloc gateway B1 + B3 (journée dédiée, sem. du 12/10)

| # | Action | Qui | Échéance | Statut | Preuve / commentaire |
|---|---|---|---|:--:|---|
| c.1 | Version gateway VM = image GKE ; parité des 5 jetons | DSO ; LEAD confirme | jeu 8/10 | ⬜ | |
| c.2 | Services K8s, ConfigMap `.env.url`, icônes, sidecar `/comparator` `/crawler`, variables Docker | DSO | jeu 8/10 | ⬜ | |
| c.3 | Dump complet `gateway_db` | DSO | J 9h | ⬜ | fichier / taille : |
| c.4 | Bascule mcp-gateway → zoho, templates-runner → api-gateway-go ; jumeaux arrêtés | DSO | J 9h30-11h | ⬜ | |
| c.5 | A Gandi `api.` et `mcp.` → IP LB | DSO | J 11h | ⬜ | voir journal Gandi |
| c.6 | `graph-rag-api-admin`, `graph-rag-dlq-manager` | DSO | J après-midi | ⬜ | |
| c.7 | Tests fonctionnels gateway et MCP | devs | J | ⬜ | |
| c.8 | Décision J+1 (rollback prêt) | DSO, LEAD | J+1 9h30 | ⬜ | |

### V2-d — SSO et fronts (sem. du 12/10, selon décisions)

| # | Action | Qui | Préalable | Statut | Preuve / commentaire |
|---|---|---|---|:--:|---|
| d.1 | `account-service-backend` sur Cloud Run (`all-traffic`) | DSO | V2-c | ⬜ | |
| d.2 | `login.hellopro.eu` | DSO | d.1 + clients OAuth (devs SSO) | ⬜ | |
| d.3 | `rag.hellopro.eu` | DSO | test de connexion par un dev | ⬜ | |
| d.4 | `cmf.hellopro.eu`, front `mcp.` | devs puis DSO | fronts construits | ⬜ | |
| d.5 | `formulaire.hellopro.eu` | — | — | ⏭️ | hors vague 2 (décision 3 du 30/09) |
| d.6 | `conseils.hellopro.fr` (via `nextjs-conseils.hellopro.eu`) | PROD décide, DSO exécute | GO PROD + réponse Ecritel | ⬜ | |

### V2-e — Stockage (sem. du 19/10)

| # | Action | Qui | Échéance | Statut | Preuve / commentaire |
|---|---|---|---|:--:|---|
| e.1 | Cible GCS pour `image_download_data` et `crawler_data` | DSO propose, CTO valide | sem. du 19/10 | ⬜ | tailles au 01/10 : 370 Go et 205 Go |
| e.2 | Code `image-download`, `image-cdn`, `crawler-service` | devs | à planifier | ⬜ | |
| e.3 | Retrait de l'IP publique VM (plus rien n'y pointe) | DSO + Ecritel | fin de vague | ⬜ | |

---

## 4. Demandes externes

### Ecritel

| Date | Objet | Envoyé par | Statut | Réponse (résumé) |
|---|---|---|:--:|---|
| jeu 1/10 | Règles Apache vers `35.245.31.1` : `conseils.hellopro.fr`, `www.hellopro.fr`, autres (message prêt : plan § 5) | DSO | ⬜ | |

### Journal des modifications Gandi (DSO)

Une ligne par modification, **avant** de la faire (valeur d'origine notée = retour arrière garanti).

| Date / heure | Enregistrement | Type | Avant | Après | TTL | Par | Motif |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

---

## 5. Décisions

Le détail de chaque décision (pourquoi, objectif, options, recommandation, conséquence si on ne tranche pas) : [`plan-vague-2.md` § 6](plan-vague-2.md#6-décisions--pourquoi-objectif-options-recommandation).

| # | Décision | Qui | Échéance | Statut | Décision prise |
|---|---|---|---|:--:|---|
| 1 | Plan et calendrier ; un dev par service P4/P5 | CTO, LEAD | jeu 1/10 | ✅ | **01/10 : plan validé, devs prêts à partir du 5/10** |
| 2 | Bascule de `conseils` (SEO, pages PHP non migrées) | PROD, LEAD | avant V2-d | ✅ | **30/09 : GO reco** — back-end seul ; comparaison préalable Cloud Run / VM, **contenus identiques exigés** |
| 3 | Formulaire Next.js | LEAD | jeu 1/10 | ✅ | **30/09 : hors vague 2** — pas en production, fonctionnalités en cours ; Next 15 non urgent |
| 4 | P9 à trancher (`api-gateway-service`, `api-model`, `api-chatbot`, `…-debug`, `SERVICE_CRAWLING`, `SERVICE_OPTIMOTEUR`) | LEAD | jeu 8/10 | ✅ | **01/10 : règle** — non migré = reste sur la VM : **UP** si utilisé et non migrable, **arrêté en réserve** sinon ; classement par l'action 0.13 ; aucune suppression pendant la vague |
| 5 | `dlq-manager-service` / `dlq.hellopro.eu` | métier, CTO | avant V2-c | ✅ | ⚠️ 30/09 : service **UP depuis 2 mois** sur la VM, **exposé sans authentification** (F-HP-SEC-028 CRITICAL) → **accès fermé aux IP Hellopro le 30/09** (0.14 ✅). Journal : outil **utilisé** (requeue quotidien par le bureau, appels Ecritel) → ✅ **01/10 : on laisse sur la VM d'abord** (UP, restreint aux IP Hellopro) ; migration GKE quand F-HP-SEC-027 est corrigé |
| 6 | Cloud Armor : critères de passage en blocage | RSSI | avant V2-d | ✅ | **30/09 : option A** — observation, blocage adresse par adresse après 7 jours sans faux positif, limite de débit sur `login.` (« la sécurité est importante ») |
| 7 | CD GKE prod (F-HP-IND-005) : calage | CTO | jeu 1/10 | ✅ | **30/09 : GO, progressif** — cadrage 1-2/10, puis **un service par jour**, testé et validé avant le suivant (à partir du 19/10) |
| 8 | Certificats par validation DNS (évolution du module LB) | CTO, DSO | jeu 1/10 | ✅ | **30/09 : GO reco** (Certificate Manager, CNAME Gandi) |
| 9 | Jeton API Gandi temporaire plutôt que l'interface | CTO, DSO | jeu 1/10 | ✅ | **30/09 : GO** — le jeton va être créé (action 0.12) |

---

## 6. Journal

| Date | Événement |
|---|---|
| 30/09 | Série des consumers close (GO L6). Inventaire vague 2 : 85 services encore sur la VM. Faits confirmés : DNS `hellopro.fr` / `hellopro.eu` pilotés par nous sur Gandi ; Apache `hellopro.fr` = Ecritel ; `*.hellopro.eu` Gandi → VM directe ; `conseils.hellopro.fr` résout vers le front Ecritel (45.223.103.188) ; vhost VM `nextjs-conseils.hellopro.eu` → `:8610`. Plan et suivi rédigés, à valider le 1/10. Décision 3 prise : formulaire hors vague 2 (pas en production). Détail des décisions ajouté au plan (§ 6). Soir : décisions 2, 6, 7, 8, 9 prises ; 4 = revérifier l'usage sur la VM ; **5 : `dlq-manager-service` UP depuis 2 mois et `dlq.hellopro.eu` exposé sans authentification → F-HP-SEC-028 (CRITICAL)**, mesure immédiate. |
| 01/10 | Réserve embedding levée (L6 entièrement validé). Revue : décision 1 (plan validé, devs à partir du 5/10) et décision 4 (règle « non migré = VM, UP ou arrêté en réserve ») ; décision 5 : **on laisse sur la VM d'abord**. Mesures VM (0.2) et usage P9 (0.13) relevés ; nouvelle règle « un jumeau VM n'est arrêté que sans appelant resté sur la VM » (plan § 7bis, action 0.17) ; 5 vhosts publics hors plan à contrôler (0.16). |
| 01/10 soir | Exposition anonyme des Cloud Run fermée (31/31). Jeton Gandi : ven 2/10 si possible, sinon lun 5/10 après-midi ([procédure](procedure-jeton-gandi.md)) ; seuls les CNAME des certificats et le TTL en dépendent, sans effet sur V2-a / V2-b. |
| 02/10 | 0.19 : la VM et GKE sont vus comme internes par Cloud Run → **V2-a en entrée interne, sans jeton ni code** ; correctif du smoke test CD à faire avant les wrappers. |
| 02/10 | Service debug graph-rag mis en réserve (décision 4). Correctif du smoke test CD préparé (0.20). |
| 02/10 | Constat (confirmé par le user) : des correctifs urgents partent sur la VM par `features/poc` sans passer par `prod`. P0 : comparaison-texte et optimize prêts ; detection-langue et content-extractor attendent le rapatriement (0.21). Nouvelle règle : après bascule, les correctifs vont dans `prod`. |
| 02/10 après-midi | V2-a lot 1 prêt : 3 PR (rapatriement detection-langue, content-extractor + `common_utils`, wrappers comparaison / optimize) mergées et déployées, vérifiées (entrée interne, VM 200, internet 404, code = VM, Redis OK). Script de bascule de route prêt. |
