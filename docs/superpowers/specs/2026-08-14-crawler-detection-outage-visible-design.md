# Spec — une panne de détection doit être visible, pas seulement inoffensive

**Date** 2026-08-14 · **Périmètre** `crawler-service` (Node + Python) · **Statut** à approuver

Suite du constat **C** de `docs/superpowers/references/2026-07-29-crawler-detection-seam-audit.md`.
**Ne pas ré-auditer** la référence. Mais son périmètre est **re-dérivé** ici : elle précède
`verdictUnavailable` (livré aujourd'hui, `29176915`/`53df7168`) et ne connaissait donc qu'un
seul site de défaillance, là où il y en a dix.

---

## 1. Où on en est

Les chantiers du jour ont rendu une panne de détection **inoffensive** : plus de faux
verdict `not_french`, plus de fausse revendication `action:'deleted'`, et les pages sans
verdict sortent de l'ensemble des orphelines (`8c96983b` + `47c0e537`).

Elle reste **invisible**, et c'est ce que cette spec traite. Chaîne vérifiée :

- aucun des dix sites `verdictUnavailable = true` ne pose `context.stopReason` ni
  `context.fatalExitCode` — les seuls poseurs de `fatalExitCode` sont `routes.ts:332/344`
  (=7), `:426` (=8) et `functions.ts:747` (=9) ;
- la file se vide donc normalement, `isError` reste `""`, et
  `gracefulShutdown('COMPLETED', context.fatalExitCode ?? 2)` sort en **2** (`main.ts:1763`) ;
- `_classify_exit_code(2)` rend `(None, None)`, `is_success` est vrai, statut `finished`,
  **webhook de SUCCÈS** (`crawler_manager.py`).

Conséquence opérationnelle : un run où la détection est tombée se déclare réussi. Sur la
homepage il reste une trace en texte libre tronquée à 250 caractères ; **sur une page
interne, il n'y a aucune trace** — ni compteur, ni message, ni champ. Seule la ligne
`[VERDICT_UNAVAILABLE]` du log.

C'est cette invisibilité qui a permis à toute la classe de défauts de survivre : personne ne
pouvait la compter.

## 2. La contrainte de l'audit est LEVÉE — vérifié, pas supposé

L'audit posait un préalable : *« confirmer que le BO traite `detection_unavailable` (ou une
cause inconnue) comme réessayable et non terminale ; s'il auto-retire sur cause inconnue,
livrer la moitié Python et le mapping BO ensemble »*.

**Il retire sur une allowlist explicite de deux causes, pas sur l'inconnu :**

```php
if (AUTO_RETIRE_ENABLED && in_array($failure_cause, ['proxy_blocked', 'domain_dead'], true))
```

`script_process_update_crawling.php:205` et `script_process_detect_fiche_produit.php:112`
(ce dernier ajoute `&& !est_statut_terminal_decide($id_domaine)`). Une cause absente de
cette liste — `detection_unavailable` comme n'importe quelle inconnue — **ne retire rien**.

Donc **la moitié Node peut partir seule**, exactement comme l'audit l'avait prévu. Un exit 10
non encore connu du Python dégrade dans la branche `unknown` ⇒ `failed` + webhook d'échec,
ce qui est déjà l'amélioration recherchée.

Note au passage : `map_failure_cause_to_reason` (`fonctions_retire_domaine.php:37`) est du
**code mort** — aucun appelant. Les deux sites passent `$failure_cause` directement, déjà
contraint par l'allowlist. Ne pas le « réparer » en croyant qu'il protège quelque chose.

## 3. Périmètre re-dérivé : dix sites, deux classes qui ne se valent pas

Frontière structurelle vérifiée : `const isMainSite = matchesMainSite(request.url, site)`
(`routes.ts:556`), `if (isMainSite) {` (`:578`), son `} else {` (`:771`).

| Classe | Sites | Ce qui se passe |
|---|---|---|
| **Homepage** | `:644`, `:714`, `:767` | `isEnqueuingLinks` reste faux ⇒ aucun lien enfilé ⇒ en crawl initial, run d'**une seule requête**, dataset vide |
| **Page interne** | `:789`, `:814`, `:821`, `:833`, `:854`, `:889`, `:898` | le crawl **continue** ; seule cette page est sautée |

**Elles exigent des traitements opposés, et c'est le cœur de cette spec.**

Une homepage sans verdict ne produit rien : un webhook de succès est un mensonge, et
l'échec est le verdict honnête. **Exit 10 justifié.**

Une page interne sans verdict n'invalide pas le crawl. Faire échouer tout un crawl parce
qu'**une** URL n'a pas eu de verdict serait un remède pire que le mal : une détection qui
hoquette sur une page détruirait un crawl entier de plusieurs centaines de pages réussies.
**Il faut compter et rapporter, pas tuer.**

Un correctif uniforme sur les dix sites — la lecture littérale de l'audit — serait donc
activement nuisible. C'est la conséquence de son antériorité sur `verdictUnavailable`, et
elle ne se voit qu'en re-dérivant.

## 4. Volet A — exit 10 sur la homepage

