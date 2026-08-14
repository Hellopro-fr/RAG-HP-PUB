# Spec — « la détection n'a pas répondu » ≠ « le site n'est pas français »

**Date** 2026-08-14 · **Périmètre** `crawler-service` (`crawler/src/`) · **Statut** approuvée 2026-08-14

Cette spec traite les constats **A** et **B** de
`docs/superpowers/references/2026-07-29-crawler-detection-seam-audit.md`, la première
tranche que cet audit recommande lui-même. **Ne pas ré-auditer** : les 13 constats ont
survécu à une vérification adversariale (15/16), la référence est l'enregistrement durable.

Toutes les ancres de code citées ici ont été **re-vérifiées le 2026-08-14** (tableau §6) :
l'audit a été fait au tip `b4e70966` et le crawler n'a pas bougé depuis, mais le service de
détection **si** (§2).

---

## 1. Le défaut

Le crawler ne dispose d'aucun état pour « je n'ai pas obtenu de verdict ». Une panne de la
détection, un challenge anti-bot non résolu et un site réellement non francophone
convergent tous vers la même branche terminale, qui :

- incrémente `filtered_nonfr` — que le BO traduit en `isError='not_french'` ;
- pousse la page dans le dataset `nfr-{domain}` ;
- **en mode mise à jour, appelle `updateChecker.checkUrl(..., false)`** ⇒ `isEligible` faux
  ⇒ **`action:'deleted'` et une ligne dans `deleted_urls.jsonl`**.

Autrement dit : **un redémarrage de la détection pendant une MAJ émet des revendications de
suppression contre des fiches françaises vivantes.**

Le précédent existe une fonction plus haut. L'axe HTTP a été durci après l'**incident
1320-402** (63 refus anti-bot en 403 → 59 fausses suppressions) pour que seuls 404/410
puissent revendiquer une suppression — `UpdateChecker` ignore délibérément
`unverified_http_error_*`. Ce raisonnement n'a jamais été étendu à l'axe détection, qui est
une surface de panne **plus large** : une dépendance HTTP partagée au lieu de statuts par URL.

Sur un domaine non-`.fr`, le message posé est exactement `"Page non détectée en Français"`,
que `not_french_signal.php` (BO) croit **sans condition, avant tout test de compteur** — donc
un 500 côté détection, renvoyé en HTTP 200 avec `method='error'`, devient un verdict métier
permanent.

## 2. Ce qui a changé depuis l'audit — à re-dériver, pas à recopier

L'audit précède N1 (garde « pas de verdict linguistique sans texte », déployé le 2026-08-14).
N1 remplace `Check_nok_v2` / `nlp_not_confirmed` / `nlp_override_tld_fr` par
`fetch_empty_content` sur une page à **texte visible nul**. Deux conséquences directes ici :

1. **N1 a élargi le chemin de résurrection `.fr`.** La porte `nlpRejected` teste
   `nlp_not_confirmed` / `nlp_override`. Une page à texte nul qui rendait auparavant l'un des
   deux rend maintenant `fetch_empty_content` ⇒ `nlpRejected` devient **faux** ⇒ l'appel
   `checkUrl` s'engage ⇒ tout hôte `.fr` est accepté sans travail réseau.
2. **A et N1 se composent bien.** N1 rend le signal « illisible » explicite ; A l'empêche
   d'être blanchi en verdict. Traiter `fetch_empty_content` comme technique est *plus* juste
   après N1 qu'avant : la méthode signifie littéralement « nous n'avons pas pu lire la page ».

Corollaire : ne pas reprendre de l'audit la phrase « `fetch_empty_content` signifie une
homepage presque sans texte, donc sans liens à exploser en arbres de locales » comme si la
population était restée la même. Elle a grossi.

## 3. Périmètre

