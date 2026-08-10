# Faux négatifs de détection FR — design

**Date** : 2026-08-10
**Service** : `api-detection-langue-fr` (Python, RAG-HP-PUB `features/poc`)
**Statut** : design approuvé, non implémenté

---

## 1. Le problème, et comment il a été trouvé

Sur le run du 2026-08-10 (`[SCRIPT] Traitement crawling — FR:6 | NonFR:7 | Indet:51 | Err:40`, 104 domaines), l'opérateur a vérifié **à la main** quatre domaines classés non-français. **Les quatre sont français.**

| ID | Domaine | Verdict du service | Réalité constatée par l'opérateur |
|---|---|---|---|
| 324 | `automatismes.net` | `Check_nok_v2` | FR |
| 2493 | `groupe-denis.com` | `Check_nok_v2` | `http://` → `https://ibyd.fr/` → FR |
| 6351 | `rgb-solutions.green` | `Check_nok_v2` | `https://rgb-solutions.green/` (apex) → FR |
| 346 | `sfte-shop.fr` | `fetch_empty_content` | `http://www.` → `https://sftefrance.fr/` → FR |

`Check_nok_v2` représentait **5 des 7 verdicts « non-FR »** du run. Trois des cinq ont été vérifiés, et les trois sont faux. C'est un taux qu'aucune revue de code n'aurait révélé.

**Pourquoi c'est plus grave que les 40 erreurs d'infrastructure du même run** : celles-ci sont rejouables (`error` et `fetch_failed` ne sont jamais mis en cache), tandis qu'un `Check_nok_v2` sur un domaine français est un prospect perdu **et** un verdict faux figé 7 jours (`domain_fr.py:49`, `TTL_NOK`, la méthode n'étant ni dans `_NEVER_CACHE_METHODS` ni dans `_TRANSIENT_METHODS`).

## 2. Deux défauts distincts, pas un

### 2.1 Défaut A — la variante d'URL n'est jamais tentée sur un fetch réussi

`scrape_html` considère un fetch réussi dès que le **HTML brut** dépasse 100 caractères (`scraper.py:575` `if content and len(content) > 100`) — pas le texte visible. Et la Phase 2 de `fetch_html` (variantes `http`/`https`, `www`/apex) ne se déclenche **que si la Phase 1 échoue** : un `return result` en sort avant.

Conséquence : une page récupérée mais inexploitable verrouille la forme d'URL testée. Or c'est exactement le cas où la variante répare — quand la redirection vers le vrai site n'existe que sur `http` (2493, 346) ou sur l'apex (6351).

**Contrainte structurelle** : `fetch_html` ne peut pas connaître le verdict, qui naît de la matrice de décision *après* le fetch. Le rattrapage doit donc vivre plus haut, là où verdict et URL coexistent.

### 2.2 Défaut B — le signal lexical n'est pas consulté quand fastText se trompe avec assurance

Sondé sur `automatismes.net` : **aucun** `html lang`, **aucun** hreflang, TLD `.net` — donc zéro signal URL et zéro signal HTML — mais 3 500 à 4 000 caractères de français limpide, page rendue côté serveur. Verdict : `Check_nok_v2`.

Le mécanisme :
- le **Cas 7** exige un indicateur HTML ou URL (`domain_fr.py`, `if nlp_available and (html_indicates_french or url_indicates_french)`) — absent ici ;
- le **Cas 8**, seul à consulter le signal lexical, est gardé par `soft_from_fasttext`, qui exige que **fastText ait dit `fr`**. Ce garde a été ajouté au chantier soft-French du 2026-07-29 précisément pour empêcher le lexical d'outrepasser le NLP, et son propre commentaire le dit : « fastText ne laisse jamais le signal lexical changer le label ».

Donc si fastText tranche pour une autre langue avec assurance, le signal lexical n'est **jamais lu**, quelle que soit la quantité de français sur la page.

`6351` est **ambigu** entre A et B : son apex est français sans `html lang` (profil de 324), et la forme `www` testée par le service n'a pas pu être sondée. Le discriminant serait `/detect-debug` sur les deux formes.

## 3. Mesure : quel discriminant lexical est utilisable

`_compute_french_signal` (`language_detector.py:288-317`) compte séparément les mots **exclusivement** français (poids 2,0) et les mots **partagés** avec les langues romanes (poids 0,5), puis ne publie que le score agrégé — `details` ne porte que `french_signal` (`:687`).

