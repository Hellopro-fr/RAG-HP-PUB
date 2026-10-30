# Décision : retour de la recherche (`api-recherche`) sur la VM — 15/10/2026

> **Décision** : la route `/search-service` repasse de Cloud Run à la VM le **15/10/2026 à 05:43 UTC** (08:43 heure locale, UTC+3).
> **Pris par** : DevSecOps, sur le seuil de retour arrière fixé avant la bascule (taux d'erreur de nuit supérieur à 15 %).
> **Réversible** : oui, en une commande (`bascule_route.sh SERVICE_SEARCH apply …`). Le service Cloud Run reste déployé.
> **Suite** : la recherche rejoint le lot reporté **V2-a3-bis**, avec les conditions de reprise listées en fin de document.

## En bref

De jour, la recherche marche **mieux sur Cloud Run que sur la VM** : 0,4 % d'erreurs, contre 7,7 % sur la VM.

La nuit, un client envoie en boucle quelques grosses requêtes (environ 20 Ko) qui **ne se terminent jamais**. La VM les laissait tourner sans limite, sur 8 workers et 24 vCPU, sans gêner les autres appels. Sur Cloud Run, chaque instance n'a que 2 workers et 1 vCPU. Ces requêtes y sont coupées par le délai maximal (300 s, puis 900 s), et elles **bloquent la capacité** pendant ce temps. Résultat : **56 % d'erreurs** entre 20h et 00h UTC dans la nuit du 14 au 15/10.

Agrandir Cloud Run coûterait plus cher en permanence, pour un traitement de nuit qu'on ne connaît pas encore. Le retour sur la VM rétablit le service tout de suite, sans coût supplémentaire. On reprendra la migration une fois ce client et ses requêtes identifiés.

## Chronologie

| Date (UTC) | Événement | Preuve |
|---|---|---|
| 08/10 | Bascule de `/search-service` vers Cloud Run (lot V2-a3). Référence VM sur 24 h : 3 273 × 200 / 274 × `503`, soit **7,7 %** | `suivi-vague-2.md` (08/10 09:00) |
| 08 → 09/10 (nuit) | Cloud Run : 3 042 × 200 / 95 × `503` (**3,0 %**) / 3 × `504`. GO à J+1 | `v2a-releve-1009-0901.log` |
| 12/10 20:00 → 13/10 00:00 | Maintenance GCE de la VM (arrêt et redémarrage) : pics d'erreurs attendus | `vm-etat-compare-1013-0857.log` |
| 13 → 14/10 (nuit) | Jour : 0,4 %. **Nuit (20h-04h) : 82 erreurs sur 208 (39 %)**. Des `504` arrivent **toutes les 5 minutes**, et le même motif existait déjà la nuit précédente | `gw-fenetre-search-service-1014-0939.log`, `v2a-diag-503-search-service-1014-0943.log` |
| 14/10 | Diagnostic : **54 × `504`, tous à 300,00 s**, le délai par défaut de Cloud Run. Corps de 19,6 à 20,2 Ko, en 4 ou 5 tailles qui reviennent (un même lot relancé en boucle). Un seul appelant, `172.20.0.1` (passerelle Docker de la VM). Sur la VM, la gateway n'impose **aucun délai** à `search-service` | `vague2_carte_fv.log`, `api-gateway-go/internal/config/service_map.go:28-33` |
| 14/10 | Correctif tenté : délai Cloud Run porté à **900 s** (PR #887, révision `api-recherche-00010-vpb`) | PR #887 |
| 14 → 15/10 (nuit) | **25 × `504` à exactement 900 s** sur les mêmes requêtes. **311 × `503`** la nuit (39 la nuit précédente). Nuit de 20h à 00h : **302 erreurs sur 542 (56 %)**. Jour : 3 erreurs sur 667 (0,4 %) | `gw-fenetre-search-service-1015-0838.log`, `vague2_carte_gx.log` |
| 15/10 05:43 | **Retour sur la VM** : `.env.url` restauré (`SERVICE_SEARCH=http://api-recherche-service:8510`), puis `rescan` du catalogue à 05:44:28 (29/29 services) | `bascule-SERVICE_SEARCH-revert-1015-0843.log`, `-rescan-1015-0844.log`, `-check-1015-0844.log` |

## Chiffres clés

| Mesure | VM (référence) | Cloud Run, délai 300 s (nuit du 13 au 14/10) | Cloud Run, délai 900 s (nuit du 14 au 15/10) |
|---|---|---|---|
| Erreurs de jour | 7,7 % (sur 24 h) | 0,4 % | **0,4 %** |
| Erreurs de nuit | 7,7 % (sur 24 h) | **39 %** | **56 %** (20h-00h) |
| `504` (délai dépassé) | aucun délai côté VM | 46, toutes les 5 min | 25, toutes à 900 s |
| `503` de nuit | — | 39 | **311** |

## Cause

1. **Un traitement de nuit** envoie, depuis `172.20.0.1`, quelques requêtes `POST /search` d'environ 20 Ko, et les relance dès qu'elles échouent. Le client d'origine n'est pas encore identifié : la gateway ne transmet pas son agent, et cette adresse correspond à un port publié ou à un processus de l'hôte de la VM.
2. **Ces requêtes ne se terminent pas**, ni en 5 minutes ni en 15. Sur la VM, rien ne les coupe : la gateway n'a pas de délai pour cette route. Elles s'y terminent peut-être, ou y tournent indéfiniment sur l'un des 8 workers, sans gêner les autres.
3. **Sur Cloud Run, la capacité est faible par requête lourde** : 1 vCPU et 2 workers gunicorn (`uvicorn`) par instance, 3 instances au plus. Une requête longue immobilise un worker, et probablement sa boucle d'événements, si les appels gRPC bloquent. Avec quelques requêtes de ce type, une bonne partie de la capacité est prise. Les autres appels de nuit sont alors refusés (`503`). Les journaux Cloud Run montrent aussi des erreurs gRPC vers le reranking (« Connection reset by peer ») toutes les 30 minutes.
4. **Allonger le délai a aggravé la situation** : à 900 s, chaque requête bloquée occupe un worker trois fois plus longtemps.

## Options étudiées

| Option | Effet attendu | Coût | Retenue ? |
|---|---|---|---|
| Garder Cloud Run avec un délai de 900 s | les requêtes ne se terminent toujours pas, et la capacité reste saturée la nuit | — | **non** (mesuré : 56 %) |
| Délai de 3 600 s (le maximum de Cloud Run) | une requête bloquée occupe un worker 1 h : saturation encore plus forte | — | non |
| Plus de workers, de vCPU ou d'instances (`min` > 1, `--no-cpu-throttling`) | absorberait peut-être le lot, sans garantie puisque les requêtes ne se terminent pas | **surcoût permanent**, alors que l'objectif est de réduire les coûts | non, tant que le lot n'est pas compris |
| **Retour sur la VM** | comportement d'avant la migration (7,7 %, aucun délai) | aucun (la VM tourne déjà) ; Cloud Run repasse en `min=0` (environ −10 €/mois) | **oui** |

## Effets du retour

- La route `/search-service` vise de nouveau `http://api-recherche-service:8510` (conteneur `rag-hp-pub-api-recherche-service-1`, en cours).
- Le Cloud Run `api-recherche` reste déployé (révision `00010-vpb`). Il repasse en **`min_instances: 0`** pour ne plus rien coûter sans trafic.
- Les livraisons sur la recherche se font **de nouveau par `features/poc`**. Le guide équipes et le garde-fou `poc` sont mis à jour.
- Rien ne change pour les autres routes déjà sur Cloud Run.

## Conditions pour reprendre la migration (lot V2-a3-bis)

1. **Identifier le client de nuit** derrière `172.20.0.1`, et le contenu de ses requêtes d'environ 20 Ko.
2. **Mesurer leur durée réelle sur la VM**. Soit elles se terminent, et on connaît leur durée, soit elles ne se terminent jamais, et c'est un défaut à corriger côté client ou service.
3. **Corriger la cause** : borner ces requêtes (taille, `top_k`, pagination), ajouter un délai côté client, ou rendre les appels gRPC non bloquants dans `api-recherche`.
4. **Option d'architecture**, si ce lot reste lourd : une route dédiée aux traitements de nuit (VM ou service séparé), pour que les appels interactifs restent sur Cloud Run.
5. **Rejouer une nuit** sur Cloud Run avec un seuil fixé à l'avance : moins de 7,7 %, et aucun `503` en rafale.

## Avancement des conditions de reprise

| Condition | État | Preuve |
|---|---|---|
| 1. Identifier le client de nuit | ✅ **15/10** : `172.20.0.1` est le nginx de la VM ; le vrai client est le **back-office PHP Hellopro chez Ecritel (`213.182.35.29`)**, sans agent HTTP, qui envoie **100 %** des appels de la recherche, de jour comme de nuit (66 483 requêtes depuis le 01/10). Reste à savoir **quelle tâche** PHP envoie les lots de nuit (devs du back-office) ; piste (15/10, en vérification côté devs) : **le moteur de recherche principal du site Hellopro** | `route-sources-search-service-1015-1402.log` |
| 2. Mesurer la durée réelle sur la VM | ✅ **16/10** : nuit du 15 au 16/10 sur la VM, **20h-00h UTC : médiane jusqu'à 59,8 s, max 939 s** (les requêtes terminent, la VM n'ayant pas de délai) ; 01h-03h rapide ; jour p95 ~2,8 s. **Le client PHP abandonne à 60 s** (448 `499`, médiane 59,8 s) : au-delà, le serveur calcule pour rien. Les requêtes de 20 Ko sont rapides le jour → la cause probable est une **contention des backends la nuit**, pas la taille. Référence jour : médiane 0,5-2 s, p95 ~2,8 s | `nginx-timing-log-mesure-1016-0814.log` |
| 3. Corriger la cause | 🔄 **cause probable (16/10)** : la nuit, les requêtes de recherche (~20 Ko, nombreux documents) passent par le **reranking**, servi par **Triton épinglé sur le seul GPU 1** (GPU 0 inutilisé), qui sert aussi l'embedding d'api-classification ; erreurs ONNX `MatMul` (mémoire GPU) et lenteur → abandon du client à 60 s. Pistes, à valider par la mesure GPU de 24 h : (a) **Triton sur les 2 GPU** — seulement **en attendant le retour de vLLM** sur le GPU 0 (décision du 16/10 : le GPU 0 reste réservé aux modèles locaux) ; (b) **délai serveur de 60 s** aligné sur le client ; (c) borner le nombre de documents à reranker par requête. **Code (16/10)** : `reranking_use_case.py` tokenise sans `max_length` (`truncation=True` = longueur maximale du modèle) et envoie des lots de 256 ; avec une requête de ~20 Ko, la mémoire nécessaire par lot devient énorme → correctif le plus direct : **`max_length` (ex. 512) et lots plus petits**, à valider par l'équipe IA (qualité du classement). **Volume (16/10)** : de 20h à 00h UTC, le reranking reçoit 1 660 à 2 530 requêtes / h (70 000 à 111 000 documents / h, ×10 par rapport au jour) alors que la recherche publique n'en envoie que 100 à 285 → **un autre appelant** sature le reranking la nuit : **`api-classification` (VM, 10 répliques)**, dont l'activité suit exactement la courbe du reranking (20h-01h UTC). L'embedding priorise la recherche (file HAUTE) mais **le reranking n'a pas de priorité** : la recherche attend derrière la classification. Correctifs possibles : **priorité dans le reranking** (comme l'embedding), lot de classification étalé ou décalé, `max_length` et lots plus petits, Triton sur 2 GPU en pont | `recherche-rerank-gpu-1016-0907.log` |
| 4. Option d'architecture | 🔄 **cause complète (16/10)** : le même back-office (Ecritel) envoie la nuit **54 lots de classification** de 120 à 708 Ko, de 6 à 31 min chacun (20h-01h UTC) ; ils saturent embedding + reranking (Triton, GPU 1) et la recherche, sans priorité au reranking, attend. Options : priorité de la recherche dans le reranking ; lots de classification plus petits, étalés ou après 01h ; `max_length` / lots ; Triton sur 2 GPU en pont | `route-sources-classification-service-1016-1740.log`, `nginx-timing-log-mesure-1016-1741.log` |
| 5. Rejouer une nuit | ⬜ | — |

