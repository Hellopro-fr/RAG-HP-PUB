# Procédure de bascule d'une route HTTP — vague 2

> **Exécutée par le DevSecOps**, avec le dev testeur du service. Les développeurs n'ont **aucune** commande à lancer :
> ce document dit ce qui se passe, dans quel ordre, et quand leur tour arrive.
>
> C'est l'équivalent, pour les **services HTTP**, de [`procedure-bascule-un-lot.md`](procedure-bascule-un-lot.md)
> (consumers, vague 1). Elle s'applique aux lots **V2-a1, V2-a2, V2-a3** (routes de la gateway) et, avec l'aiguillage
> propre à chacun, à **V2-b** (lignes `mcp_servers`), **V2-c** et **V2-d** (vhosts nginx de la VM) : voir la fiche du lot.
> Plan : [`plan-vague-2.md`](plan-vague-2.md) · suivi : [`suivi-vague-2.md`](suivi-vague-2.md) · fiches : [`lots/`](lots/).
>
> Les cartes d'exécution exactes (quoi, quand, où, impact, repli, log) sont produites au moment de chaque route, à
> partir de la fiche `lots/V2-<x>.md`. Aucun secret n'apparaît ici. Scripts :
> `RAG-HP-PUB-infra/infra-microservices/scripts/migration/vague2/` (README du dossier `migration/`).

---

## Ce qui change par rapport à la vague 1

| | Vague 1 (consumers) | Vague 2 (HTTP) |
|---|---|---|
| Ce qu'on bascule | l'abonnement à une file RabbitMQ | **une adresse** : la ligne `SERVICE_<X>` de `.env.url`, une ligne `mcp_servers`, ou la destination d'un vhost nginx |
| Le jumeau VM | **arrêté avant** de repointer GKE (deux jumeaux se partageraient la file) | **reste UP** : un service HTTP sans état ne reçoit que ce qu'on lui envoie ; c'est le repli le plus rapide |
| Rollback | `scale 0` GKE, `docker start` VM, secrets remis en dev (~2 min) | **remettre la ligne** puis `rescan` (effet en quelques secondes) — sans `rescan`, au prochain scan du catalogue (≤ 15 min) |
| Preuve | consumers > 0, la file draine | codes HTTP de la route dans les logs de la gateway, requêtes reçues par Cloud Run, test du dev |
| Unité | un lot de 2 à 9 consumers en une fenêtre | **une route à la fois**, ~2 h entre deux routes, un lot sur une ou deux journées |

Exception : les services qui **écrivent seuls** au démarrage ou en boucle (`api-gateway-go`, `mcp-gateway-service`) —
leur jumeau VM est arrêté dans le même geste (fiche V2-c).

## Les trois invariants

**Le code qui sert la prod ne change pas en basculant.** Avant toute route : le code du conteneur VM = l'image Cloud Run
(`p0_code.sh`). Si la VM fait tourner un correctif parti par `features/poc`, il est d'abord rapatrié dans `prod` par le
DSO (plan § 7quater), puis le CD redéploie. Après la bascule, les correctifs du service vont dans `prod`.

**Une seule ligne modifiée, en place.** `.env.url` est monté en lecture seule dans `api-catalog` : un `sed -i` crée un
nouveau fichier (nouvel inode) que le conteneur ne voit pas. `bascule_route.sh` réécrit le fichier **en place**, vérifie
que l'inode n'a pas changé et que **2 lignes** exactement diffèrent de la sauvegarde.

