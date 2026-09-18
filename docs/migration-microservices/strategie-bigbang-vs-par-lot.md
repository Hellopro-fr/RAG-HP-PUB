# Bascule d'un coup ou par lots — aide à la décision

> **Option préparée en détail** : le plan par lots est écrit — [`plan-bascule-par-lots.md`](plan-bascule-par-lots.md), fiches [`lots/`](lots/), [`procedure-bascule-un-lot.md`](procedure-bascule-un-lot.md), [`suivi-bascule-par-lots.md`](suivi-bascule-par-lots.md). Il devient la référence si la décision le retient, et reste archivé sinon.
>
> **Pour la réunion du 2026-09-18.** Document d'entrée, pas de conclusion : la décision appartient au CTO,
> au Lead Dev et au DevSecOps.
>
> Les deux options sont **réellement jouables**. Le plan « d'un coup » est prêt et son rollback a été répété
> chronomètre en main le 17/09. Ce document expose ce qu'on gagne et ce qu'on perd dans chaque cas.

---

## Le point qui a changé

Jusqu'ici la question ne se posait pas, parce qu'on croyait la flotte indivisible. Elle ne l'est pas.

Un consumer bascule en deux gestes : on **arrête son jumeau sur la VM**, et on **repointe son secret** du broker
de développement vers celui de production. Ces deux gestes se font **service par service**. Rien n'oblige à les
faire tous le même jour — à condition de ne jamais laisser les deux jumeaux d'un même service tourner en même
temps sur la file de production.

Trois exceptions, qui restent des blocs indivisibles :

| Bloc | Pourquoi il ne se découpe pas |
|---|---|
| **B1 — cluster gateway** (4 services) | Base MySQL et jetons d'administration partagés. Une bascule partielle casse la synchronisation |
| **B3 — always-on** (3 services) | Le `dlq-manager` et ses règles d'archivage doivent être câblés ensemble |
| **`image-comparison`** | Compteur Redis partagé avec la VM, à isoler au moment de la bascule |

---

## Ce qu'on sait, chiffré

| Donnée | Valeur | Source |
|---|---|---|
| Rollback complet de la flotte | **~9 min** (51 s + ~3 min + 17 s + ~2 min) | Répété et mesuré le 17/09 |
| Reconnexion AMQP d'un conteneur après redémarrage | **7 s** | Mesuré sur un pilote |
| Services à basculer | 34 consumers + 4 (B1) + 3 (B3) | Inventaire du 16/09, corrigé le 17/09 |
| Secrets à repointer | 35, en **deux conventions de nommage** | Relevé du 17/09 |
| Capacité | 33 pods → ~66, soit 8,75 GiB sur 13,3 disponibles | Calcul C6 |
| **Écritures jamais exercées sur données réelles** | **Neo4j, Milvus prod, webhooks HMAC, archivage ES** | — |

Cette dernière ligne est le cœur du sujet. Tout le reste a été éprouvé en shadow depuis juillet ; **les écritures,
non**. C'est le seul vrai inconnu, et c'est lui qui devrait décider.

---

## Option A — Tout d'un coup, le week-end

**Ce qu'on gagne.** Une fenêtre, un gel, une procédure de rollback, et c'est fini. L'équipe est mobilisée une seule
fois. Pas d'état intermédiaire à suivre : lundi matin, tout est d'un côté ou de l'autre. Le plan existe, il est
détaillé heure par heure, et son rollback a été répété.

**Ce qu'on perd.** Tous les inconnus se déclenchent dans la même fenêtre de trois heures. Si l'écriture Neo4j se
comporte mal, on l'apprend au milieu de cinq autres chaînes qui viennent de basculer, et il faut décider vite, un
samedi, avec moins de monde joignable. Le rollback est global : **une seule chaîne cassée fait revenir les 34**.

Et les 9 minutes mesurées sont le temps d'**exécution** du rollback, pas celui du **diagnostic**. Constater
l'anomalie, comprendre qu'elle est structurelle et non transitoire, appeler, se mettre d'accord : c'est là que
passe le temps réel. C'est pourquoi on s'est gardé 21 minutes de marge.

---

## Option B — Par lots, sur plusieurs jours

**Ce qu'on gagne.** Le rayon d'impact tombe d'une flotte à une chaîne. Le rollback d'une chaîne se compte en
**secondes**, pas en minutes, et il ne touche que les services concernés. Les écritures sur données réelles se
valident une famille à la fois : Milvus d'abord, Neo4j ensuite, chacune avec toute l'attention disponible plutôt
qu'un dixième. La montée en capacité s'observe progressivement au lieu d'être calculée à l'avance. Et chaque lot
apprend quelque chose au suivant.