Mesuré le 2026-08-10 en rejouant le calcul sur les listes réelles du service :

| Échantillon | mots | exclusifs (occurrences) | **exclusifs distincts** | signal agrégé |
|---|---|---|---|---|
| FR `automatismes.net` (extrait réel) | 63 | 22 | **15** | 1.000 |
| FR `rgb-solutions` (extrait réel) | 45 | 9 | **9** | 1.000 |
| Espagnol | 46 | 0 | **0** | 0.761 |
| Italien | 42 | 0 | **0** | 0.238 |
| **Portugais** | 30 | 1 | **1** | **1.000** |
| Anglais | 30 | 0 | **0** | 0.000 |
| FR catalogue sans prose | 19 | 0 | **0** | 0.000 |

Trois conclusions, toutes portantes :

1. **Le score agrégé est inutilisable comme discriminant.** Il sature à 1.000 pour le portugais comme pour le français, et le seuil `> 0.3` du Cas 8 (`domain_fr.py:1633`) laisserait passer l'espagnol à 0.761.
2. **Le compte de mots exclusifs distincts sépare nettement** : 9 à 15 pour le français, 0 à 1 pour tout le reste.
3. **Un seuil à 1 serait faux** : le portugais marque 1, via le mot `mais` (« plus » en portugais), présent dans `FRENCH_EXCLUSIVE_STOPWORDS`. Les données pointent vers **≥ 5 distincts**.

**Limite honnête** : un catalogue français sans prose (uniquement des noms de produits et de marques) marque **0**. Ce rattrapage ne sauvera que les pages contenant du texte rédigé — il ne faut pas en attendre autre chose.

**Faiblesse de cette mesure, et raison du choix d'observation** : six textes courts, dont quatre rédigés par l'assistant. Le seuil de 5 est plausible, pas éprouvé. C'est pourquoi le volet B est livré **inerte** (§5).

---

**Correction du 2026-08-10 (post-implémentation).** Les chiffres du tableau
ci-dessus — en particulier les valeurs 15, 9, 0.761 et 1.000 (PT) — viennent
d'extraits qui n'ont **pas été conservés** mot pour mot : ils ne sont pas
reproductibles et ne doivent plus être cités comme référence. L'implémenteur
et le relecteur du volet B ont chacun, **indépendamment**, rejoué
`_compute_french_signal` et `_count_french_exclusive_distinct` sur les
échantillons durables du dépôt (`tests/test_lexical_observation.py`), avec
accord exact entre les deux mesures :

| Échantillon | signal agrégé (`french_signal`) | exclusifs distincts |
|---|---|---|
| FR (prose) | 1.000 | **8** |
| ES (prose) | 0.833 | 0 |
| PT (prose) | 0.814 | 1 (`mais`) |
| IT (prose) | 0.417 | 0 |
| EN (prose) | 0.000 | 0 |
| FR catalogue (sans prose) | 0.000 | 0 |

C'est cette table qu'il faut citer désormais, pas les 15/9/0.761/1.000
d'origine — ceux-ci restent ci-dessus comme trace de ce qui a motivé la
décision au moment où elle a été prise, non comme référence chiffrée. Les
conclusions ne changent pas : la conclusion 1 (score agrégé inutilisable comme
discriminant) est même **renforcée** — l'espagnol mesuré à 0.833 dépasse le
plancher `> 0.3` du Cas 8 encore plus largement que le 0.761 d'origine. La
conclusion 2 (le compte de distincts sépare nettement) tient aussi : 8 pour le
français contre 0 ou 1 pour tout le reste. La conclusion 3 (`mais` faussement
exclusif, seuil à 1 invalide) est inchangée. Table publiée aussi dans le
`CLAUDE.md` du service, section « Lexical-Signal Observation at Case 9
(inert) ».

**Corroboration indépendante — un TROISIÈME jeu de valeurs, sur un TROISIÈME
jeu d'échantillons.** Le chantier soft-French antérieur
(`docs/superpowers/specs/2026-07-28-detection-soft-french-lexical-corroboration-design.md`,
§ mesure du 2026-07-29) a rejoué le même `french_signal` sur SES propres
échantillons et mesuré : espagnol (prose industrielle) **0.990** avec ZÉRO mot
exclusivement français (19 correspondances sur les mots partagés
`de`/`la`/`le`/`un`), espagnol (e-commerce) 0.679, portugais **0.407**,
italien 0.275, anglais 0.000, la page française cible 1.000. Ni ce jeu de
valeurs (0.990/0.407…) ni les deux précédents (0.761/1.000 d'origine ;
0.833/0.814 réel-repo) ne coïncident — trois mesures indépendantes, trois jeux
de valeurs distincts. Ce n'est pas une contradiction à trancher : c'est en
soi une preuve supplémentaire que l'agrégat est fortement dépendant de
l'échantillon — ce qui RENFORCE, plutôt qu'affaiblit, la conclusion qu'il ne
peut pas servir de discriminant.

