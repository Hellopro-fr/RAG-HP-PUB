# Plan — « la détection n'a pas répondu » ≠ « le site n'est pas français »

Spec : `docs/superpowers/specs/2026-08-14-crawler-detection-verdict-unavailable-design.md`
(approuvée 2026-08-14, `admission_rejected` inclus dans l'ensemble fermé).

Service : `apps-microservices/crawler-service/crawler/`. Trois tâches, dans cet ordre :
la tâche 1 est autonome, la tâche 2 dépend d'elle, la tâche 3 est indépendante des deux.

## Outillage local

**Prérequis mesuré le 2026-08-14 : les dépendances n'étaient pas installées.** `node_modules`
était **vide** alors que `package-lock.json` existe, donc le test échouait en
`ERR_MODULE_NOT_FOUND: Cannot find package 'axios'` — un échec d'environnement, pas de code.
L'affirmation de l'audit selon laquelle ce test « tourne localement sous tsx » était donc
fausse en l'état. Installer d'abord :

```bash
cd apps-microservices/crawler-service/crawler
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install --no-audit --no-fund
```

**`npm install`, PAS `npm ci`** — et ce n'est pas une négligence. Le `package-lock.json`
présent localement **n'est pas suivi par git** et il est désynchronisé de `package.json`
(`p-limit@3.1.0` verrouillé contre `p-limit@5.0.0` requis), donc `npm ci` échoue par
conception en `EUSAGE`. Le Dockerfile (`npm install`, ligne 8) et la CI
(`ci_services_crawler.yml:43-45`, avec le commentaire « pas de package-lock.json dans le
repo — à remplacer par `npm ci` quand un lockfile sera committé ») font déjà ce choix.
Rien n'est cassé : la commande ci-dessus est celle qui correspond à la CI.

(`node_modules` est git-ignoré, la réinstallation est sans effet sur le dépôt. Les
navigateurs sont inutiles ici : le test n'importe ni crawlee ni playwright.)

Puis :

```bash
npx tsc --noEmit          # typecheck
npx tsx --test src/class/DetectionLangueClient.test.ts
```

`DetectionLangueClient.test.ts` n'importe pas crawlee : il tourne localement. Ne pas tenter
de lancer le crawler entier — il exige Redis, un proxy Apify et un navigateur.

**Base de référence mesurée le 2026-08-14, après installation :** `DetectionLangueClient.test.ts`
rend **16 tests, 16 passés, 0 échec**, et `npx tsc --noEmit` ne sort **rien**. La référence est
donc verte : tout échec observé après cette ligne est imputable au changement en cours, pas à
l'existant. Citer cette base dans le rapport de tâche.

**Ce compte bouge à chaque tâche livrée — le relever, ne pas le citer de mémoire.** Il valait
3 à l'écriture de ce plan ; les tâches 1 à 3 ont ajouté les leurs (prédicat
`isTechnicalFailureMethod`, `extractPrimaryMethod`, puis `stripInjectedLanguageParam`), d'où 16.
Une base périmée fait imputer à son propre changement un delta qui vient de la tâche
précédente : mesurer la référence **avant** de coder, dans le même shell.

**Si le test échoue encore après l'installation, l'établir comme préexistant avant de coder**
— relever le message exact et le citer dans le rapport. Ne jamais attribuer à son propre
changement un échec dont on n'a pas vérifié qu'il est neuf : dans ce dépôt, une erreur de
collecte préexistante a déjà fait passer une suite entière pour verte alors qu'elle
n'exécutait aucun test.

**Règle de contrôle, non négociable** : chaque test ajouté doit être vu **échouer** en
retirant le code qu'il garde, puis repasser après restauration. Deux tests d'un chantier
précédent de ce dépôt passaient sans leur correctif. Le rapport de tâche doit citer le
message d'échec obtenu.

---

## Tâche 1 — le prédicat `isTechnicalFailureMethod`

**Fichier** `src/class/DetectionLangueClient.ts` (+ son test).

Ajouter une méthode statique à côté de `requiresNlpValidation` (`:186-188`), dont elle suit
la forme (ensemble local, pas de dépendance) :

```ts
static isTechnicalFailureMethod(method: string): boolean
```

Elle rend `true` si la méthode dénote une défaillance technique — c'est-à-dire l'absence de
verdict — et non un jugement linguistique.

Ensemble fermé : `challenge_page`, `error`, `fetch_empty_content`, `admission_rejected`.

Contraintes :

- **Commenter le statut de chaque membre.** Les trois premiers sont atteignables sur les
  appels du crawler ; `admission_rejected` **ne l'est pas** aujourd'hui (le crawler envoie
  `html_content`, donc il court-circuite l'admission) et figure là par précaution. Sans ce
  commentaire, un futur lecteur conclura que le crawler l'observe en production.
- **Décider et documenter le traitement des méthodes composées.** `method` peut être
  `+`-composé. Regarder comment `extractPrimaryMethod` (`:170-176`) split, et choisir
  explicitement entre égalité stricte et appartenance après split. Écrire la raison dans le
  code : c'est le genre de détail qui se retourne quand une nouvelle méthode composée
  apparaît, et §2 de la spec montre que ça arrive.

  > **Correction 2026-08-14** — une version antérieure de ce plan donnait `...+variant_rescue`
  > comme exemple motivant. Il est **inatteignable** sur les appels du crawler, pour deux
  > raisons indépendantes vérifiées : le rattrapage est gardé par
  > `if not html_was_provided and ...` (`routes.py:621`) et le crawler envoie toujours
  > `html_content` — le CLAUDE.md du service dit « crawler-service is immune » ; et le suffixe
  > n'annote jamais qu'un verdict **`ok=True`** (`routes.py:205`, `:223`), donc il ne peut pas
  > qualifier une défaillance technique. Conséquence pour la décision : **aucun chemin
  > atteignable ne compose une méthode technique aujourd'hui**, donc le choix ne repose pas
  > sur des données observées mais sur l'asymétrie des erreurs — égalité fausse rouvre le
  > faux `not_french` et la revendication de suppression (silencieux, destructeur), split
  > faux coûte du budget de crawl et se voit dans `filtered_nonfr`. Choisir le côté
  > récupérable.
- Ne modifier aucune méthode existante.

**Tests** (`src/class/DetectionLangueClient.test.ts`) :

1. `true` pour chacun des quatre membres.
2. **`false` pour `Check_nok_v2`, `nlp_not_confirmed`, `nlp_override_tld_fr`.** C'est
   l'assertion la plus importante du chantier : ce sont exactement les trois verdicts de
   l'allowlist `DETECTION_LANGUAGE_VERDICTS` du BO, et un prédicat qui les avalerait
   arrêterait de filtrer les vrais sites non francophones.
3. `false` pour une méthode de succès (`langHtml`, `direct_match`, `nlp_confirmed`).
4. Le cas composé retenu à l'étape précédente, dans les deux sens.

---

## Tâche 2 — l'état « verdict indisponible » dans `routes.ts`

**Fichier** `src/routes.ts`. **Dépend de la tâche 1.**

L'invariant à faire respecter — le formuler ainsi dans le commentaire du drapeau :

> Aucune défaillance technique ne doit incrémenter `filtered_nonfr`, écrire dans
> `nfr-{domain}`, ni appeler `updateChecker.checkUrl`.

**a. Le drapeau.** `let verdictUnavailable = false;` à côté de `let isEnqueuingLinks = false;`
(`:557`).

**b. Le poser.** Aux cinq sites connus : les trois `catch` (`:717-720`, `:768-770`,
`:817-819`, aujourd'hui `log.error` seul) et les deux branches de challenge non résolu
(`:739-741`, `:788-790`). **Chercher aussi tout autre chemin** qui laisse
`isEnqueuingLinks` faux sans verdict linguistique — la liste est celle du 2026-08-14, pas une
garantie d'exhaustivité. Rapporter tout site supplémentaire trouvé.

**c. Le prédicat avant la porte.** Devant le test `nlpRejected` (`:692-693`) : si
`DetectionLangueClient.isTechnicalFailureMethod(detectResult.method)`, poser
`verdictUnavailable = true` et **ne pas appeler `checkUrl`**. C'est ce qui ferme la
résurrection `.fr` — `checkUrl` accepte tout hôte `.fr` sans travail réseau.

**d. Le garde du detect de page interne.** `:793-812` renvoie une page de challenge non
résolue à la détection et **remet `isEnqueuingLinks = true` si l'appel rend `ok`**, sans
garde. L'encadrer par `verdictUnavailable`.

**e. Scinder la branche terminale.** Insérer `else if (verdictUnavailable)` **avant** le
`else` de blanchiment (`:1138`) : un `log.warning` explicite, et **rien d'autre** — pas de
`filtered_nonfr`, pas de `Dataset.open("nfr-" + …)`, pas d'appel `updateChecker`.
**Vérifier la structure d'accolades** avant d'insérer : le `else` de `:1138` se referme sur
le `if (isEnqueuingLinks)` de `:823`, à confirmer dans le fichier.

**Non-régression prioritaire.** Un site réellement non francophone (`Check_nok_v2`) doit
conserver **exactement** le comportement d'aujourd'hui : compteur, `nfr-`, et en MAJ
`checkUrl(..., false)`. Le but n'est pas d'arrêter de filtrer.

**Tests.** `routes.ts` n'est pas testable en unitaire ici (il importe crawlee). Donc :
`npx tsc --noEmit` doit passer, et le rapport doit démontrer par **lecture du diff** que les
trois écritures sont inatteignables quand `verdictUnavailable` est vrai. Ne pas inventer un
harnais de test pour `routes.ts` dans ce chantier — le dire si ça manque, plutôt que de
fabriquer une couverture qui n'en est pas une.

---

## Tâche 3 — constat B : la propagation `?lang=fr`

**Fichier** `src/routes.ts`. Indépendante des tâches 1 et 2.

Remplacer la porte `if (primaryMethod === "pattern_match_query")` (`:636`) par un appel
**inconditionnel** à `DetectionLangueClient.extractLanguageQueryParam(site)` dans la branche
`detectResult.ok`, en assignant `context.languageQueryParam` si le retour est non nul.

Le helper s'auto-garde (`:201-218`) : il rend `null` sauf si la seed porte un
`lang|locale|language|hl` matchant `/^fr/i`. Conserver le `log.info` existant.

Pourquoi la porte est morte : `extractPrimaryMethod` préfère n'importe quelle méthode HTML
trouvée **n'importe où** dans le `+`-split, et la matrice de décision place `html_method`
avant la position 0 — donc `pattern_match_query+langHtml+nlp_confirmed` se réduit à
`langHtml` et le test est faux.

**Ne pas toucher** la branche jumelle `:706` (chemin `checkUrl`), correcte par accident parce
que `/check-url` rend des jetons nus.

**À signaler dans le rapport, pas à corriger** : la propagation se déclenchera désormais aussi
quand le verdict vient du TLD. L'injection est additive et seulement si absent, donc le rayon
d'action est un paramètre de requête en plus sur les URL internes — ce qui **change les clés
de dédup**. Le noter comme conséquence assumée, et vérifier si `QM_TIER2_ENABLED` a un
comportement qui en dépend.

**Test.** Ajouter un test de `extractPrimaryMethod` épinglant la réduction
`pattern_match_query+langHtml+nlp_confirmed` → `langHtml` : c'est *elle* qui rend la porte
morte, et c'est la seule moitié testable localement. Le changement dans `routes.ts` est
couvert par `tsc --noEmit` plus la lecture du diff.

---

## Documentation

`apps-microservices/crawler-service/CLAUDE.md` : consigner le nouvel état
`verdictUnavailable` et l'invariant, l'ensemble fermé du prédicat avec le statut de chaque
membre, et le changement de comportement de la propagation du paramètre de langue. Corriger
toute affirmation existante que ces changements rendent fausse — la règle du dépôt est de
réparer le `CLAUDE.md` dans le même commit que le code qui le contredit.

## Déploiement

Rebuild de `crawler-service`. Aucun changement de compose, aucun BO, aucune migration, aucune
coordination avec le service de détection.
