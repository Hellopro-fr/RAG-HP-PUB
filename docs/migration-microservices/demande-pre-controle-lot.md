# Demande de pré-contrôle d'un lot — modèle à envoyer au Lead Dev

> À envoyer par le DevSecOps la veille du lot (P0, point 2 de [`procedure-bascule-un-lot.md`](procedure-bascule-un-lot.md)).
> Le pré-contrôle est la parole des devs sur leur code : ni le DSO ni le LEAD ne peuvent le produire à leur place.
> Ce qu'on sait déjà côté DSO est pré-rempli ; le dev confirme ou complète. **Une fiche « rien à signaler » est une réponse valide, mais elle doit exister.**

## Le message (copier, remplacer les crochets, envoyer)

> **Objet : Pré-contrôle lot L[n] — réponse attendue avant [jour heure]**
>
> Bonjour,
>
> Le lot **L[n]** ([services, noms compose]) bascule sur GKE **[date] entre 14h et 16h** (heure Paris). Avant de lancer, j'ai besoin d'un pré-contrôle par service, fait par le dev qui connaît le code.
>
> **Quoi** : une fiche par service (modèle en bas de [`guide-pre-check-service.md`](guide-pre-check-service.md), section « Fiche de remontée »). Les services de ce lot sont **P[priorité]** dans l'inventaire → étapes **[1 à 6 / 4 à 6]** du guide seulement.
>
> **Les trois questions qui comptent** (les commandes sont dans le guide, 10-15 min par service) :
> 1. **Fichiers / volumes (étape 4)** — le service écrit-il sur disque ailleurs que [ce qu'on sait déjà] ? Sur GKE, ce qui n'est pas déclaré disparaît avec le pod.
> 2. **Variables (étape 5)** — le code lit-il une variable absente de la ligne du service dans [`env-migration-matrix.md`](env-migration-matrix.md) ? Sur la VM tout le monde hérite du `.env` unique ; sur GKE, seulement ce qui est déclaré.
> 3. **Écritures (étape 6)** — **que se passe-t-il si un message est traité deux fois ?** Pendant la bascule, un message en vol peut être rejoué (jumeau VM arrêté, pod GKE le reprend). Cible des écritures : [API HelloPro / Milvus / Neo4j / back-office…]. Réponse attendue : *rejouable sans dégât* oui / non / à vérifier, et pourquoi.
>
> **Ce qu'on sait déjà côté DSO** (à confirmer, pas à refaire) : [liste courte, ex. « écriture `/app/tracking` connue et décidée », « variables lues = A, B, C toutes dans la matrice »].
>
> **Forme de la réponse** : la fiche remplie (ou « idem service X » quand le code est le même), verdict coché, envoyée à [canal / personne] **avant [jour heure]**. Sans réponse pour un service, il sort du lot.
>
> **Il me faut aussi** : le nom du **référent joignable** pendant la fenêtre (14h-16h) et le lendemain à 9h30 pour la décision. Après bascule, on lui demandera un scénario métier de bout en bout sur la chaîne et la confirmation que les écritures attendues sont là, **et pas en double**.
>
> Merci. Point de contact : DevSecOps.

## Ce que le DSO fait des réponses

1. Consigne les verdicts dans la fiche du lot (`lots/L[n].md`, section « Prérequis spécifiques »), avec date et source.
2. Toute réponse « non » ou « à vérifier » sur l'idempotence devient une **contrainte de P6** : un message contrôlé avant d'ouvrir le flux, et un point de vigilance dans le rollback.
3. Une variable absente de la matrice = ajout au manifeste GKE **avant** le lot, pas pendant.
4. Ligne du tableau de suivi : `⬜ à venir` → `🟡 prêt` seulement quand les fiches et le référent sont là.

## Historique des demandes

| Lot | Envoyée le | Réponses reçues | Verdict consigné dans |
|---|---|---|---|
| L1 | — (lot pilote, vérifications DSO) | — | `lots/L1.md` |
| L2 | 21/09 (oral, via le LEAD) | 21/09 : tracking seul fichier écrit · toutes variables dans la matrice · double traitement « déjà géré » | `lots/L2.md` |
