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

## Feuille de lot

| Étape | Heure | Résultat | Par |
|---|---|---|---|
| P0 — code, variables, clés tierces, sortie IP (×8) | | | DSO |
| P0 — script `mcp_servers` prêt et relu | | | DSO |
| Dump `mcp_servers` | | | DSO |
| **mcp-api-recherche** — plan / apply / check / test | | | DSO · dev |
| **mcp-classification-produit** — idem | | | DSO · dev |
| **mcp-google-analytics** — idem | | | DSO · dev |
| **mcp-google-analytics-minisite** — idem | | | DSO · dev |
| **mcp-google-search-console** — idem | | | DSO · dev |
| **mcp-semrush** — idem | | | DSO · dev |
| **mcp-ringover** — idem | | | DSO · dev |
| **mcp-leexi** — idem | | | DSO · dev |
| Relevé 17h / nuit | | | DSO |
| **Décision J+1 9h30** (par serveur) | | | LEAD · DSO |
