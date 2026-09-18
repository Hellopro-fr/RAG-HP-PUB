# Plan de bascule par lots — VM GPU → GKE, en heures ouvrées

> **Statut : préparé le 2026-09-18 en anticipation de la décision de l'après-midi.** Si l'option « par lots » est
> retenue, ce plan devient la référence et le week-end du 19-20 est **annulé**. Si l'option « d'un coup » l'emporte,
> ce document est archivé tel quel.
>
> Ce que ce plan couvre : les **41 services des priorités P1, P2 et P3** de l'inventaire — 34 consumers, le cluster
> gateway B1 et les always-on B3. Les priorités P4 à P9 (API HTTP sur Cloud Run, fronts, MCP) font l'objet d'un plan
> distinct, la vague 2. Rien ne change pour elles ici.
>
> ⚠️ **Deux numérotations coexistent.** Les **P1…P10** sont les *priorités* de l'inventaire, pour les développeurs.
> Les **L1…L7** sont les *lots d'exécution* de ce plan. L1-L7 ne couvrent que P1-P3.

---

## 1. Le principe

Un consumer bascule en **deux gestes indépendants** : on arrête son jumeau sur la VM, et on repointe son secret du
broker de développement vers celui de production. Rien n'oblige à le faire pour tous le même jour.

Ce qui rend le découpage possible, c'est que **le broker de production est déjà le point de rendez-vous de toute la
VM**. Une chaîne peut donc être à cheval — le processor sur GKE, le writer encore sur la VM — puisque les deux
parlent au même broker. La seule règle absolue :

> **Jamais les deux jumeaux d'un même service actifs en même temps sur la file de production.**
> Sinon ils se partagent les messages : traitements en double, ordre cassé, et aucune erreur visible.

C'est l'invariant qui structure toute la procédure : **arrêter la VM d'abord, repointer GKE ensuite** — et
l'inverse exact au rollback.

Trois blocs restent indivisibles et forment le dernier lot : le cluster gateway B1 (base et jetons partagés), les
always-on B3, et `image-comparison` (compteur Redis partagé — hors de ces lots, il est en P4).

---

## 2. Les sept lots

Du moins risqué au plus risqué, pour que la mécanique soit rodée avant d'arriver aux écritures sensibles.
Le détail de chaque lot — composition exacte, secrets, vigilances, prérequis, feuille de lot — est dans `lots/`.

| Lot | Contenu | Services | Conteneurs VM | Risque | Ce qu'on y valide | Fiche |
|:--:|---|:--:|:--:|---|---|---|
| **L1** | Pilote : `deepseek-metrics-collector`, `nettoyage-bruit-ocr` | 2 | 6 | Faible | **La procédure elle-même**, rollback inclus | [`lots/L1.md`](lots/L1.md) |
| **L2** | QC — 7 services | 7 | 14 | Faible | Sortie internet vers les LLM et l'API HelloPro, sous vraie charge | [`lots/L2.md`](lots/L2.md) |
| **L3** | prix — 5 services | 5 | 8 | Moyen | **Première écriture Milvus en production** (un seul writer) | [`lots/L3.md`](lots/L3.md) |
| **L4** | processors + writers — 9 services | 9 | 39 | Moyen-fort | Écriture Milvus **à l'échelle**, le plus gros volume de la série | [`lots/L4.md`](lots/L4.md) |
| **L5** | graph-rag — 8 processors | 8 | 30 | **Fort** | **Écriture Neo4j** — jamais exercée sur données réelles | [`lots/L5.md`](lots/L5.md) |
| **L6** | `embedding-service`, `template-llm-service`, `webhook-service` | 3 | 9 | **Fort** | gRPC GPU en charge, et **webhook HMAC vers le back-office PHP** | [`lots/L6.md`](lots/L6.md) |
| **L7** | B1 cluster gateway + B3 always-on — bloc indivisible | 7 | — | **Fort** | MySQL `gateway_db` prod, jetons partagés, règles d'archivage ES | [`lots/L7.md`](lots/L7.md) |

**Total : 41 services, 106 conteneurs VM arrêtés (L1-L6).** L7 est de nature différente : il câble des services HTTP
sur les données de production sans arrêter leurs jumeaux VM, qui continuent de servir les entrées publiques jusqu'à
la vague 2.

**L1 est le lot le plus important de la série.** Il ne vaut rien fonctionnellement — deux services sans écriture
critique — et c'est précisément pour ça qu'on y joue **le rollback pour de vrai**, même si tout va bien. La
répétition du 17/09 a trouvé cinq défauts dans une procédure qu'on croyait prête. Si la mécanique doit casser,
qu'elle casse là.

---

## 3. Le calendrier

