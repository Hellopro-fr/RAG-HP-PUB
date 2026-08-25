# Cause d'échec de fetch et proposition de retrait de domaine — design

**Date** : 2026-08-06
**Services** : `api-detection-langue-fr` (Python, RAG-HP-PUB `features/poc`) + BO Marketplace (PHP 7.4, `master`)
**Statut** : design approuvé, non implémenté

---

## 1. Le problème

Un domaine dont le DNS n'existe plus et un domaine dont le proxy a eu un hoquet
produisent **exactement le même verdict** : `method='fetch_failed'`,
`error='Impossible de récupérer le contenu HTML'`.

Mesuré en production le 2026-08-06 : `distritel.fr` est un `getaddrinfo ENOTFOUND`
(le domaine a disparu) et porte le même verdict que 17 autres domaines du même lot,
dont certains sont probablement vivants.

Conséquence directe : **aucun retrait automatique de domaine mort n'est branchable**
sans risquer de retirer des domaines vivants — la classe exacte de l'incident 1320-402
(confondre « nous n'avons pas pu répondre » avec « la réponse est négative »).

### Ce que le rapport crawling sait déjà faire

Depuis le déploiement du 2026-08-06 (commit BO `802993a1`), le rapport sépare
« Non-FR jugés » des « Indéterminés » et alerte au-delà de 30 % du lot. Sur le run du
2026-08-05, 92 « Non-FR » ne portaient que **14** verdicts linguistiques ; les 78 autres
étaient des échecs de collecte. Ce chantier donne une **cause** à ces 78.

---

## 2. Ce que l'investigation a réfuté

Deux formulations initiales de ce design étaient fausses. Elles sont consignées ici
parce que les reprendre coûterait un cycle.

### 2.1 « Il suffit d'exposer `last_error` »

**Faux.** `scrape_html` n'attrape et ne relève une erreur de navigation que pour quatre
codes **Chromium** (`app/services/scraper.py:137-142`, `:444-446`). Toute autre erreur
de `page.goto` est **avalée** (`:448-449`, simple `logger.warning`) ; la fonction
poursuit, tente une extraction partielle, ne trouve pas de contenu et retourne `None`
(`:558-560`). `app/services/redirect_tracker.py:251` traduit alors ce `None` en
`"Contenu vide ou trop court"`.

Le moteur déployé est **Camoufox/Firefox** (`app/core/config.py:30`
`CAMOUFOX_ENABLED: bool = True`). Donc en production, exposer `last_error` tel quel
annoncerait « contenu vide » pour un DNS mort. **La cause réelle n'existe aujourd'hui
que dans une ligne de log.**

Effets de bord découverts au même endroit :
- `_FATAL_ERRORS` (`redirect_tracker.py:20-24`) est **du code mort** : `scrape_html` ne
  lève jamais ces messages, elle retourne `None` après un log. Un proxy invalide se
  présente donc aussi comme « Contenu vide ou trop court ».
- En **Phase 2** (variantes d'URL), les exceptions n'alimentent même pas `last_error`
  (`redirect_tracker.py:329-334`, aucun `last_error = ...`) : la cause de la dernière
  tentative réelle est perdue avant le `return None` final.

### 2.2 « Exiger la cause sur deux runs espacés »

**Inopérant ici.** Le script est déclenché à la main :
`docs/pipelines/A-lancement-crawl-initial.md:549` (Marketplace) — « Pas de cron, pas de
lock file », déclencheur CLI opérateur. Un seuil multi-runs ne se remplirait que si
l'opérateur relançait délibérément le même lot. Le garde-fou contre les faux positifs
est **la validation humaine de la liste**, pas un compteur.

### 2.3 Le libellé Gecko du DNS introuvable n'est attesté nulle part

Un seul libellé Gecko est adossé à une observation de production :
`page.goto: NS_ERROR_PROXY_CONNECTION_REFUSED`
(`docs/superpowers/specs/2026-06-16-crawler-failure-recovery-design.md:10-11`, panne du
gateway proxy sur `headpowerac.net`, 27 URLs).

`NS_ERROR_UNKNOWN_HOST` n'apparaît que dans **un test écrit à la main**
(`tests/test_variant_gate.py:62`), dans le plan qui commandait ce test, et dans une spec
qui l'affirme sans preuve — laquelle déclare elle-même le token non vérifiable sur cette
machine (`docs/superpowers/specs/2026-08-03-detection-teardown-flood-and-retry-cascade-cost-design.md:131`).
C'est une **supposition circulaire**.

Trois listes de codes **Chromium** sont mortes sur le moteur déployé, dans deux services :
`_VARIANT_ELIGIBLE_ERRORS` et `_PERMANENT_NAV_ERRORS` (détection), `PERMANENT_ERROR_MARKERS`
(`crawler-service/crawler/src/httpStatusPolicy.ts:138-146`). **Deviner un libellé est le
mode d'échec que ce design évite**, et c'est la raison de tout son découpage.

> **Correction (2026-08-07, relevée à l'implémentation).** Une version antérieure de ce
> document rangeait `_FATAL_ERRORS` parmi les « listes de codes Chromium ». C'est faux et
> trompeur : cette liste contient des chaînes **françaises propres au service**
> (`'Proxy non configuré'`, `'Proxy obligatoire'`, `'Proxy invalide'`,
> `redirect_tracker.py:20-24`), aucun code `ERR_*`. Elle est morte pour une raison
> **différente** — `scrape_html` retourne `None` au lieu de lever sur ces cas
> (`scraper.py:393-400`), donc la branche `except` qui la teste est inatteignable.
> La conséquence pratique compte : y ajouter des codes Gecko ne la réparerait pas.
> Les deux familles de mort ne se corrigent pas de la même façon.

---

## 3. Périmètre

### Dans le périmètre

- **B1** — faire remonter la cause brute d'un échec de fetch jusqu'à l'appelant HTTP.
- **B2** — un script BO qui **propose** une liste de domaines à retirer et n'écrit rien
  sans `--apply`, avec une liste de causes **vide à la livraison**.

### Hors périmètre (explicitement)

- Toute **classification** de cause (`permanent`/`infra`/…) : exige les vrais libellés.
- La **réparation des trois listes Chromium mortes** : même raison. Elles restent mortes.
- Le branchement sur le seam `not_french` (`fonctions_scrapping.php:1179`) : cause
  linguistique, pas mortalité — chantier distinct.
- Un état « refusé » persistant pour un candidat écarté par l'humain (voir §7).
- Toute interface graphique.
- Deux chemins de la détection restent **muets** : l'échec réseau du repli homepage
  (`app/api/routes.py:270-280`, qui produit `method=<verdict de validation>` et non
  `fetch_failed`) et le saut de stub (`:357-367`). Signalé pour que ce ne soit pas une
  surprise ultérieure.

---

## 4. B1 — la cause remonte jusqu'à l'appelant

### 4.1 Contrainte de conception

À `scraper.py:448-449`, après l'erreur de navigation, **le code continue volontairement
et tente une extraction partielle**. Lever une exception à cet endroit supprimerait ce
rattrapage : régression silencieuse sur les pages lentes mais lisibles.

`scrape_html` conserve donc **exactement** son type de retour
(`Optional[ScrapeResult]`) et reçoit un paramètre optionnel de collecte.

> Compromis assumé : un type de retour riche (`ScrapeOutcome`) serait plus élégant mais
> imposerait de toucher tous les appelants et leurs tests, pour une valeur que seul
> `fetch_html` consomme.

### 4.2 `scraper.py` — capture

Nouveau paramètre `error_sink: Optional[dict] = None`. Quand il est fourni, il est
rempli **avant** chaque retour d'échec :

| Site | Ligne | `stage` |
|---|---|---|
| Erreur de navigation avalée (**la cause qui manque**) | `:448-449` | `navigation` |
| Contenu absent ou trop court | `:558-560` | `content` |
| Proxy absent / invalide | `:393-400` | `proxy` |
| Playwright absent | `:386-391` | `runtime` |

Forme écrite : `{'cause': <str>, 'stage': <str>}`.

- `cause` = **première ligne** du message (`err_str.splitlines()[0]`, le précédent
  existe déjà à `:445`), tronquée à **200 caractères**. Sans cela on injecterait le
  call-log Playwright multi-lignes dans chaque réponse HTTP et dans le cache Redis.
- `stage` est déduit du **site d'écriture dans le code**, jamais d'une analyse du texte.
  C'est ce qui garantit qu'aucun libellé n'est présupposé.

Le comportement de retour ne change pas : sink absent ⇒ comportement actuel à
l'identique.

### 4.3 `redirect_tracker.py` — propagation

`fetch_html` reçoit le même paramètre optionnel, fournit son **propre** sink à chaque
appel de `scrape_html`, et retient la dernière cause non vide.

Points à câbler, parmi les 4 `return None` recensés : `:224` (proxy absent), `:307`
(garde `variant_pointless`), `:340` (fin de fonction — **cas dominant**).

Le 4e, `:269` (branche `_FATAL_ERRORS`), n'est **pas** câblé : §2.1 établit qu'il est
inatteignable, donc le câbler produirait du code non testable. Si la branche redevient
vivante un jour, le champ vaudra `None` — dégradation propre.

**La boucle Phase 2 (`:329-334`) doit aussi renseigner la cause** : c'est le trou
identifié en §2.1, sans quoi le champ portera la cause de Phase 1 alors que des
variantes ont été tentées après.

### 4.4 `routes.py` + `schemas.py` — exposition

`DetectionResponse` (`app/models/schemas.py:88-112`) gagne :

```python
failure_detail: Optional[str] = None
```

Câblé au site `fetch_failed` de `routes.py:202-205` et à son miroir debug `:858-864`.

**Pourquoi un champ dédié et non `error`** : `error` est un message destiné à l'humain,
recopié dans des fichiers de trace côté BO
(`script/chatgpt/script_launch_crawl_csv.php:620`, `:658-660`). Un champ séparé découple
aussi de `method`, déjà surchargé par trois décisions BO distinctes (dont un routage vers
table de retry).

**Rétrocompatibilité — vérifiée** :
- `DetectionResponse` n'a **aucun** `model_config` ⇒ pydantic 2.10.5 applique
  `extra='ignore'`. Le code de production dépend déjà de cette tolérance
  (`routes.py:186` `DetectionResponse(**cached)` sur un payload caché contenant
  `requested_url`).
- Le champ **doit** être `Optional` avec défaut : une entrée de cache antérieure au
  déploiement, relue par `DetectionResponse(**cached)`, n'aura pas la clé.
- **Aucun test** (Python, TS, PHP) n'asserte la forme exhaustive de la réponse ⇒ rien à
  mettre à jour.
- Le champ traverse batch, `first_match` et le job asynchrone sans code supplémentaire
  (`routes.py:141` `DetectionResponse(**{**result.model_dump(), ...})`,
  `app/core/async_jobs.py:411`).
- **Jamais caché pour `fetch_failed`** : `domain_fr.py:53`
  `_NEVER_CACHE_METHODS = frozenset({'error', 'fetch_failed', 'admission_rejected'})`.
  Aucun risque de figer une cause 30 jours, aucune migration de cache.

**Consommateurs — aucun à modifier pour éviter une casse** : le client Python partagé
renvoie le dict brut (`libs/common-utils/src/common_utils/detection_client.py:53-54`) ;
le client TS type par générique axios sans validation runtime
(`crawler/src/class/DetectionLangueClient.ts:103`) ; les 9 appelants PHP lisent par accès
tableau avec `??`.

---

## 5. B2 — proposer sans retirer

### 5.1 Marqueur dans le blob JSON (aucune migration)

Fonctions **pures** dans un fichier dédié —
`BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_detect_failure_pure.php`
— sur le modèle de `fonctions_relaunch_on_eligible_pure.php:19-34` :

- `detect_failure_apply(array $data, array $payload): array`
- `detect_failure_read(array $data): ?array`
- `detect_failure_strip(array $data): array`

Clé `detect_failure` dans `domaine_scrapping_produit_ia.data_crawling_dspi`.
Les 7 clés déjà utilisées du blob (`homepage`, `old_url`, `dropData`, `breakLimit`,
`relaunch_on_eligible`, `maintenance_probe`, `maintenance_homogeneity_ratio`) ne
comportent pas ce nom : **pas de collision**.

Payload : `{cause, stage, seen_count, first_seen_at, last_seen_at}`.

Le `seen_count` est gratuit dans la même écriture. Il ne conditionne **rien** dans ce
chantier (cf. §2.2) mais permettra d'exiger un seuil plus tard, sur des données réelles,
sans toucher la base.

**Pourquoi le blob et non `crawl_events`** : `crawl_events.event_type` est un ENUM
contraint dont l'extension exige une migration PROD-first (le précédent v4 a déjà mordu),
pour un historique dont §2.2 montre qu'il ne se remplirait pas. Aucune clause d'exclusion
de crawl ne lit le blob, donc poser un marqueur y est inerte.

**Limite acceptée** : l'écriture du blob est un read-modify-write sans verrou, dernier
écrivain gagnant (`fonctions_maintenance_domaine.php:146-148`). Un marqueur peut être
écrasé par une écriture concurrente (`dropData`, `homepage`). Acceptable : la liste est
recalculable au prochain lancement.

### 5.2 Écriture du marqueur

Dans `pct_traitement_crawling_rindra_BO.php`, après le split existant :

- domaine **indéterminé** porteur d'un `failure_detail` ⇒ `detect_failure_apply`
  (incrémente `seen_count` si la cause est identique) ;
- domaine ressortant **FR** ou **jugé non-FR** ⇒ `detect_failure_strip`.

L'effacement est obligatoire : sans lui, un site réparé resterait candidat
indéfiniment.

### 5.3 Le script de proposition

Nouveau fichier
`BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/roadmap_v1/pct_propose_retire_domaine_mort_rindra_BO.php`,
calqué sur `pct_revive_retire_auto_sans_relance_rindra_BO.php` :

1. `$__is_web = (php_sapi_name() !== 'cli');` + `header('Content-Type: text/plain; charset=UTF-8')`
2. `$apply = in_array('--apply', $argv ?? [], true) || ($__is_web && ($_GET['run'] ?? '') === '1');`
3. Sélection par `data_crawling_dspi LIKE '%detect_failure%'` (précédent :
   `fonctions_relaunch_on_eligible.php:94`)
4. Partition en seaux : **candidats** / **déjà retirés** / **cause non listée** /
   **introuvables**
5. Aperçu imprimé, puis `exit(0)` **avant toute écriture** si `!$apply`
6. En mode apply : `retire_domaine($id, 'domain_dead', 'auto', <cause tronquée>)`
   - `domain_dead` est une raison valide (`fonctions_retire_domaine.php:15`)
   - `retire_note_dspi` est `VARCHAR(255)`, tronqué par la fonction elle-même (`:103`)
   - `retire_domaine` est idempotent sur un domaine déjà retiré (`:99`)
7. Garde re-vérifiée dans le `WHERE` via `retire_ia_update` (`:44-58`, égalités
   uniquement) : `affected_rows = 0` ⇒ dérive concurrente ⇒ domaine non traité, signalé
8. Mail récapitulatif via `envoyer_mail_scripts`

### 5.4 La liste des causes est un paramètre vide

```php
// Vide à la livraison : AUCUN candidat ne peut être proposé, quel que soit le contenu
// du blob. À remplir sur des libellés RÉELLEMENT observés (voir §6), jamais devinés.
const DETECT_FAILURE_RETIRE_CAUSES = [];
```

C'est ce qui rend B2 **structurellement inerte** au déploiement.

**Le mode aperçu fonctionne malgré la liste vide** : il groupe et compte toutes les
causes observées, avec leur volume et les domaines concernés. C'est l'instrument de
récolte, et la base sur laquelle la liste sera remplie.

### 5.5 Flag dédié

```php
if (!defined('RETIRE_PROPOSAL_ENABLED')) { define('RETIRE_PROPOSAL_ENABLED', false); }
```

Patron `MAINTENANCE_DETECT_ENABLED` (`fonctions_maintenance_domaine.php:26-28`).
Un flag propre plutôt que d'élargir `AUTO_RETIRE_ENABLED`, qui vaut `true` et garde déjà
quatre écritures réelles.

---

## 6. Comment la liste des causes sera remplie

1. Déployer B1 (rebuild du service).
2. Lancer un lot représentatif. Le rapport affiche la cause de chaque indéterminé.
3. Déployer B2 (SFTP), lancer le script **en aperçu** : il groupe les causes par volume.
4. Décider quelles causes signifient « le domaine n'existe plus », remplir
   `DETECT_FAILURE_RETIRE_CAUSES`, re-déployer, relancer en aperçu, puis `--apply` sur un
   sous-ensemble.

Canaux de récolte alternatifs si nécessaire (aucun requis par ce design) :
`GET /crawler/admin/logs/{crawl_id}?grep=NS_ERROR|SEC_ERROR` (header `X-API-Key`, clé
`API_KEY_ADMIN_CRAWLER_SERVICE`) ; le dataset `error-{domain}` conserve les messages
bruts sous la clé `errors` avec `failure_class`
(`crawler-service/crawler/src/functions.ts:762-773`) — un enregistrement
`failure_class:"unknown"` + `status_code:0` est le signal exact d'un libellé de transport
non reconnu. Note : `GET /admin/dataset?kind=error` **ne projette pas** ces champs
(`app/router/admin.py:311-325`).

---

## 7. Décisions utilisateur (déjà prises)

- **Cause brute, pas classification** : « Nous allons partir sur ta recommendation »
  (option A) — aucune valeur devinée n'entre dans le code.
- **B1 et B2 spécifiées ensemble, B2 non activée** : « on peut spécifier mais ne pas
  activer directement mais d'abord que je valide sur la liste ».
- **Découpage retenu** : B1 complète et activable + B2 mécanisme avec liste vide.
- **Persistance** : blob `data_crawling_dspi`, un seul constat suffit, aucune migration.
- **Pas d'état « refusé »** au premier jet : le besoin découle d'une exécution périodique
  qui n'existe pas. L'opérateur applique sur un sous-ensemble d'IDs ; les non-retenus
  restent candidats sans nuisance récurrente.

---

## 8. Tests

**B1** (`pytest tests/`, référence : 314 passés / 7 échecs pré-existants dans
`test_domain_fr.py`) :
- sink rempli au `stage='navigation'` quand `page.goto` échoue, **et** extraction
  partielle toujours tentée (non-régression du rattrapage `:448-449`)
- sink rempli au `stage='content'` sur contenu trop court
- sink rempli au `stage='proxy'` sur proxy absent/invalide
- cause tronquée à 200 caractères, première ligne uniquement
- `error_sink=None` ⇒ comportement identique à aujourd'hui (byte-identique en sortie)
- `fetch_html` retient la cause de la **Phase 2** quand des variantes ont été tentées
- `DetectionResponse(**cached)` sans la clé ⇒ `failure_detail is None`, pas d'exception

**B2** (`php <script>`, convention `test_parse_ids.php`) :
- `detect_failure_apply` / `_read` / `_strip` purs : pose, incrémentation de
  `seen_count` sur cause identique, remise à 1 sur cause différente, effacement,
  tolérance à un blob JSON invalide
- liste de causes vide ⇒ **zéro candidat** même avec des marqueurs présents
- aperçu sans `--apply` ⇒ aucune écriture (assertion sur l'absence d'appel d'écriture)

---

## 9. Déploiement

| Ordre | Quoi | Comment |
|---|---|---|
| 1 | `api-detection-langue-fr` | push + **rebuild Docker VM**. Pas de migration, pas de flag, pas de changement compose. |
| 2 | BO | MEP SFTP. Pas de migration. `RETIRE_PROPOSAL_ENABLED=false`, liste de causes vide. |

B2 sans B1 n'aurait aucune cause à lire : l'ordre est contraignant.

**Rétrocompatibilité de B1** : additive. Un appelant qui ignore `failure_detail` ne voit
aucun changement.

---

## 10. À vérifier avant / pendant l'implémentation

Ces points ne sont **pas** établis par l'investigation et ne doivent pas être présumés :

1. **Valeur de `AUTO_RETIRE_ENABLED` en PRODUCTION.** Le dépôt local porte `true`
   (`fonctions_retire_domaine.php:9`) mais le BO se déploie par SFTP manuel. Ne change
   pas ce design (B2 a son propre flag) mais conditionne ce qui est actif aujourd'hui.
2. **Types SQL réels** des colonnes citées : tout est déduit des chaînes SQL PHP, aucun
   `bdd_describe_table` n'a été exécuté. À confirmer pour `data_crawling_dspi`
   (taille du blob) avant d'y ajouter une clé.
3. **Volumétrie** : aucune requête n'a été exécutée. Le nombre de domaines qui seraient
   proposés est inconnu.
4. **Quelle opération produit réellement un message contenant `Timeout`** qui atteint
   `last_error` : celui de `page.goto` est avalé, donc le token vient d'ailleurs
   (`new_context`/`new_page`, ou le nom de classe `TimeoutError`). Non vérifié à
   l'exécution.
5. **Les échecs de lancement Camoufox sont avalés** (`scraper.py:205-210`) avant le
   fallback Chromium : à décider si leur cause vaut d'être remontée, ou si le fallback
   masque une cause plus utile que celle du Chromium qui suit.
6. `map_failure_cause_to_reason()` (`fonctions_retire_domaine.php:37-41`) est **du code
   mort** attendant son premier appelant. À préférer à un `in_array` dupliqué si un
   mapping cause → raison devient nécessaire.

---

## 11. Références

- Rapport séparant jugés/indéterminés : BO `802993a1`, déployé 2026-08-06
- Audit du seam crawler↔détection :
  `docs/superpowers/references/2026-07-29-crawler-detection-seam-audit.md`
- Taxonomie d'échec du crawler : `crawler/src/httpStatusPolicy.ts:131-177` et
  `docs/superpowers/specs/2026-06-16-crawler-failure-recovery-design.md`
- Socle de retrait : `fonctions_retire_domaine.php`, patron propose/apply :
  `pct_revive_retire_auto_sans_relance_rindra_BO.php`