Sur les trois sites homepage : poser `context.stopReason = "detectionUnavailable"` et
`context.fatalExitCode = 10`, puis appeler le `stopCrawler(...)` existant — le même motif
que les branches voisines qui savent déjà arrêter proprement (`:619-620` pour un challenge
non résolu, `:649`/`:748` pour un échec d'écriture de méthode).

Côté Node : entrée dans `ERROR_MAP` (`main.ts:1126-1140`).

Côté Python : `elif exit_code == 10: return ("Service de détection de langue indisponible",
"detection_unavailable")` dans `_classify_exit_code`, **avant** la branche 137, et ajouter
`10` au tuple d'exclusion. Vérifier les numéros de ligne dans le fichier au moment de
coder : l'audit les donnait pour un état antérieur du dépôt.

**Séquencement.** Exit 10 est libre (le tuple liste 0,2,3,4,5,6,7,8,9,-1,137). La moitié
Node peut partir seule (§2). Rien à coordonner avec le BO.

### Un cas à trancher explicitement

En mode **mise à jour**, `context.homepageReady.resolve()` est délibérément **hors** du
résultat de détection (`routes.ts:1294-1295`), donc `seedPhase2` sème les URL du crawl
précédent même si la homepage n'a pas eu de verdict. Arrêter le crawl sur exit 10
supprimerait ce travail de Phase 2.

Deux lectures défendables, et l'implémenteur doit choisir **en le documentant** :
- **arrêter quand même** — sans verdict de homepage, le crawl de MAJ ne peut pas décider de
  la langue du domaine, et les pages internes seront de toute façon toutes sans verdict ;
- **ne pas arrêter en mode MAJ** — les pages internes ont leur propre détection et peuvent
  réussir ; l'échec de la homepage ne condamne pas le run.

La seconde est probablement la bonne, mais elle demande de vérifier si la détection est
tombée *globalement* ou seulement sur cette URL — information que le crawler n'a pas
aujourd'hui. Ne pas trancher au feeling : mesurer d'abord ce que fait un run de MAJ réel.

## 5. Volet B — rendre la panne partielle comptable

C'est le volet qui n'est pas dans l'audit, et le plus utile à l'exploitation.

Ajouter un compteur `StatsManager` — nom suggéré `verdict_unavailable` — incrémenté sur
**chacun** des dix sites, homepage comprise. Il doit remonter dans la charge du webhook,
comme `filtered_nonfr`.

Pourquoi ça compte plus qu'il n'y paraît : la **panne partielle** est la bande dangereuse
que le sidecar a rendue inoffensive mais pas détectable. Assez de pages jugées pour que le
dataset soit non vide et la couverture au-dessus de 80 %, le reste silencieusement protégé
— sur un run étiqueté sain. Sans compteur, personne ne sait que ça s'est produit.

Deux contraintes :

- **Ne pas réutiliser `errors`.** C'est lui qui alimentait la garde de santé du BO et les
  deux plafonds de suppression ; l'incrémenter ici rearmerait des freins qui bloquent *tout*
  le traitement destructeur, ce qui n'est pas la décision de cette spec. Voir le résidu du
  §7.
- **Vérifier la liste blanche du webhook** (`fonctions_scrapping.php:761-771`) : elle porte
  déjà `filtered_nonfr`, `message_erreur_crawling` et `failure_cause`. Un compteur absent de
  cette liste n'arrive jamais au BO — un correctif qui ne remonte rien est inerte.

Et un message pour les pages internes : aujourd'hui aucun des sept n'écrit dans
`crawlErrorMessage`. Décider s'il faut en poser un, en tenant compte de la troncature à 250
caractères et du fait que le champ est partagé — écraser une cause plus grave serait une
régression.

## 6. Critères d'acceptation

1. Une homepage sans verdict, en crawl **initial**, produit un **webhook d'échec**, pas de
   succès. C'est le seul critère qui prouve que le défaut est fermé.
2. Un site réellement non francophone conserve **exactement** son comportement actuel :
   succès, `filtered_nonfr` incrémenté, aucun exit 10. Non-régression prioritaire.
3. Une page interne sans verdict **n'arrête pas** le crawl, et le compteur monte.
4. Le compteur arrive dans la charge du webhook côté BO (pas seulement dans le log).
5. Un exit 10 vu par un Python qui ne le connaît pas encore dégrade en `failed` + webhook
   d'échec, sans exception.
6. Chaque test ajouté doit **échouer dans au moins une variante de neutralisation**. Une
   seule direction ne prouve que les assertions qui pointent dans l'autre sens.

## 7. Hors périmètre, nommé

- **Réarmer la garde de santé et les plafonds du BO.** Ils restent aveugles à une panne de
  détection depuis que `errors` n'est plus incrémenté sur un rejet linguistique. Le sidecar
  a retiré les pages de l'ensemble des orphelines ; il n'a pas rétabli de frein. Chantier
  distinct, et il ne se règle pas en remettant l'appel supprimé.
- `?lang=fr-BE` propagé alors que l'exclusion régionale ne le filtre pas.
- Le danger tier-2 (`lang` classé `toRemove`), latent tant que `QM_TIER2_ENABLED` est faux.
- Constats D à L de l'audit.

## 8. Déploiement

Rebuild `crawler-service`. Aucun changement de compose, aucun BO, aucune migration — sauf si
le volet B exige d'ajouter le compteur à la liste blanche du webhook, auquel cas une MEP BO
d'une ligne s'ajoute et doit partir **après** le rebuild (sinon la liste blanche référence un
champ que le crawler n'émet pas encore, ce qui est inoffensif mais trompeur à la lecture).