Un lot par jour ouvré, **jamais un vendredi** : l'observation de 24 heures doit tomber un jour où l'équipe est là.

| Jour | Lot | Fenêtre | Décision |
|---|:--:|---|---|
| lun 21/09 | **L1** | 14h00-16h00 | mar 22 · 9h30 |
| mar 22/09 | **L2** | 14h00-16h00 | mer 23 · 9h30 |
| mer 23/09 | **L3** | 14h00-16h00 | jeu 24 · 9h30 |
| jeu 24/09 | **L4** | 14h00-16h00 | ven 25 · 9h30 |
| ven 25/09 | — | **Tampon.** Bilan de la première semaine, correction de la procédure si besoin | — |
| lun 28/09 | **L5** | 14h00-16h00 | mar 29 · 9h30 |
| mar 29/09 | **L6** | **14h00-16h00** (contrainte : après 13h, cf. `template-llm-service`) | mer 30 · 9h30 |
| mer 30/09 | **L7** | 14h00-16h00 | jeu 1/10 · 9h30 |
| jeu 1 – ven 2/10 | — | **Tampon.** Marge pour un lot rejoué, et bilan de la série | — |

**Date de fin engagée : mercredi 30 septembre**, marge jusqu'au vendredi 2 octobre. Au-delà, la série est
considérée en dérive et repasse en comité.

Pourquoi l'après-midi : la matinée sert à la décision sur le lot précédent et aux derniers prérequis ; la fenêtre
14h-16h (11h-13h UTC) sort de la plage tarifaire pleine de DeepSeek ; et un rollback à 16h30 se fait encore avec
tout le monde présent. La nuit sert d'observation, la décision tombe le lendemain à 9h30.

Le gel de `features/poc` annoncé par le LEAD pour le lundi 21 coïncide avec le début de la série — c'est heureux.

---

## 4. La journée d'un lot

| Quand | Quoi | Qui |
|---|---|---|
| **J-1, matin** | Fiche de lot relue. Pré-contrôles des devs concernés **reçus**. Re-scan Trivy des images du lot. Snapshots des données touchées si le lot écrit. Message J-1 à l'équipe | DSO · LEAD |
| **J, 9h30** | Décision sur le lot précédent : lot suivant, prolonger l'observation, ou rollback | CTO · DSO · LEAD |
| **J, 14h00** | Pré-flight : contexte, listes **dérivées** (jamais recopiées), comptes vérifiés, état de référence du broker | DSO |
| **J, ~14h15** | Arrêt des jumeaux VM du lot → repointage des secrets → rollout → contrôle broker → montée en réplicas | DSO |
| **J, ~15h00** | Validation fonctionnelle : un scénario de bout en bout sur la chaîne ; pour les lots à écriture, **un message contrôlé** avant d'ouvrir | LEAD · dev référent |
| **J, 16h00** | Message J-soir : ce qui a basculé, ce qu'on observe, où regarder | DSO |
| **J → J+1** | Observation : drainage des queues, taux d'erreur, écritures **non dupliquées** | DSO · dev |
| **J+1, 9h30** | Décision | CTO · DSO · LEAD |

Détail exécutable : [`procedure-bascule-un-lot.md`](procedure-bascule-un-lot.md).

---

## 5. Qui fait quoi pendant la série

| Rôle | Engagement |
|---|---|
| **DSO** | Exécute chaque lot. Tient le [tableau de suivi](suivi-bascule-par-lots.md) **à chaque geste**. Porte le rollback |
| **CTO / PM-IA** | Décision de 9h30 chaque matin. Arbitre un arrêt de série |
| **LEAD** | Collecte les pré-contrôles avant J-1 de chaque lot. Valide fonctionnellement après bascule. Pour L7 : revue écrite des règles d'archivage ES |
| **Devs concernés** | Pré-contrôle remis avant J-1 de *leur* lot. Un référent joignable pendant la fenêtre et le lendemain matin |
| **RSSI** | Re-scan de chaque lot conforme au VEX signé. Décision de rollback avec le CTO |
| **ECRITEL** | **Non mobilisé.** Aucune entrée publique ne bouge dans cette série |

---

## 6. Les règles de la série

1. **Arrêter la VM avant de repointer GKE**, et l'inverse au rollback. Sans exception.
2. **Aucune liste recopiée.** Conteneurs VM, déploiements GKE, secrets : tout est dérivé au moment de l'exécution,
   et les comptes sont vérifiés contre la fiche de lot avant d'agir.
3. **`kubectl patch` clé par clé**, jamais `create --dry-run | apply`. Sept secrets sont multi-clés ; les
   reconstruire effacerait les identifiants Milvus des writers.
4. **`docker stop`, jamais `docker rm`.** Le conteneur arrêté est le filet de rollback.
5. **Un lot par jour, jamais le vendredi.** L'observation de 24 h est non négociable.
6. **Le rollback de L1 est joué**, même si tout va bien.

