# Vague 2 — registre des reports, décisions et traitements différés

> **À quoi sert ce document** : tout ce qui a été **décidé, reporté ou laissé ouvert** pendant la vague 2, au même endroit,
> pour le reprendre plus tard sans relire tout le journal. Chaque ligne dit **quoi**, **pourquoi**, **où est la preuve**,
> **ce qu'il faut faire** et **quand le reprendre**. Le journal détaillé reste [`suivi-vague-2.md`](suivi-vague-2.md) ;
> les findings détaillés sont dans `Docs/DevSecOps/plan_et_strategie_remediation.md` et `backlog.md`.
>
> **Principes de décision (user)** : (1) **objectif = réduire les coûts** — un réglage Cloud Run se chiffre face au gain réel
> sur la VM ; pas de surcoût permanent pour un service qui ne fait rien économiser tant que la VM reste (09/10) ;
> (2) **les défauts de code vus en migration sont corrigés par le DSO après la migration**, puis rapport aux devs (07/10) ;
> (3) **les services en stabilisation restent sur la VM** ; on récupère leurs changements `features/poc` juste avant la migration (07/10).
>
> Mis à jour le **09/10/2026 (soir)**.

## 1. Lots et services reportés

| Élément | Décision (date) | Pourquoi | Preuves | À faire | Reprise |
|---|---|---|---|---|---|
| **V2-a3-bis** : `api-rest-milvus`, `api-classification`, `api-ingestion` | basculés le 08/10, **remis sur la VM** (08/10 16:22 ; 09/10 09:10), lot reporté (09/10) | rest-milvus : `global-stats` en `503` hors rafale ; classification : 97 % d'échecs sur la rafale de nuit (lenteur) ; ingestion : `413` (corps > 32 Mio) | `lots/V2-a3-bis.md`, `lots/V2-a3.md`, logs `data/cutover` du 08-09/10 | 3 correctifs DSO (cf. fiche) | quand la réduction de la VM le rend utile |
| **V2-a4** : `agent-service`, `mcp-hellodata-service` (+ `mcp-normalize-unite`) | préparé puis **différé** (07/10) ; Cloud Run supprimés | services en stabilisation (correctifs fréquents via `features/poc`) | `lots/V2-a4.md` (check-list du jour J) | drift `poc` → rapatriement, CD, parité, bascule | feu vert des devs « stabilisés » |
| `unit-registry`, `neo4j_new`, `tailscale`, `mcp-template-neo4j` | **restent sur la VM** (07/10) | services temporaires / liaison VPS OpenClaw | `suivi-vague-2.md` (07/10 14:30) | rapatrier leur code dans `prod` quand même | — |
| `mcp-google-analytics-minisite-service` (V2-b) | **reste sur la VM, pas d'arrêt** (14/10) | aucun usage depuis le 30/05, mais le projet de mini-sites reprend bientôt avec de nouveaux sites | `lots/V2-b.md` | migrer avec la reprise du projet (même méthode que GA : P0, fichier d'identifiants, outils) | reprise du projet mini-sites |
| **V2-c** : périmètre (15/10) | joué **lundi 19/10** ; **image-comparison non migré** ; **services dépendant des MySQL VM non migrés pour l'instant** (mcp-gateway, mcp-zoho, et account-service en V2-d) ; **analyse préalable** pour les services à fort risque (api-gateway-go, DLQ) | décision équipe : limiter le risque sur les flux | `lots/V2-c.md`, `drift-1015-0859.log` | périmètre réel service par service, analyse de risque, validation, cartes | 19/10 |
| **V2-c** : analyse de risque (15/10) | hors lot confirmé par les relevés (MySQL : api-gateway-go, mcp-gateway, mcp-zoho ; templates-runner suit mcp-gateway) ; graph-rag-api-admin **ne migre pas** (client Ecritel, écritures Neo4j, aller-retour gRPC, aucun gain) ; **option B recommandée : pas de bascule le 19/10** (option A : graph-rag-dlq-manager seul, gain quasi nul) | **option B validée (15/10)** : pas de bascule le 19/10 ; tout le lot reste sur la VM | `lots/V2-c.md` § Analyse de risque | shadows GKE inactifs à réduire à 0 (après mesure) ; usage du 19/10 à choisir | 19/10 |
| **api-recherche** (V2-a3) | **remise sur la VM le 15/10** → **V2-a3-bis** | lot de nuit (requêtes de 20 Ko, client `172.20.0.1`) qui ne termine jamais et sature Cloud Run (56 % d'erreurs la nuit à 900 s) | `rapports/decision-retour-vm-api-recherche-2026-10-15.md` | identifier le client, mesurer sur la VM, corriger, rejouer une nuit | V2-a3-bis |
| `document-echange-processor-service`, `qc-fabricant-reference`, `prix-extraction-siteweb` | **restent sur la VM** (vague 1) | pas d'équivalent GKE | `inventaire-services-migration-par-lot.md:227`, `correspondance-endpoints-vm-cloud.md:130` | lot à définir | réduction de la VM |
| `mcp-classification-produit-service` (V2-b) | basculé le 09/10 08:30 UTC, **remis sur la VM** (09/10) et **rattaché à V2-a3-bis** | dépend d'api-classification : sur Cloud Run il appelle l'URL `run.app` d'api-classification, en entrée interne → `404` ; et api-classification est revenue sur la VM | `suivi-vague-2.md` (09/10 ~11:40), `deploy-mcp-classification-produit-service.yml:58`, `deploy-api-classification.yml:62` | à la reprise de V2-a3-bis : VPC Connector sur le MCP **ou** URL interne, après la bascule d'api-classification | avec V2-a3-bis |

## 2. Décisions techniques et options écartées

| Sujet | Décision (date) | Option écartée et raison |
|---|---|---|
| rest-milvus, `global-stats` | correctif de code DSO (09/10) | **CPU toujours alloué** (`--no-cpu-throttling`) : +35-40 €/mois estimés pour des échecs ponctuels |
| `min_instances` des services revenus sur la VM | `min=0` (PR #879, 09/10), `min=1` remis juste avant la rebascule | garder `min=1` : ≈ 10 €/mois chacun sans trafic |
| `opti-moteur-front` → embedding | garde l'appel VM `10.11.0.2:8555` (option A, 07/10) — **F-HP-MIG-014** | repointer vers Cloud Run : sortie HTTPS internet + `min=1` + latence |
| hellodata sur Cloud Run (quand V2-a4 reprendra) | frontière VPC acceptée (option A, 07/10) — **F-HP-SEC-034** | garder hellodata sur la VM |
| Crawler | repointé vers detection/extractor Cloud Run (07/10), recreate avec `--no-deps --scale crawler-service=7` | `up -d` simple (aurait supprimé 6 crawlers) |
| Ordre et méthode V2-b | serveur par serveur, changement d'URL par le dev responsable de mcp-gateway (interface admin), test d'outil réel avant le relevé (09/10) | changement en SQL : registre en mémoire, la gateway ne relirait pas |
| Google Analytics : 9 outils sur Cloud Run au lieu de 7 | **maintien** (09/10) : les 7 outils de la VM sont présents, 2 ajouts en lecture (`analytics-mcp==0.6.0` figé en `prod`) ; compte de service en lecture seule | retour arrière au seul motif du nombre d'outils |
| GSC : `403` sur `sc-domain:hellopro.fr` au test après bascule (12/10) | **maintien** : `list_properties` montre une seule propriété (`https://www.hellopro.fr/`, `siteFullUser`), rapport OK dessus → droit Google du compte de service, hors migration | retour arrière sur le critère « 0 `403` dans les logs du jumeau » : non probant, `mcp-proxy` n'écrit pas les erreurs d'outils |
| Jumeaux VM leexi et ringover | **restent démarrés** (12/10) : mcp-gateway les appelle en direct (`LEEXI_INTERNAL_URL`, `RINGOVER_INTERNAL_URL`) pour l'admin et le périmètre des jetons à chaque appel d'outil ; arrêt = refus des jetons à périmètre | arrêt immédiat après la bascule (ce qu'on fait d'habitude pour un jumeau) |

## 3. Surveillances et preuves en attente

| Sujet | Seuil / attendu | Prochaine lecture |
|---|---|---|
| Rafale d'embedding de 21h (V2-a2) | VM 8-12 % de `503` ; Cloud Run 17 % (07/10), 15,8 % (08/10) ; **seuil 20 %** | relevé de nuit suivant |
| Repointage du crawler | jumeaux VM detection/extractor à 0 **et** Cloud Run qui reçoit les appels du crawl | premier crawl (aucun depuis le 07/10) |
| **Maintenance GCE de la VM GPU** (12/10 20:00 → 13/10 00:00 UTC, arrêt + redémarrage) | état identique à la référence ; 62 conteneurs passés `no` → `unless-stopped` (09/10) | **clos le 13/10** : VM redémarrée à 21:04 UTC, état identique à la référence, réservation L4 `READY`, GPU visibles, 5 MCP `healthy` |
| MCP basculés (leexi, ringover, Google Analytics) | usage réel sur Cloud Run (leexi 2-114 appels/j, ringover 4-242/j), 0 erreur ; jumeaux VM à 0 | relevé J+1 lundi 12/10, puis mise en réserve des jumeaux (`vm_reserve.sh`) |
| Google Analytics : 2 × `404` au changement d'URL, 1 flux coupé à 300 s | ne doit pas se répéter en régime établi | relevé lundi 12/10 |
| ↳ relevé du 12/10 | **clos** : 404 et coupure non répétés depuis le 09/10 14:07 ; leexi 38 et ringover 109 appels d'outils sans erreur | — |
| Recherche après la maintenance (13/10) | 5,6 % d'erreurs en régime établi (02h-06h UTC) ; pics à 21h-00h = arrêt et démarrage à froid | relevé de la nuit du 13 au 14/10 (seuil 15 %) |
| ↳ nuit du 13 au 14/10 | jour 0,4 % ; **nuit 39 %** (paquets de `504` par heure, déjà présents la nuit précédente) → diagnostic de l'appelant de nuit en cours ; pas de retour arrière avant d'en connaître la cause | 14/10 |
| ↳ décision (14/10) | **délai Cloud Run de la recherche porté à 900 s** (PR) : la VM n'avait pas de délai ; coût = temps de traitement, pas de surcoût permanent ; mesure la nuit du 14 au 15/10 | retour immédiat sur la VM (gain de jour perdu : 0,4 % contre 7,7 %) |
| ↳ nuit du 14 au 15/10 (900 s) | **échec** : 25 × `504` à 900 s (les requêtes de 20 Ko ne terminent jamais), 311 × `503` la nuit (capacité saturée) → **retour de la recherche sur la VM (15/10)**, ajout à **V2-a3-bis** ; Cloud Run à repasser en `min=0` (≈ −10 €/mois) | délai 3 600 s : saturerait encore plus la capacité ; plus de workers / vCPU : surcoût permanent pour un lot de nuit inconnu |
| mcp-gateway : `LEEXI_INTERNAL_URL` / `RINGOVER_INTERNAL_URL` vers Cloud Run | **fait le 13/10** (recréation 08:33 UTC, coupure ~4 s ; périmètre Leexi testé par le dev) ; 2 jumeaux en réserve | clos |
| GSC : compte de service `mcp-search-console@…` sans droit sur la propriété domaine `sc-domain:hellopro.fr` | ajout du compte sur la propriété domaine si l'équipe en a besoin (propriétaire de la Search Console) | hors migration, à signaler à l'équipe |
| Ringover : `/admin/users` en `502` (VM et Cloud Run, 12/10) — l'API Ringover refuse `FetchAllUsers` | sélecteurs utilisateurs/équipes Ringover de l'admin de la gateway, et périmètre des jetons Ringover, probablement inopérants depuis avant la migration ; cause à lire puis à signaler au dev | hors migration |
| ↳ cause (12/10) | API Ringover `403 insufficient permissions` sur la liste des utilisateurs : droit à ajouter à la clé API côté Ringover (dev / admin Ringover) | hors migration |
| ↳ retour (12/10) | message envoyé au dev ; restriction **probablement intentionnelle** (clé API limitée) → aucune action côté migration | — |
| « RAG Hellopro » : défauts applicatifs vus au test du dev (13/10) — filtres INT64, `hybrid` sans BM25, ID arrondis, `siteweb_2` lent | **F-HP-DEV-013**, correctif DSO après migration + rapport aux devs ; contournements donnés par le dev (filtrer `devis` sur `categorie`, `id` de premier niveau, `semantic` sur `devis`) | hors migration (même code sur la VM) |
| `llm-service` → API DeepSeek hébergée (13/10) | **F-HP-SEC-037** : à qualifier par le RSSI (données personnelles possibles dans les prompts) | hors migration |

## 4. Correctifs DSO après migration (rapport aux devs ensuite)

> **Décision user (14/10)** : les signalements **hors migration** (sécurité, gouvernance, défauts applicatifs, droits d'outils tiers) sont **décidés et traités par le DSO** dans ce lot post-migration, puis rapport à l'équipe ; ils ne bloquent pas la migration.

| Finding | Objet | Statut |
|---|---|---|
| F-HP-DEV-010 | `api-detection-langue-fr` : erreur d'encodage sur surrogates isolés (`language_detector.py:~482`) | 🟡 tracé |
| F-HP-DEV-011 | `api-catalog` : deadlock MySQL 1213 entre scans (`endpoint_repo.go:23`) | 🟡 tracé |
| F-HP-DEV-012 | `api-info` du scan sur rest-milvus ; fuite AMQP d'ingestion ; canal gRPC par appel vers la base (`database_client.py:31`, +1-2 s par recherche) ; logs `INFO` absents de rest-milvus | 🟡 tracé |
| F-HP-MIG-015 | `SERVICE_NAME` Cloud Run ≠ VM → priorité gRPC (corrigé V2-a3 #876) ; **reste : contrôler les consumers GKE** | 🟠 en cours |
| F-HP-SEC-035 | gateway VM « fail-open » : service routé sans politique d'autorisation = public | 🟠 ouvert (inventaire possible avant) |
| F-HP-SEC-036 | mcp-gateway n'écrit plus son journal d'audit (`Field 'event'`) : aucune trace des appels d'outils MCP | 🟠 ouvert |
| F-HP-SEC-031 / 032 / 033 / 034 | `SYNC_TOKEN` en dur (opti-moteur) ; ACL Tailscale ; agent-service sans auth ; hellodata en-têtes non signés | 🟡/🟠 ouverts |
| Compose : `restart: unless-stopped` | rendre durable la correction du 09/10 (un `compose up -d` remet `no`) ; mcp-gateway l'a déjà dans le compose | ⬜ PR à faire |
| **F-HP-SEC-037** | LLM via l'API DeepSeek hébergée (`llm-service`) — **action DSO** : inventaire des flux (services, types de données), puis option retenue avec le RSSI : modèle interne (vLLM sur la VM GPU) ou fournisseur sous contrat UE ; d'ici là, ne pas injecter `echanges` (données personnelles) dans les prompts ; corriger la description « vLLM » de l'outil MCP | 🟠 décidé : post-migration |
| **F-HP-DEV-013** | mcp-api-recherche : filtres INT64 (`UseNumber` / typage), clés inconnues rejetées, `hybrid` seulement avec BM25, ID non arrondis, index de `siteweb_2` | 🟡 décidé : post-migration |
| Semrush (retours du dev, 14/10) | `ERROR 50 :: NOTHING FOUND` → résultat vide « aucun mot-clé payant » ; clarifier la description de `keyword_overview` ; `display_limit` par défaut plus bas (ou avertissement) sur les outils de backlinks (40 unités / ligne) | ⬜ post-migration (amélioration) |
| GSC : propriété domaine `sc-domain:hellopro.fr` | **réglé le 14/10** : l'équipe utilise `https://www.hellopro.fr/` comme `site_url` | ✅ clos, rien à faire |
| Ringover : `/admin/users` `403` (clé API sans droit « utilisateurs ») | probablement voulu ; si les jetons Ringover à périmètre doivent servir, ajouter le droit de lecture des utilisateurs à la clé (`mcp-ringover-api-key` + variable VM) | ⬜ sur besoin |
| F-HP-SEC-035 (sondes de scanners vues le 13/10) | gateway VM « fail-open » : refuser les services inconnus, bloquer `/.env`, `/google-key.json`… | 🟠 décidé : post-migration |
| **F-HP-SEC-035 (cas aggravé, 15/10)** | graphadmin (Cypher brut Neo4j) et graphdlq ouverts sans jeton depuis Internet → **correctif nginx posé le 15/10 08:18 UTC** (IP Hellopro seulement, vérifié, Ecritel OK) ; reste politique par route + fail-closed ; règle de pare-feu 80 / 443 ouverte au monde sur tout le VPC à cibler | 🟢 exposition Internet fermée · 🟠 fond post-migration |
| **F-HP-SEC-032 (confirmé 15/10)** | ACL du tailnet ouvertes : la VM accepte SSH, MySQL 3307, Neo4j, 8500, 8520, 8527, 8597, 9200… depuis le tailnet (8 pairs, dont `vps-monitoring` à identifier) → flux à garder : VM → VPS:8797 (`qualif-lecture`) ; pairs tous légitimes ; ACL cible : `autogroup:member` → `autogroup:self:*` + `tag:gateway` → VPS:8797, rien vers la VM (après `tailnet_observe.sh report`) ; console : accès user | 🟠 **décidé : post-migration (15/10)**, en tête des correctifs |
| Shadows GKE inactifs (V2-c option B, 15/10) | 7 shadows hors lot : 400m CPU / 704 Mi réservés, nœuds limités par la mémoire (89-96 %) → réduction à 0 sans gain financier ; à faire en hygiène (`kubectl scale --replicas=0`, réversible) ; FinOps réel = mémoire réservée du cluster | ⬜ post-migration |