**Dedans** — constats A et B, tous deux dans `crawler/src/routes.ts` (+ un prédicat statique
dans `DetectionLangueClient.ts`), testables dans `DetectionLangueClient.test.ts` qui existe
déjà et tourne localement sans importer crawlee.

**Dehors, nommé pour ne pas être re-proposé :**

- **Le garde BO** (`fonctions_relaunch_on_eligible.php:251-253`) — même classe, 3 lignes,
  mais **bien plus bénin** : l'action y est déjà `blocked`, pas une suppression, et une
  branche « service indisponible » distincte existe déjà (`:246-250`). Le défaut est un
  *message* faux (« Homepage non FR — relance annulée ») quand la vraie cause est
  « illisible », et une relance annulée récupérable au prochain essai. Chantier séparé :
  autre dépôt, autre mécanisme de déploiement (MEP SFTP).
- Constats C à L de l'audit, avec leurs contraintes de séquencement (**A avant L**,
  **F avant ou avec A**, et **A tue l'item réfuté** — ne pas implémenter les deux).
- Le re-portage des familles de challenge manquantes dans la copie locale du crawler : A est
  le correctif racine, la copie locale dégrade alors en simple pré-filtre.

## 4. Constat A — un état « verdict indisponible »

### 4.1 L'invariant, pas les numéros de ligne

> **Aucune défaillance technique ne doit incrémenter `filtered_nonfr`, écrire dans
> `nfr-{domain}`, ni appeler `updateChecker.checkUrl`.**

C'est l'invariant à faire respecter. Les sites énumérés ci-dessous sont ceux connus au
2026-08-14 ; **l'implémenteur doit chercher tout autre chemin qui atteint la branche
terminale**, et non se limiter à cette liste. (Une spec qui nomme un numéro de ligne au lieu
d'un invariant a déjà laissé une boucle non bornée dans ce dépôt.)

### 4.2 Les trois pièces

**(a) Un drapeau `verdictUnavailable`**, déclaré à côté de `isEnqueuingLinks`
(`routes.ts:557`), initialisé `false`, positionné dans :

| Site | Ce qui s'y passe aujourd'hui |
|---|---|
| `:717-720` | `catch` du detect de homepage — seul `log.error` |
| `:768-770` | `catch` — seul `log.error` |
| `:817-819` | `catch` — seul `log.error` |
| `:739-741` | challenge non résolu — `isEnqueuingLinks = false` |
| `:788-790` | challenge non résolu — `isEnqueuingLinks = false` |

**(b) Un prédicat statique** `DetectionLangueClient.isTechnicalFailureMethod(m)`, sur un
ensemble **fermé**, appelé **avant** le test `nlpRejected` (`routes.ts:692`) : si la méthode
est technique, poser `verdictUnavailable` et **ne pas** appeler `checkUrl` — c'est ce qui
ferme la résurrection `.fr`.

Ensemble retenu : **`challenge_page`, `error`, `fetch_empty_content`** — les trois seules
méthodes d'échec technique réellement atteignables sur les appels du crawler — **plus
`admission_rejected`**, ajouté par précaution et inatteignable en l'état (voir la décision
ci-dessous).

Pourquoi seulement ces trois sont atteignables : le classifieur de challenge et le chemin
`error` tournent sur du html **fourni**, alors que `validate_page` et le repli homepage sont
enfermés dans `if not html_was_provided` — donc `soft_404`, `redirected_to_home`,
`http_error`, `http_error_transient` et `fetch_failed` **ne peuvent pas arriver** au crawler.
Ne pas les ajouter « au cas où » : l'ensemble doit rester lisible comme l'affirmation
vérifiable qu'il est, et chaque membre non atteignable doit porter la raison de sa présence.