### Arrêt de la série

- **1 rollback** → pause d'un jour ouvré, analyse de cause **écrite**, correction de la procédure, reprise.
- **2 rollbacks** → série **suspendue**, comité CTO / LEAD / DSO avant toute reprise.
- Dérive au-delà du 2 octobre → comité.

---

## 7. Le gel de `prod` pendant la série

Le rebuild du 15/09 et son re-scan valent pour les images **telles que déployées**. Un merge sur `prod` qui touche
un service en attente de bascule les invalide pour ce service.

| Ce qui est gelé | Ce qui reste libre |
|---|---|
| Tout merge touchant `apps-microservices/<service>` ou `libs/` pour un service **des lots non encore passés** | `docs/` — aucun workflow ne s'y déclenche |
| En particulier `product-processor-service` (L4) et `mcp-gateway-service` (L7), les deux seuls consumers GKE avec un **wrapper CD** : un merge les redéploierait | Les services de P4 à P9 (Cloud Run, fronts) — hors de cette série |
| | Un service **déjà basculé** et validé — après re-scan |

**Chaque lot est re-scanné la veille** (Trivy image sur ses seules images, quelques minutes). C'est ce re-scan
ciblé, et non un gel total, qui garantit que ce qu'on déploie est ce qu'on a scanné. Toute CRITICAL non couverte
par le VEX du 17/09 bloque le lot.

---

## 8. Ce qui autorise un lot, ce qui le fait revenir

**GO du lot** (tous cochés, la veille au soir) :

- [ ] Pré-contrôles reçus pour chaque service du lot
- [ ] Re-scan du lot : 0 CRITICAL hors VEX
- [ ] Snapshots pris si le lot écrit (Milvus, Neo4j, `gateway_db`)
- [ ] Prérequis spécifiques de la fiche de lot cochés
- [ ] Référent dev joignable confirmé
- [ ] Lot précédent : décision GO prononcée le matin

**Rollback du lot** — décidé par DSO + LEAD, CTO informé :

- Les queues du lot **ne drainent pas** malgré la montée en réplicas
- Une écriture incorrecte ou **dupliquée** constatée (Milvus, Neo4j, back-office)
- Une chaîne métier cassée sans contournement
- Un service du lot en crash-loop non expliqué en 15 minutes

**Ce qui n'est pas un motif de rollback** : `llm_templating_queue` sans consommateur avant 13h locales
(désabonnement volontaire) · une queue `_dlq` sans consommateur (c'est leur état normal) · une latence un peu
plus élevée le premier jour.

---

## 9. Communication

**La veille (J-1), aux devs concernés et au LEAD :**

> Demain **[date]** entre 14h et 16h, le lot **L[n]** bascule : **[services]**. Vos pré-contrôles sont reçus, merci.
> Un référent joignable pendant la fenêtre : **[nom]**. Après bascule, on vous demande un scénario de bout en bout sur
> votre chaîne et de confirmer que les écritures attendues sont là — et pas en double. Décision définitive
> **[J+1] à 9h30**. Point de contact : DevSecOps.

**Le soir (J), à toute l'équipe :**

> Lot **L[n]** basculé à **[heure]** : **[services]** tournent maintenant sur GKE avec les données de production ;
> leurs jumeaux VM sont arrêtés (et redémarrables en une minute). Observation en cours : **[état des queues]**.
> Rien à faire de votre côté. Si vous constatez un comportement inhabituel sur **[chaînes]**, remontez-le au
> DevSecOps **avant** de chercher à corriger. Décision demain 9h30.

---

## 10. Ce qui change par rapport au plan « J0 week-end »

| Abandonné | Conservé |
|---|---|
| La fenêtre du week-end 19-20 et son runbook heure par heure | Le VEX signé, la whitelist ECRITEL, les secrets réels, les images rebuildées |
| La montée à ~66 pods **en une fois** — remplacée par une montée par lot, ajustée sur les queues | Les cinq règles de la fenêtre, devenues les règles de la série |
| Le rollback global de 9 minutes — remplacé par un rollback **par lot**, de l'ordre de la minute | La procédure unitaire, qui est la même que celle du J0 découpée par lot |
| L'astreinte week-end | Les pièges horaires et les faux positifs `_dlq` |

---

## 11. Après L7

La série close, les 41 services de P1-P3 tournent sur GKE avec les données de production. Les jumeaux VM des
consumers restent **arrêtés mais présents** pendant sept jours, puis sont supprimés. La vague 2 — priorités P4 à P9,
entrées publiques, fronts — fait l'objet d'un plan séparé, qu'on écrira avec ce qu'on aura appris ici.