**La gateway ne voit pas la modification tout de suite** (constat du 05/10, code d'`api-catalog`) : le catalogue surveille le
*dossier* `/app`, mais `.env.url` y est monté **seul** ; une écriture sur l'hôte ne lui parvient pas. Il ne relit le
fichier qu'à son **scan périodique** (`SCAN_INTERVAL: 15m`), puis la gateway reprend la table en ≤ 5 s. Pour un effet
immédiat — bascule comme rollback — mode **`rescan`** : `docker restart` d'`api-catalog`, scan complet au démarrage ;
pendant les quelques secondes du redémarrage, la gateway **garde sa dernière table de routes**
(`api-gateway-go/internal/catalog/refresher.go`).

**Un jumeau VM n'est arrêté que lorsque plus rien sur la VM ne l'appelle** (règle du 01/10, plan § 7bis). La gateway
n'est pas toujours le seul appelant : `crawler-service` appelle directement détection de langue et content-extractor,
`mcp-classification-produit` appelle la classification.

---

## Vue d'ensemble

| Étape | Quoi | Où | Durée | Niveau |
|:--:|---|---|:--:|:--:|
| **P0** | La veille : parité de code et de variables, rapatriement, réglages cible du Cloud Run, appelants VM, dev testeur | Poste · GitHub | 1-2 h par service | 🟢 (🟠 si PR) |
| **P1** | Pré-flight : ligne actuelle, inode, santé de la cible depuis la VM, trafic de référence | Poste → VM | 5 min | 🟢 |
| **P2** | **Bascule de la route** (`apply` puis `rescan`) | Poste → VM | 2 min | 🔴 PROD |
| **P3** | Contrôle à 5 et 15 min : codes HTTP de la route, requêtes reçues par Cloud Run | Poste → VM | 15 min | 🟢 |
| **P4** | Test du parcours réel par le dev, OK écrit | dev | 15 min | — |
| **P5** | Relevés midi / 17h / nuit | Poste | — | 🟢 |
| **P6** | Décision J+1 9h30 : GO / prolonger / rollback | DSO · LEAD | — | — |
| **P7** | Clôture : rapport du service, suivi, sort du jumeau VM | DSO | 30 min | 🟢 (🟠 réserve) |
| **R** | **Rollback de la route** (`revert`) | Poste → VM | ≤ 1 min | 🔴 PROD |

Tous les scripts se lancent du **poste (Git Bash)** ; ceux qui touchent la VM passent par `gcloud compute ssh` (config
`default`, remise sur `kubectl-local` en sortie). **Chaque sortie va dans un `.log`** de
`Docs/DevSecOps/TICKETS/001-MIGRATION-ARCHI/data/cutover/` : le DSO lit le log et consigne le constat.

---

## P0 — La veille

| | |
|---|---|
| **Quoi** | Tout ce qui ne dépend pas de l'heure de bascule |
| **Pourquoi** | Le jour J ne contient que des gestes préparés. Un écart de code ou une variable manquante se corrige la veille ; découvert après `apply`, il se rollbacke |
| **Où** | Poste (`gcloud` config `default`) · GitHub (PR vers `prod`) |

1. **Fiche du lot relue** : composition, route, cible, vigilances.
2. **Routes et parité des variables** : `p0_route.sh <compose>:<cloudrun>` — ligne `.env.url`, mode catalogue de la
   gateway, trafic 7 jours, réplicas VM, réglages Cloud Run, **variables comparées par empreinte** (une instance de
   données dev en shadow apparaît ici comme `DIFFERENT (valeur)`).
3. **Parité de code** : `p0_code.sh <compose>:<cloudrun>:<dossier>` — code du conteneur VM vs image Cloud Run vs `prod`
   vs `features/poc`, bibliothèques comprises. Écart → `p0_diff.sh` pour l'origine.
4. **Rapatriement** si la VM fait tourner du code absent de `prod` : PR du DSO, code fonctionnel seulement (on garde les
   `requirements.txt` épinglés et les Dockerfile de `prod`). Gate verte, merge, CD.
5. **Réglages cible du wrapper CD** (même PR ou PR dédiée) : entrée `internal-and-cloud-load-balancing`, appel anonyme
   (`allow_unauthenticated: true`), `min_instances: 1`, connecteur VPC `private-ranges-only` si le service joint une base
   interne, variables manquantes, capacité calée sur la VM. Sortie en IP fixe (`all-traffic`, NAT `35.233.35.8`)
   **seulement** si un tiers filtre par IP.
6. **Après le déploiement** : `v2a_verif_deploy.sh` — entrée interne, `min=1`, internet **404**, VM **200**, clients
   Redis si utilisé. Puis `audit_cloud_run.sh` : le CD ne doit pas avoir rouvert un autre service.
7. **Appelants restés sur la VM** (compose, `.env.url`, `mcp_servers`, défauts du code) : ils gardent le jumeau UP.
8. **Dev testeur nommé** et parcours de test décrit dans la fiche ; message J-1.
9. **Suivi** : ligne du service `⬜` → `🟡 prêt`.

## P1 — Pré-flight (J, avant chaque route)

```bash
cd RAG-HP-PUB-infra/infra-microservices/scripts/migration/vague2
HEALTH_PATH=<chemin de santé> bash bascule_route.sh SERVICE_<X> plan https://<cloudrun>-xqksdwdiga-ew.a.run.app
SINCE=60m bash bascule_route.sh SERVICE_<X> check          # trafic de référence de la route, côté VM
```

**Critère** : la ligne `SERVICE_<X>` existe **une seule fois** (sinon le script s'arrête), l'inode est noté, la santé de
la cible depuis la VM est **`200`**. Le trafic de référence sert de comparaison en P3.

## P2 — Bascule de la route

```bash
bash bascule_route.sh SERVICE_<X> apply https://<cloudrun>-xqksdwdiga-ew.a.run.app
```

Le script sauvegarde `.env.url.bak-<date-heure>` à côté du fichier, remplace la seule ligne `SERVICE_<X>`, relit.
Le fichier est modifié, **mais la route n'a pas encore changé** : le script affiche l'heure du prochain scan du catalogue.

```bash
bash bascule_route.sh SERVICE_<X> rescan                   # effet immédiat : redémarrage d'api-catalog, scan de démarrage
```

**Critère** : `inode N -> N (inchange, OK)`, `lignes modifiees : 2`, puis `scan de demarrage : … scan boot …`.
**Sinon `revert` immédiat.** Sans `rescan`, la route bascule au prochain scan (≤ 15 min) : tester **après** ce scan.

## P3 — Contrôle à 5 puis 15 minutes

```bash
SINCE=15m bash bascule_route.sh SERVICE_<X> check          # scans du catalogue + codes HTTP de la route (gateway)
bash cr_requetes.sh 1                                      # requêtes reçues par le Cloud Run (métrique request_count)
```

**Preuve de destination** (indispensable sur une route peu appelée) : un `GET` de santé à travers la gateway
(`curl -s -i http://127.0.0.1:8500/<route>/<santé>` sur la VM), et **aucune** trace de ce `GET` dans les logs du jumeau
VM au même instant. Si le jumeau le reçoit, la gateway sert encore la VM : le scan n'est pas passé (`rescan`).

**Critère** : des `2xx` sur la route, **aucun code nouveau** par rapport au trafic de référence (surtout `502`, `503`,
`504`) ; le Cloud Run reçoit des requêtes. Route peu appelée : pas de trafic en 15 min n'est pas un échec, c'est le test du
dev (P4) qui tranche.

**Rollback immédiat** si : rafale de `5xx` sur la route, `502/504` répétés (cible injoignable), ou le dev voit une
régression. On analyse **après** avoir remis la ligne, pas avant.

## P4 — Test du parcours réel

Le dev testeur joue le parcours décrit dans la fiche (l'écran, l'API ou le traitement qui appelle cette route) et écrit
**OK** ou **KO** dans le canal de bascule. Pendant ce temps, le DSO relance `check` pour voir ses appels passer.

## P5 — Relevés

À midi, 17h et le lendemain 9h : `check` avec `SINCE` couvrant la période, `cr_requetes.sh 1`. On compare le volume et
les codes à la référence VM des jours précédents (`p0_route.sh`, trafic 7 jours). Côté Cloud Run, le journal des
requêtes et la sortie de l'application sont collectés (aucune exclusion FinOps) : `gcloud run services logs read <service>`
— la preuve de destination s'y lit aussi. ⚠️ `gcloud logging read` lancé depuis Git Bash est mal transmis par `gcloud.cmd`
(0 ligne) : console ou Cloud Shell pour les filtres avancés. Guide des devs : [`acces-logs-services-migres.md`](acces-logs-services-migres.md), section Vague 2.

## P6 — Décision J+1 9h30

DSO + LEAD : **GO** (route validée), **prolonger** l'observation, ou **rollback**. Consigné dans le suivi.

## P7 — Clôture du service

1. **Rapport** `rapports/<service>.md` (modèle `_TEMPLATE.md`, variante Cloud Run) : avant / après, preuves, accès aux
   logs, rollback.
2. **Suivi** : ligne du service — basculé le, validé DSO, validé dev, observation 24 h ; tableau des routes à jour.
3. **Jumeau VM** : il reste UP tant qu'un service resté sur la VM l'appelle. Quand plus rien ne l'appelle (logs du
   conteneur sur 24 h) : `vm_reserve.sh <conteneur> check` puis `apply` (`docker stop`, jamais `rm` ; décision 4).
4. À partir de là, **ses correctifs passent par `prod`**, plus par `features/poc`.

## R — Rollback de la route

```bash
bash bascule_route.sh SERVICE_<X> revert                   # remet la ligne depuis la DERNIÈRE sauvegarde, en place
bash bascule_route.sh SERVICE_<X> rescan                   # effet immédiat (sinon prochain scan, ≤ 15 min)
SINCE=5m bash bascule_route.sh SERVICE_<X> check
```

**Durée** : ~1 min avec `rescan` (≤ 15 min sans). Le jumeau VM n'a jamais été arrêté : il reprend le trafic sans démarrage.
**Critère** : la ligne d'origine est revenue, l'inode est inchangé, les appels repartent en `2xx` vers la VM.
**Décision** : DSO, LEAD informé, consigné dans le suivi (section Rollbacks). Après un rollback : analyse écrite avant de
rejouer la route ; deux rollbacks dans la vague → pause et point CTO / LEAD / DSO.

---

## Ce que le développeur voit passer

La veille, un message avec l'heure de bascule de son service et le parcours à tester. Le jour J, juste après la bascule
(~5 min), on lui demande de jouer ce parcours et d'écrire OK / KO. Le lendemain 9h30, la décision. **C'est tout** :
aucune commande, aucun accès à l'infrastructure, aucune modification de code pendant la fenêtre. Après la bascule, ses
correctifs pour ce service partent dans `prod` (PR, gate, CD), plus par `features/poc`.