> **Décision prise (2026-08-14) — `admission_rejected` EST dans l'ensemble.** Il n'est pas
> atteignable aujourd'hui : le crawler envoie `html_content`, donc il court-circuite le
> contrôle d'admission. Il y figure quand même, avec un commentaire disant explicitement
> qu'il est inatteignable en l'état, pour deux raisons — une saturation de service n'est
> jamais une propriété du site, et si un futur changement fait passer le crawler par
> l'admission, le blanchiment silencieux revient sans que personne ne relise ce prédicat.
> Le service le classe déjà lui-même dans `_NEVER_CACHE_METHODS` (« une saturation ne doit
> jamais être persistée comme réponse de domaine ») : l'ensemble fermé du crawler s'aligne
> sur ce jugement plutôt que de le contredire.
>
> Conséquence pour les tests : `admission_rejected` doit être épinglé comme technique, **et**
> un commentaire doit dire qu'aucun chemin ne l'atteint aujourd'hui — sinon un futur lecteur
> conclura à tort que le crawler l'observe en production.

**(c) Scinder la branche terminale.** Insérer un `else if (verdictUnavailable)` **avant** le
`else` de blanchiment (`routes.ts:1138`), qui journalise en `warning` et ne fait **rien
d'autre** : pas de compteur, pas d'écriture `nfr-`, pas d'appel `updateChecker`.

### 4.3 Un garde supplémentaire

`routes.ts:793-812` renvoie une page de challenge non résolue à la détection et **remet
`isEnqueuingLinks` à `true` si l'appel rend `ok`** — sans garde. À encadrer par
`verdictUnavailable`.

### 4.4 Effet de bord gratuit

Honorer le `challenge_page` du serveur importe son classifieur à 9 familles, maintenu. La
copie portée à la main du crawler (`functions.ts:233-320`) ignore `Rescaled_WAF`,
`JS_PoW_bot_check` et `Squid_proxy_error`, et resserre la regex de titre d'erreur à
`(403|401|406|429|503)` là où le service utilise `[45]\d{2}`. Ces familles sont **exactement**
celles qui atteignent le chemin de blanchiment.

### 4.4bis Le second canal : `crawlErrorMessage` (ajouté 2026-08-14 après la tâche 2)

L'invariant du §4.1 ne nomme que trois écritures. Il en manquait une quatrième, et c'est
celle que le §1 met en avant : `context.crawlErrorMessage = "Page non détectée en Français"`
(`routes.ts:704`), que `not_french_signal.php` croit **sans condition, avant tout test de
compteur**. Elle est posée *avant* le garde du §4.2, donc la tâche 2 seule laisse le BO
recevoir un faux `not_french` sur le chemin non-`.fr` — le but affiché du chantier n'est pas
atteint sans elle.

Portée réelle : l'affectation est gardée par `if (!context.crawlErrorMessage)`. Les méthodes
exposées sont **quatre**, pas trois — `error`, `fetch_empty_content`, `admission_rejected`,
**et `challenge_page`**.

> **Correction 2026-08-14 (tâche 3).** Une version antérieure de ce §4.4bis excluait
> `challenge_page` en disant qu'un challenge non résolu avait déjà posé son message en
> `:618`. Deux erreurs, et elles se contredisaient avec le §4.4 de cette même spec.
>
> 1. **Ce n'est pas le message qui protège ce cas, c'est le `return`.** `:618` pose son
>    message puis `:619-620` font `stopCrawler` + **`return`** : le contrôle n'atteint jamais
>    l'affectation, donc le garde `if (!...)` n'est même pas consulté. Raisonner sur le garde
>    était un contresens sur le mécanisme.
> 2. **Et ce chemin ne couvre que le challenge détecté par le CRAWLER.** Quand c'est le
>    *service* qui classe la page en `challenge_page` — ce qui arrive précisément pour les
>    trois familles que la copie portée à la main du crawler ignore, celles que le §4.4
>    énumère (`Rescaled_WAF`, `JS_PoW_bot_check`, `Squid_proxy_error`) — aucun message n'a été
>    posé avant, et la page était donc bien tamponnée « Page non détectée en Français ».
>
> Autrement dit le §4.4 (« effet de bord gratuit : honorer le `challenge_page` du serveur
> importe son classifieur ») et le §4.4bis se contredisaient : le premier disait que ces
> familles arrivent bien au crawler, le second supposait qu'elles ne pouvaient pas atteindre
> le message. Le premier avait raison.