Second client, interactif : l'interface du moteur de recherche RAG (`api-html-recherche-service`, `rag.hellopro.eu`) ouvre depuis le navigateur `wss://api.hellopro.eu/search-service/ws/search` ; peu utilisée (1 connexion `101` sur la période), mais **à tester en V2-a3-bis** (WebSocket sur Cloud Run : connexion coupée au délai maximal du service).

À noter : 4 480 réponses `499` depuis le 01/10 (le client PHP coupe avant la réponse) ; son propre délai d'attente est à connaître.

## Pièces

Journaux dans `Docs/DevSecOps/TICKETS/001-MIGRATION-ARCHI/data/cutover/` :
- relevés de nuit : `gw-fenetre-search-service-1014-0939.log`, `gw-fenetre-search-service-1015-0838.log` ;
- diagnostic : `v2a-diag-503-search-service-1014-0943.log`, `vague2_carte_fv.log`, `vague2_carte_gx.log` ;
- retour arrière : `bascule-SERVICE_SEARCH-revert-1015-0843.log`, `bascule-SERVICE_SEARCH-rescan-1015-0844.log`, `bascule-SERVICE_SEARCH-check-1015-0844.log`.

Contexte : `suivi-vague-2.md` (entrées du 08/10 au 15/10), `reports-et-decisions-vague-2.md` (§ 1 et § 3), PR #887.
