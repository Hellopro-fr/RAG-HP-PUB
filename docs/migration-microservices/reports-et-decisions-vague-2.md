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

## 3. Surveillances et preuves en attente

| Sujet | Seuil / attendu | Prochaine lecture |
|---|---|---|
| Rafale d'embedding de 21h (V2-a2) | VM 8-12 % de `503` ; Cloud Run 17 % (07/10), 15,8 % (08/10) ; **seuil 20 %** | relevé de nuit suivant |
| Repointage du crawler | jumeaux VM detection/extractor à 0 **et** Cloud Run qui reçoit les appels du crawl | premier crawl (aucun depuis le 07/10) |
| **Maintenance GCE de la VM GPU** (12/10 20:00 → 13/10 00:00 UTC, arrêt + redémarrage) | état identique à la référence ; 62 conteneurs passés `no` → `unless-stopped` (09/10) | `vm_etat.sh snapshot` lundi 18h, `vm_etat.sh compare` mardi matin ; GPU + réservation L4 |
| MCP basculés (leexi, ringover, Google Analytics) | usage réel sur Cloud Run (leexi 2-114 appels/j, ringover 4-242/j), 0 erreur ; jumeaux VM à 0 | relevé J+1 lundi 12/10, puis mise en réserve des jumeaux (`vm_reserve.sh`) |
| Google Analytics : 2 × `404` au changement d'URL, 1 flux coupé à 300 s | ne doit pas se répéter en régime établi | relevé lundi 12/10 |

## 4. Correctifs DSO après migration (rapport aux devs ensuite)

| Finding | Objet | Statut |
|---|---|---|
| F-HP-DEV-010 | `api-detection-langue-fr` : erreur d'encodage sur surrogates isolés (`language_detector.py:~482`) | 🟡 tracé |
| F-HP-DEV-011 | `api-catalog` : deadlock MySQL 1213 entre scans (`endpoint_repo.go:23`) | 🟡 tracé |
| F-HP-DEV-012 | `api-info` du scan sur rest-milvus ; fuite AMQP d'ingestion ; canal gRPC par appel vers la base (`database_client.py:31`, +1-2 s par recherche) ; logs `INFO` absents de rest-milvus | 🟡 tracé |
| F-HP-MIG-015 | `SERVICE_NAME` Cloud Run ≠ VM → priorité gRPC (corrigé V2-a3 #876) ; **reste : contrôler les consumers GKE** | 🟠 en cours |
| F-HP-SEC-035 | gateway VM « fail-open » : service routé sans politique d'autorisation = public | 🟠 ouvert (inventaire possible avant) |
| F-HP-SEC-036 | mcp-gateway n'écrit plus son journal d'audit (`Field 'event'`) : aucune trace des appels d'outils MCP | 🟠 ouvert |
| F-HP-SEC-031 / 032 / 033 / 034 | `SYNC_TOKEN` en dur (opti-moteur) ; ACL Tailscale ; agent-service sans auth ; hellodata en-têtes non signés | 🟡/🟠 ouverts |
| Compose : `restart: unless-stopped` | rendre durable la correction du 09/10 (un `compose up -d` remet `no`) | ⬜ PR à faire |