Ce n'est **pas** un changement de contrat : le fichier pose déjà des messages distincts en
`:394` (`Erreur HTTP …`), `:583` et `:618`. Poser un message technique distinct suit ce motif
existant. Et une fois `filtered_nonfr` non incrémenté (tâche 2) **et** le message distinct,
les deux canaux se ferment ensemble — la branche compteur de `not_french_signal.php` ne peut
plus se rabattre dessus, puisque le §1 de cet audit note qu'elle se déclenchait justement
parce que `filtered_nonfr=1` et `nb_success_crawled=0`.

### 4.5 Cadrage à ne pas répéter

L'audit corrige une affirmation de sa propre synthèse : il est **faux** qu'un site `.fr`
muré par un WAF soit « crawlé de bout en bout avec l'interstitiel comme contenu de chaque
page ». Le handler qui écrit dans le dataset principal n'a qu'un site d'appel, **à
l'intérieur** de `if (isEnqueuingLinks)`. Les pages internes reçoivent aussi
`challenge_page`, donc elles n'entrent pas dans le dataset principal. **Seule la homepage
ressuscitée entre dans le plan de données RAG.** Les vrais dommages sont (1) le budget de
crawl brûlé avec un rapport SUCCESS, et (2) le tampon `not_french` permanent sur le chemin
non-`.fr` / détection-500. **Mener avec (2).**

> **Correction 2026-08-14 — ce paragraphe contredisait le §4.1, et la tâche 2 l'a relevé.**
> Une version antérieure disait que les pages internes « atterrissent dans `nfr-{domain}` »
> et présentait cela comme le dénouement bénin. Or c'est exactement ce que l'invariant du
> §4.1 **interdit**. La remarque de l'audit portait sur le *dataset principal* — elle
> réfutait la thèse « des ordures dans le plan RAG » — et non sur une approbation des
> écritures `nfr-`. Lu littéralement, ce §4.5 autorisait à n'implémenter que les pièces
> (a)–(e) puis à **déclarer l'invariant fermé alors qu'il restait ouvert sur les pages
> internes**, c'est-à-dire sur le volume : en mode MAJ, chacune est une revendication
> `action:'deleted'`. L'invariant prime — une page interne sans verdict n'est écrite ni dans
> `nfr-`, ni dans le compteur.

## 5. Constat B — la propagation `?lang=fr` est morte

`routes.ts:636` conditionne la capture du paramètre de langue à
`primaryMethod === "pattern_match_query"`. Mais `extractPrimaryMethod`
(`DetectionLangueClient.ts:170-176`) préfère **n'importe quelle** méthode HTML trouvée
**n'importe où** dans le `+`-split, et la matrice de décision place `html_method` avant la
position 0. Donc `pattern_match_query+langHtml+nlp_confirmed` se réduit à `langHtml`, le test
est faux, et `context.languageQueryParam` n'est jamais assigné.

La ré-injection (`:1021-1027`) est alors inopérante, chaque lien découvert perd le paramètre,
le serveur sert sa langue par défaut, et le `forced_method` `langHtml` stocké rejette chaque
page — **droit dans la branche A**. Net : le crawl complet d'un site réellement français ne
rend presque aucune page française, avec un `filtered_nonfr` gonflé et un mauvais signal BO.

**Correctif retenu** — appeler `DetectionLangueClient.extractLanguageQueryParam(site)` sans
condition dans la branche `detectResult.ok` et assigner si non nul. Le helper s'auto-garde
déjà (`:201-218`) : il rend `null` sauf si la seed porte un `lang|locale|language|hl` qui
matche `/^fr/i`. Deux lignes.