## 4. Volet A — rattrapage par variante d'URL (actif)

**Emplacement** : `_detect_single_url` dans `app/api/routes.py`, juste après le premier `check_page_if_french` (`:400`). C'est le seul point où le verdict et l'URL demandée coexistent.

**Déclenchement** : le verdict est `Check_nok_v2` **ou** `fetch_empty_content`, et aucune variante n'a encore été tentée.

Périmètre retenu après arbitrage sur les six familles du run :

| Verdict | Volume | Retenu ? | Raison |
|---|---|---|---|
| `Check_nok_v2` | 5 | **oui** | cas 2493 et 6351 ; seul verdict caché 7 jours |
| `fetch_empty_content` | 8 | **oui** | cas 346 |
| `http_error` | 3 | non | gain supposé, aucun cas mesuré |
| `challenge_page` | 13 | non | un WAF protège en général les deux formes : plus gros volume, gain le moins attesté |
| `http_error_transient` | 11 | non | condition serveur, pas une question de forme d'URL |
| `error` (timeout 300 s) | 7 | non | le budget est déjà épuisé par construction |

**Mécanique** : réutiliser `_generate_url_variants` (`redirect_tracker.py:163`, fonction pure de module déjà utilisée par la Phase 2). Pour chaque variante, **un seul fetch** — pas la cascade de `HTTP_MAX_RETRIES` — suivi d'une passe de détection. La première variante qui rend `ok=True` gagne ; les suivantes ne sont pas tentées.

**Budget horloge, qui sert aussi de kill-switch** : un nouveau réglage `VARIANT_RESCUE_BUDGET_S` (défaut **120**) vérifié **avant** chaque variante. Dépassé, on rend le verdict d'origine inchangé. Sans ce garde, un domaine pourrait consommer 4 fetchs (1 réussi + 3 variantes) et heurter le `wait_for` de 300 s par item (`routes.py`), transformant un `Check_nok_v2` en `error` — une régression pire que le défaut, puisque `error` ne porte ni cause ni retry. Mettre le budget à `0` désactive le rattrapage sans code mort ni flag supplémentaire.

**Résultat en cas de succès** : `ok=True`, `url` = la variante retenue, `analyzed_url` = la même — c'est le mécanisme déjà employé par le repli homepage (`routes.py:321`, `:336`), qui existe précisément pour dire « l'URL analysée diffère de l'URL demandée ». La clé de cache reste l'URL d'origine (`domain_cache.set(url, effective_url, …)`).

**Traçabilité** : le `method` est suffixé `+variant_rescue`, pour que le rattrapage soit mesurable dans le rapport BO sans aucun changement côté BO.

**Hors périmètre** : ne touche ni la Phase 2 de `fetch_html`, ni la garde `variant_pointless`, ni les quatre familles écartées ci-dessus.

## 5. Volet B — observation du signal lexical (inerte)

Trois pas, aucun changement de verdict :

