# Lot V2-b — Serveurs MCP (lignes `mcp_servers`)

> **Vague 2 · lot 4/6** · risque **Moyen** · date proposée **après V2-a3** (`mcp-api-recherche` s'appuie sur `api-recherche`).
> Procédure commune : [`../procedure-bascule-route-http.md`](../procedure-bascule-route-http.md) (aiguillage propre à ce lot ci-dessous) · plan : [`../plan-vague-2.md`](../plan-vague-2.md) § 3 V2-b · suivi : [`../suivi-vague-2.md`](../suivi-vague-2.md).
> Priorité **P5** de l'[inventaire](../inventaire-services-migration-par-lot.md).

## Composition

| Service (nom `docker-compose`) | Cloud Run (nom exact) | Aiguillage | Santé |
|---|---|---|---|
| `mcp-api-recherche-service` | `mcp-api-recherche-service` | ligne `mcp_servers` (`gateway_db`) | P0 |
| `mcp-classification-produit-service` | `mcp-classification-produit-service` | ligne `mcp_servers` | P0 |
| `mcp-google-analytics-service` | `mcp-google-analytics-service` | ligne `mcp_servers` | P0 |
| `mcp-google-analytics-minisite-service` | `mcp-google-analytics-minisite-service` | ligne `mcp_servers` | P0 |
| `mcp-google-search-console-service` | `mcp-google-search-console-service` | ligne `mcp_servers` | P0 |
| `mcp-semrush-service` | `mcp-semrush-service` | ligne `mcp_servers` | `/status` |
| `mcp-ringover-service` | `mcp-ringover-service` | ligne `mcp_servers` | P0 |
| `mcp-leexi-service` | `mcp-leexi-service` | ligne `mcp_servers` | P0 |

**8 serveurs · 8 jumeaux VM laissés UP.** `mcp-neo4j-service` **reste sur la VM** (F-HP-SEC-020, CVE non corrigeable).

## Ce qui bascule dans ce lot

- L'URL de chaque serveur MCP **stockée en base** (`gateway_db.mcp_servers`, MySQL de la VM) : nom Docker → URL Cloud Run. `mcp-gateway-service` (VM) appelle ensuite Cloud Run (chemin VM → Cloud Run validé le 02/10).
- Aiguillage différent de V2-a : **une ligne de base de données**, pas une ligne de fichier. Dump de la table avant, une ligne à la fois, relecture.

## À savoir, service par service

| Service | Vigilance |
|---|---|
| `mcp-api-recherche` | Appelle `api-recherche` : à faire **après** la bascule de `SERVICE_SEARCH` (V2-a3), ou en vérifiant qu'il vise déjà l'URL Cloud Run. |
| `mcp-classification-produit` | Go. Appelle `api-classification` : une fois basculé et repointé, le jumeau VM de la classification peut partir en réserve (plan § 7bis). |
| `mcp-google-*` (×3) | Clé de compte de service montée en fichier : parité par empreinte. |
| `mcp-semrush` | Node 22 + Python via `mcp-proxy`, santé sur `/status`. **Commit `poc` seul du 02/09** → P0 de code et rapatriement éventuel. |
| `mcp-ringover`, `mcp-leexi` | API tierces : clés en Secret Manager, quotas. |
| Tous | Si un tiers filtre par IP : sortie `all-traffic` (NAT `35.233.35.8`) — en `private-ranges-only`, l'IP de sortie vers internet n'est pas fixe. |

## Prérequis spécifiques au lot

- **Aiguillage = API / interface d'administration de la gateway MCP, PAS de SQL** (constat du 07/10 dans le code) : `mcp-gateway-service` garde les serveurs **en mémoire** ; seul `PUT /api/v1/servers/{id}` (droits admin, `internal/api/handler.go:608-610`) relance la découverte du serveur (`internal/api/server_handlers.go:116-121`). Un `UPDATE` direct de `mcp_servers` ne serait pas vu avant un redémarrage ou un `discover-all`. Contrôle SSRF côté gateway : une URL `run.app` (publique) passe.
- **Script `bascule_mcp.sh <nom> plan|backup|check [url]`** (07/10) : `plan` = ligne `mcp_servers` (url, transport, santé, dernière vérification, erreur, nombre d'outils) + joignabilité de la cible ; `backup` = copie de la ligne (fichier 600, en-têtes d'authentification chiffrés) **avant** le changement ; `check` = même lecture après (santé mise à jour toutes les 30 s). Le changement d'URL lui-même se fait par l'interface ou l'API d'administration ; retour arrière = remettre l'ancienne URL de la même façon.
- Dump daté de `mcp_servers` le matin du lot, conservé.
- P0 de chaque serveur (code, variables, clés tierces, sortie IP), wrappers au réglage cible.
- V2-a3 validé (pour `mcp-api-recherche`).

## Ce qu'on attend des devs concernés

| Serveur | Dev testeur | Parcours à jouer après la bascule |
|---|---|---|
| chacun des 8 | ⬜ dev MCP | un appel d'outil MCP réel depuis un client (gateway MCP), résultat attendu connu |

## Inventaire réel de `mcp_servers` (07/10, `bascule_mcp.sh inventaire plan`)

| Serveur MCP (nom en base) | URL en base | Lot |
|---|---|---|
| RAG Hellopro | `http://mcp-api-recherche-service:8582` | V2-b |
| Classification Produit | `http://mcp-classification-produit-service:8593` | V2-b |
| Google Analytics | `http://mcp-google-analytics-service:8583` | V2-b |
| Google Analytics Minisite | `http://mcp-google-analytics-minisite-service:8594` | V2-b |
| Google Search Console | `http://mcp-google-search-console-service:8584` | V2-b |
| Semrush | `http://mcp-semrush-service:8588` | V2-b |
| Ringover | `http://mcp-ringover-service:8586` | V2-b |
| Leexi | `http://mcp-leexi-service:8589` | V2-b |
| Zoho | `http://mcp-zoho-service:8596` | V2-c (bloc gateway) |
| Neo4j | `http://mcp-neo4j-service:8587` | reste sur la VM (F-HP-SEC-020) |
| **Hellodata** | `http://mcp-hellodata-service:8597/mcp` | ⚠️ **nouveau, hors inventaire** — à qualifier avec son dev (migrer ou rester sur la VM, décision 4) |
| **Normalisation Numérique** | `http://mcp-normalize-unite-service:8602/mcp` | ⚠️ **nouveau, hors inventaire** — idem |
| Data Gouvernement Fr, Hellopro BDD, Zoho CRM | URL externes | rien à migrer |

⚠️ L'URL de Zoho CRM porte une clé d'accès dans son chemin : toute copie de la table `mcp_servers` est **sensible** (ne pas la coller dans un ticket ou un canal).

## Consigne au dev responsable de mcp-gateway (changement d'URL d'un serveur) — prête à envoyer

> Bonjour,
>
> Pour la migration des serveurs MCP vers Cloud Run (lot V2-b), on a besoin de toi pour le **changement d'URL**, serveur par
> serveur, dans l'**interface admin de mcp-gateway** (ou `PUT /api/v1/servers/{id}` avec un compte admin). **Pas en SQL** :
> le registre de la gateway est en mémoire, seul l'admin relance la découverte (`internal/api/server_handlers.go:116-121`).
>
> **Premier serveur (pilote) : « Classification Produit »** (id `ac5588e1-4332-40af-ab31-d6ddabbb19c3`).
>
> | Champ | Valeur actuelle | Nouvelle valeur |
> |---|---|---|
> | URL | `http://mcp-classification-produit-service:8593` | `https://mcp-classification-produit-service-xqksdwdiga-ew.a.run.app` |
> | URL des messages (si le champ existe) | `http://mcp-classification-produit-service:8593/mcp` | `https://mcp-classification-produit-service-xqksdwdiga-ew.a.run.app/mcp` |
>
> Ne change rien d'autre (transport `streamable-http`, en-têtes, rôle minimum, actif).
>
> **Quand** : à un moment convenu avec nous (on surveille pendant 30 min). **Après l'enregistrement** : dis-nous l'heure exacte ;
> on vérifie que le serveur reste `healthy` avec ses 4 outils, et que les appels d'outils partent vers Cloud Run.
>
> **Retour arrière** (si on te le demande) : remettre les deux valeurs « actuelles » ci-dessus dans le même écran.
> Une sauvegarde de la ligne existe côté DSO.
>
> Les serveurs suivants (leexi, ringover, GA, search-console, api-recherche, semrush) suivront le même schéma, un par un, après validation du pilote.

## Feuille de lot

> **Méthode par serveur (09/10)** : P0 en une carte (`p0_route.sh` parité des variables, `cred_fichier_parite.sh` si fichier d'identifiants, `drift_lot.sh`, **dépendances aval** lues dans le wrapper et le code, `bascule_mcp.sh plan` + `backup`) → consigne au dev (changement d'URL + **test d'un outil en lecture**) → `check` (même nombre d'outils, sinon `mcp_outils.sh`) → `mcp_releve.sh` à 30 min → GO. Seuil : 1 appel d'outil en erreur, `unhealthy` persistant ou outil manquant.

| Étape | Heure | Résultat | Par |
|---|---|---|---|
| P0 — code, variables, clés tierces, sortie IP (×8) | | | DSO |
| P0 — script `mcp_servers` prêt et relu | | | DSO |
| Dump `mcp_servers` | | | DSO |
| **mcp-api-recherche** — plan / apply / check / test | | | DSO · dev |
| **mcp-classification-produit** — idem | 09/10 08:30 → 08:54 UTC | ❌ **retour arrière** : `404` sur `classify_products_batch` (appelle api-classification Cloud Run en entrée interne, sans VPC ; api-classification revenue sur la VM) → **rattaché à V2-a3-bis** | DSO · dev |
| **mcp-google-analytics** — idem | 09/10 ~14:00 UTC | ✅ **GO** : test OK, 9 outils (7 de la VM + 2 nouveaux, `analytics-mcp==0.6.0`), 207 × 200 ; 2 × 404 au changement et 1 flux coupé à 300 s à surveiller | DSO · dev |
| **mcp-google-analytics-minisite** — idem | | | DSO · dev |
| **mcp-google-search-console** — idem | | | DSO · dev |
| **mcp-semrush** — idem | | | DSO · dev |
| **mcp-ringover** — idem | 09/10 ~12:23 UTC | ✅ **GO** : test OK, 319 × 200, 0 avertissement, jumeau VM à 0 | DSO · dev |
| **mcp-leexi** — idem | 09/10 11:15 UTC | ✅ **GO** : test OK, 12 appels d'outils, 249 × 200, 0 avertissement, jumeau VM à 0 | DSO · dev |
| Relevé 17h / nuit | | | DSO |
| **Décision J+1 9h30** (par serveur) | | | LEAD · DSO |
