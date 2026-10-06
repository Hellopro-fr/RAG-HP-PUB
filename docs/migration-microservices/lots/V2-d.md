# Lot V2-d — SSO et fronts publics

> **Vague 2 · lot 6/6** · risque **Moyen** · semaine du 12/10, après V2-c, selon décisions.
> Procédure commune : [`../procedure-bascule-route-http.md`](../procedure-bascule-route-http.md) (aiguillage = vhost nginx de la VM) · plan : [`../plan-vague-2.md`](../plan-vague-2.md) § 3 V2-d et § 1bis · suivi : [`../suivi-vague-2.md`](../suivi-vague-2.md).
> Priorités **P6, P7, P8** de l'[inventaire](../inventaire-services-migration-par-lot.md).

## Composition

| Service (nom `docker-compose`) | Cible | Adresse publique | Aiguillage (décision 10) | Préalable |
|---|---|---|---|---|
| `account-service-backend` | Cloud Run `account-service-backend` (sortie `all-traffic`) | — (porte le SSO) | URL côté appelants | après V2-c (partage `gateway_db`) |
| `account-service-frontend` | Cloud Run `account-service-frontend` | `login.hellopro.eu` | vhost nginx VM → Cloud Run | backend basculé ; clients OAuth (devs SSO) |
| `api-html-recherche-service` | Cloud Run `api-html-recherche` | `rag.hellopro.eu` | vhost nginx VM → Cloud Run | test de connexion par un dev |
| `nextjs-conseils-hp` | Cloud Run `nextjs-conseils-hp` | `nextjs-conseils.hellopro.eu` (derrière `conseils.hellopro.fr`) | vhost nginx VM → Cloud Run | décision 2 : **contenus identiques** VM / Cloud Run vérifiés avant |
| `crawler-monitor-backend` | Cloud Run `crawler-monitor-backend` | (via le front) | à qualifier | front migré |
| `redis-client-frontend`, `crawler-monitor-frontend`, `mcp-gateway-frontend` | **à créer** (build depuis la racine, lib `@hellopro/auth`) | `cmf.hellopro.eu`, front de `mcp.` | vhost nginx VM | fronts construits et testés par les devs |

**Hors lot** : `formulaire.hellopro.eu` (décision 3 : hors vague 2). Le DNS Gandi ne change qu'**une fois**, à la fin de la vague, par le titulaire du compte (décision 10).

## Ce qui bascule dans ce lot

- Les entrées publiques `login.`, `rag.`, `nextjs-conseils.`, `cmf.` : le nginx de la VM envoie vers Cloud Run (entrée interne : la VM est vue comme interne, internet reste fermé sur `run.app`).
- **Limite transitoire** : tant que le DNS pointe la VM, le public passe par le nginx de la VM, pas par le load balancer — Cloud Armor (décision 6) ne s'appliquera qu'à la bascule DNS finale.

## À savoir, service par service

| Service | Vigilance |
|---|---|
| `account-service-backend` | Porte le SSO ; partage `gateway_db`. Appelle `mcp-gateway-service` (repointé en V2-c). Appelé par `redis-client-frontend` tant qu'il n'est pas migré. |
| `account-service-frontend` | Clients OAuth et URL de retour à enregistrer ; `SESSION_SECRET`, `JWT_SECRET`, `ACCOUNT_*`, `ADMIN_EMAILS` : la lib refuse de démarrer si l'environnement est incomplet. |
| `api-html-recherche` | Déjà sur Cloud Run ; seule l'entrée publique bascule. |
| `nextjs-conseils-hp` | Remplace progressivement des pages PHP : les URL non migrées doivent continuer de répondre. Commit `poc` seul du 18/09 → rapatriement. Ecritel transmet `conseils.hellopro.fr` vers le **nom** `nextjs-conseils.hellopro.eu` (rien à changer chez eux si c'est bien un nom). |
| fronts SSO à créer | Build depuis la racine du dépôt (lib `@hellopro/auth`) ; commits `poc` seuls (`mcp-gateway-frontend` 30/09, `crawler-monitor-*` 28/08). |

## Prérequis spécifiques au lot

- V2-c validé (gateway et `gateway_db` sur la nouvelle base de fonctionnement).
- Script de bascule nginx (0.22) éprouvé en V2-c.
- Comparaison de contenu VM / Cloud Run pour `conseils` (décision 2).
- Clients OAuth enregistrés (devs SSO) ; réponse Ecritel sur la règle `conseils`.

## Ce qu'on attend des devs concernés

| Adresse | Dev testeur | Parcours |
|---|---|---|
| `login.` | ⬜ dev SSO | connexion, déconnexion, connexion d'un front client |
| `rag.` | ⬜ | connexion et recherche réelle |
| `conseils` | ⬜ PROD | pages migrées et non migrées, contenu identique |
| `cmf.`, front `mcp.` | ⬜ | parcours de chaque front |

## Feuille de lot

| Étape | Heure | Résultat | Par |
|---|---|---|---|
| P0 par service (code, variables, OAuth, contenu `conseils`) | | | DSO · devs |
| d.1 `account-service-backend` | | | DSO |
| d.2 `login.hellopro.eu` | | | DSO · dev SSO |
| d.3 `rag.hellopro.eu` | | | DSO · dev |
| d.4 `cmf.hellopro.eu`, front `mcp.` | | | devs · DSO |
| d.6 `nextjs-conseils.hellopro.eu` | | | PROD · DSO |
| Relevé 17h / nuit | | | DSO |
| **Décision J+1 9h30** (par adresse) | | | LEAD · DSO |