1. **Exposer le discriminant.** `_compute_french_signal` publie le nombre de mots exclusifs **distincts** dans `details`, à côté de `french_signal` qui reste inchangé.
2. **Diagnostiquer au Cas 9.** Quand ce compte atteint un seuil d'observation bas — **≥ 3** — écrire dans le champ `error` du verdict : `"lexical: N mots exclusifs distincts — rattrapage candidat"`.

   > **Deux seuils distincts, à ne pas confondre.** Le **seuil d'observation (3)** décide seulement de l'affichage du diagnostic : il est délibérément plus permissif que nécessaire pour faire apparaître les cas limites — notamment ceux situés entre le portugais (1) et le français mesuré (9 à 15) — puisque rien n'est activé et qu'aucun verdict ne change. Le **seuil d'activation** que le §3 situe à ≥ 5 n'est **pas** implémenté par ce chantier : il sera fixé plus tard, sur les comptes réellement observés en production. Écrire 3 ici et 5 plus tard n'est pas une incohérence, c'est la différence entre regarder et décider.
   >
   > *(Le « français mesuré (9 à 15) » ci-dessus est le chiffre d'ORIGINE, non reproductible — voir la note de correction du 2026-08-10 au §3 : valeur reproductible actuelle = 8. Les conclusions de ce paragraphe ne changent pas.)*
3. **Ne rien décider.** `ok=False`, `method='Check_nok_v2'` : identiques à aujourd'hui.

**Pourquoi le champ `error`** : le Cas 9 (`domain_fr.py:1661-1665`) ne le renseigne pas — vérifié, la colonne « Erreur » est vide pour les 5 `Check_nok_v2` du run — et le BO l'affiche déjà dans le tableau des jugés. Zéro changement de contrat, visible au prochain run, aucune modification côté BO.

**Hors périmètre** : ni le Cas 8 ni son garde `soft_from_fasttext` ne sont modifiés. Aucun verdict ne change. L'activation éventuelle sera décidée sur les données d'un run réel, avec vérification manuelle de quelques cas — la démarche qui a déjà payé deux fois sur ce chantier.

## 6. Tests

**Volet A** :
- le budget est respecté : au-delà, le verdict d'origine est rendu **inchangé**, jamais un timeout ;
- `analyzed_url` porte la variante retenue, et `url` aussi ;
- le `method` est suffixé `+variant_rescue` ;
- aucune variante n'est tentée pour `http_error`, `challenge_page`, `http_error_transient`, `error` ;
- une variante coûte **un** fetch, pas la cascade ;
- la première variante en succès arrête la boucle.

**Volet B** :
- le compte d'exclusifs distincts sur les échantillons mesurés au §3 (FR réel 9 et 15 ; ES, IT, EN 0 ; PT 1) ;
- le verdict et la méthode sont identiques avec et sans le calcul ;
- l'`error` est posé au-delà du seuil, absent en dessous ;
- un texte de moins de 10 mots ne produit aucun diagnostic (le calcul rend déjà 0.0 dans ce cas).

## 7. Décisions utilisateur (déjà prises)

- **Priorité** : les faux négatifs avant les 40 erreurs d'infrastructure — « un faux négatif est pire qu'une absence de verdict », le second étant rejouable.
- **Découpage** : une seule spec, deux volets nettement séparés (fichiers et risques disjoints), un seul rebuild.
- **Périmètre de A** : `Check_nok_v2` + `fetch_empty_content` — le plus petit périmètre couvrant des cas mesurés.
- **Livraison de B** : en observation d'abord, verdict inchangé.

## 8. Déploiement

Un seul rebuild Docker du service sur la VM. **Aucun BO, aucune migration.** B est inerte par construction ; A se neutralise en mettant `VARIANT_RESCUE_BUDGET_S=0`.

## 9. À vérifier avant / pendant l'implémentation

1. **`6351` reste ambigu** entre A et B. Le discriminant est `/detect-debug` sur `https://www.rgb-solutions.green` et sur l'apex. Ne pas le compter comme un succès de A sans cette vérification.
2. **Le seuil de 5 exclusifs distincts n'est pas éprouvé** : six textes courts, quatre rédigés par l'assistant. C'est la raison d'être du mode observation.
3. **Le mot `mais` dans `FRENCH_EXCLUSIVE_STOPWORDS`** est un faux exclusif (portugais courant). À traiter séparément : le retirer changerait le score agrégé, donc le comportement du Cas 8 déjà déployé — hors périmètre ici.
4. **Le coût réel d'un fetch** n'a pas été mesuré sur la VM. Le défaut de 120 s pour le budget est une estimation ; à réviser après un run.
5. **`analyzed_url` sur un rattrapage cross-domaine** : quand la variante redirige vers un autre domaine (2493 → `ibyd.fr`), vérifier ce que les appelants font de cette valeur — le BO a déjà un chantier « cross-domain result pairing » et un garde de déduplication à l'insertion.

## 10. Références

- Run analysé : mail `19febca1d861ddec` du 2026-08-10 15:08
- Rapport séparant jugés et indéterminés : BO `802993a1`, déployé 2026-08-06
- Chantier soft-French et son garde `soft_from_fasttext` : `docs/superpowers/specs/2026-07-29-*` et mémoire `project_detection_soft_french_lexical_corroboration`
- Cause d'échec de fetch (`failure_detail`) : `docs/superpowers/specs/2026-08-06-detection-failure-cause-and-retire-proposal-design.md`