*Forme alternative* — tester `detectResult.method.split("+").includes("pattern_match_query")`.
Elle marche aussi et reste juste à mesure que de nouvelles méthodes `+`-composées
apparaissent. **Choisir la première** : elle ne dépend d'aucune connaissance de la
composition des méthodes, dont §2 montre justement qu'elle bouge.

**Portée** — la porte morte ne mord qu'à l'intersection « la seed porte `?lang=fr` » **et**
« la homepage déclare un `<html lang>` français ». Sans la balise, `parts[0]` gagne et la
propagation marche déjà. Cette intersection est la forme CMS-i18n courante, et quand elle
frappe, tout le crawl est perdu.

**Risque** — la propagation se déclenchera aussi quand le verdict vient du TLD. L'injection
est additive et seulement si absent, donc le rayon d'action est un paramètre de requête
supplémentaire sur les URL internes — ce qui **change les clés de dédup** et la surface des
paramètres `?`.

**Correction de ce paragraphe (2026-08-14).** « À surveiller si `QM_TIER2_ENABLED` est actif »
sous-évaluait le rayon d'action : le vrai danger n'est **pas** derrière ce drapeau. L'arrêt
`limitQuestionMark` vit dans un `postNavigationHook` inconditionnel
(`functions.ts:901-910`) : `shouldStopForQuestionMark(context.countQuestionMark, …, 100)`
termine le crawl avec `isError=limitQuestionMark`, et ses **deux** échappatoires valent `false`
par défaut — `bypassQuestionMark` et `skipQuestionMark` (`context.ts:41-43`,
`main.ts:104-106`). Le compteur, lui, s'incrémente sur `url.includes('?')` dans
`routes.ts`, donc l'injection ajoutait un `?` à **chaque** page et l'arrêt tombait à la
100ᵉ : en configuration par défaut, la propagation tuait le crawl des sites qu'elle devait
sauver. Ce n'était pas une surveillance, c'était un correctif dû.

**Correctif** — `DetectionLangueClient.stripInjectedLanguageParam(url, param)` (statique, pure)
retire la paire clé+valeur **exacte** que nous avons injectée, et rend une URL sans `?` du tout
s'il ne reste plus rien. `routes.ts` en dérive `facetUrl` une fois et le donne à **toute** la
machinerie `?` : `trackQmHashStatsForUrl`, `countQuestionMark`, `recordVariant`,
`recordQuestionMarkObservation`, et l'échantillon tier-2. Motif : cette machinerie mesure une
explosion de l'espace des paramètres **produite par le site** ; compter un paramètre que le
crawler a lui-même ajouté est une erreur de catégorie. Le reste du handler garde `url`, qui
reste l'identité stockée et comptée de la page. Le match exact clé **et** valeur préserve le
`?lang=de` du site, qui continue d'incrémenter le compteur.

**Risque latent connu, non refermé — `QM_TIER2_ENABLED` (défaut `false`).** Lecture de chemin
de code, **pas une observation** : aucun run ne l'a produit, rien n'est mesuré ici.
`candidateParams()` (`questionMarkTier2.ts:37-46`) ne filtre que sur `decided`, `toRemove` et
`toKeep` — **aucune liste blanche de langue**. Trié par fréquence décroissante, `lang` peut
donc devenir le candidat de tête, et un verdict `same`-majoritaire le commite dans `toRemove`
via `commitToRemoveParam`, qui **réécrit aussi la file** : le paramètre serait alors retiré en
cours de crawl et le correctif ci-dessus annulé. Le `facetUrl` réduit l'exposition — `lang=fr`
que nous injectons n'entre plus dans `paramFrequency` — mais ne la ferme pas : les pages
portant le `?lang=de` du site l'y font entrer. Une liste blanche taillée pour exactement ça
existe déjà un module plus loin, `MEANINGFUL_OPTIONAL_PARAMS` (`filterOnSeen.ts:10` :
`lang`, `hl`, `devise`, `currency`, `region`) et tier-2 ne la consulte pas — noter au passage
qu'elle ignore `locale` et `language`, deux des quatre clés qu'`extractLanguageQueryParam`
accepte. Refermer avant toute activation de `QM_TIER2_ENABLED`.