Surtout : **en heures ouvrées**, avec le Lead Dev et les développeurs joignables. La répétition du 17/09 a montré
que les vrais problèmes ne sont pas où on les attend — un service oublié dans une liste, une commande destructive
dans une procédure, un port qui n'existe pas. Les trouver un mardi à 15h coûte infiniment moins cher qu'un samedi.

**Ce qu'on perd.** La coexistence dure plus longtemps : pendant X jours, une partie des chaînes tourne sur GKE et
l'autre sur la VM. Il faut à tout moment savoir qui est où — donc un tableau de suivi tenu à jour, faute de quoi
le débogage devient pénible. Le gel des merges sur `prod` doit tenir plus longtemps, ou être levé lot par lot, ce
qui demande de la discipline. Le temps total de DevSecOps est plus élevé : chaque lot a son cycle de préparation
et de vérification.

Et il y a un risque humain réel : une migration étalée peut **s'enliser**. Les trois derniers lots, moins urgents,
traînent des semaines. Il faut une date de fin engagée, pas seulement une date de début.

---

## Découpage proposé, si l'option B est retenue

Par **chaîne métier**, du moins risqué au plus risqué — pour que la mécanique soit rodée avant d'arriver aux
écritures sensibles.

| Lot | Contenu | Nb | Risque | Ce qu'on y valide |
|:--:|---|:--:|---|---|
| **L1 — pilote** | `deepseek-metrics-collector-service`, `nettoyage-bruit-ocr-service` | 2 | Faible | La mécanique elle-même : arrêt VM, reseed, contrôle broker, rollback |
| **L2** | QC (7 services) | 7 | Faible | Sortie internet vers les LLM et l'API HelloPro, sous vraie charge |
| **L3** | prix (5 services) | 5 | Moyen | Accès direct à Milvus |
| **L4** | processors + writers (9) | 9 | **Moyen-fort** | **Écriture Milvus en production** |
| **L5** | graph-rag (8 processors) | 8 | **Fort** | **Écriture Neo4j en production** — jamais exercée |
| **L6** | `embedding-service`, `template-llm-service`, `webhook-service` | 3 | **Fort** | gRPC vers le GPU, et **webhook HMAC vers le back-office PHP** |
| **L7** | B1 (4) + B3 (3) — **bloc indivisible** | 7 | Fort | MySQL gateway prod, jetons partagés, règles d'archivage ES |

Un lot par jour ouvré tient largement : la partie exécution se compte en minutes, c'est l'observation qui prend
du temps. **Cinq à sept jours ouvrés**, avec une date de fin engagée.

**L1 est le plus important.** Deux services sans écriture critique, dont le seul rôle est de prouver que la
procédure fonctionne de bout en bout. S'il révèle un défaut — et la répétition du 17/09 laisse penser qu'il en
reste — on le corrige avant que ça compte.

---

## Ce que je recommande

**L'option B, par chaîne, en heures ouvrées.**

Le raisonnement tient en une phrase : le seul inconnu sérieux, ce sont les écritures sur données réelles, et
l'option B transforme un gros inconnu en six petits, chacun traité avec toute l'attention disponible et une
équipe joignable.

La répétition de rollback d'hier a produit son vrai résultat non pas en confirmant un chrono, mais en révélant
**cinq défauts** dans une procédure qu'on croyait prête, dont trois auraient cassé la bascule sans message
d'erreur. Rien ne dit qu'il n'en reste pas. Un pilote de deux services les fera sortir à moindre coût.

**Ce que cette recommandation coûte**, et il faut l'assumer : plus de jours de coexistence, un tableau de suivi à
tenir, un gel plus long, et le risque d'enlisement si la date de fin n'est pas engagée fermement.

**Ce qui ferait pencher vers l'option A** : une contrainte de calendrier externe, une fenêtre de faible trafic
qu'on ne retrouvera pas, ou une indisponibilité de l'équipe en semaine. Ce sont des arguments recevables, et ce
sont eux qu'il faut peser — pas la technique, qui autorise les deux.

---

## Si l'option B est retenue, ce qu'il faut décider dans la foulée

1. **La date de fin engagée** — sans elle, l'enlisement est le scénario le plus probable.
2. **Le gel de `prod`** : maintenu du début à la fin, ou levé entre les lots ? Un merge entre deux lots invalide
   les images reconstruites et le scan de sécurité, il faudrait les refaire.
3. **Qui tient le tableau de suivi** de l'état chaîne par chaîne, et où il vit.
4. **Le critère d'arrêt** : à partir de quoi on suspend la série au lieu de passer au lot suivant.