## 6. Ancres re-vérifiées le 2026-08-14

| Fait | Emplacement | Vérifié |
|---|---|---|
| `let isEnqueuingLinks = false` | `routes.ts:557` | ✓ |
| porte `nlpRejected` (`nlp_not_confirmed` / `nlp_override`) | `routes.ts:692-693` | ✓ mot pour mot |
| affectations `isEnqueuingLinks` | `:642, 711, 740, 775, 789, 811` | ✓ |
| `if (isEnqueuingLinks)` | `routes.ts:823` | ✓ |
| branche terminale : `filtered_nonfr`, `nfr-`, `updateChecker.checkUrl(..., false)` | `routes.ts:1138-1161` | ✓ |
| porte du paramètre de langue | `routes.ts:636`, assignation `:637`, jumelle `:706` | ✓ |
| ré-injection | `routes.ts:1021-1027` | ✓ |
| `extractPrimaryMethod` + `HTML_METHODS` | `DetectionLangueClient.ts:170-176`, `:173` | ✓ |
| `requiresNlpValidation` | `DetectionLangueClient.ts:186-188` | ✓ |
| `extractLanguageQueryParam` | `DetectionLangueClient.ts:201-218` | ✓ |
| `isTechnicalFailureMethod` | **absent** — à créer | ✓ |
| fichier de test | `DetectionLangueClient.test.ts` existe | ✓ |

## 7. Critères d'acceptation

1. `isTechnicalFailureMethod` rend vrai pour chaque membre de l'ensemble fermé et **faux**
   pour `Check_nok_v2`, `nlp_not_confirmed`, `nlp_override_tld_fr` — les trois verdicts
   linguistiques de l'allowlist `DETECTION_LANGUAGE_VERDICTS` du BO. Un test qui n'épingle
   pas ce **faux** ne garde rien : c'est la frontière entre panne et verdict.
2. Sur `method='error'`, la branche terminale n'incrémente pas `filtered_nonfr`, n'ouvre pas
   `nfr-{domain}` et n'appelle pas `updateChecker.checkUrl`.
3. Un `fetch_empty_content` sur un hôte `.fr` **n'atteint plus** `checkUrl` — la résurrection
   est fermée.
4. Un site réellement non francophone (`Check_nok_v2`) conserve **exactement** le
   comportement d'aujourd'hui : compteur, `nfr-`, et en MAJ l'appel `checkUrl(..., false)`.
   C'est la non-régression qui compte le plus — le but n'est pas d'arrêter de filtrer.
5. B : une méthode `pattern_match_query+langHtml+nlp_confirmed` assigne bien
   `context.languageQueryParam` quand la seed porte `?lang=fr`.
6. Chaque test doit **échouer** si on retire le code qu'il garde. Le vérifier explicitement :
   deux tests d'un chantier précédent passaient sans leur correctif.

## 8. Déploiement

Rebuild du `crawler-service`. Aucun changement de compose, aucun changement BO, aucune
migration. **Aucune coordination avec le service de détection** : ces changements sont
purement côté appelant.

À surveiller au premier run après déploiement : le `filtered_nonfr` du rapport doit **baisser**
sur les lots où des pannes de détection se produisent, et `deleted_urls.jsonl` ne doit plus
recevoir de lignes attribuables à une indisponibilité. Un `filtered_nonfr` qui ne bouge pas du
tout est un signal qu'aucune panne n'a eu lieu pendant le run, pas que le correctif est
inerte — ne pas confondre les deux.
