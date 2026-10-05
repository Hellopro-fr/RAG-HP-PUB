# MCP HelloData — campagnes acheteurs via Claude

**Date :** 2026-09-28
**Branche :** `features/mcp-bdd-table`
**Statut :** wrapper Go implémenté le 2026-10-04 ; BO et webhook FRONT à écrire (voir l'amendement)
**Dépend de :** `2026-09-28-mcp-hellodata-server-authorizations-design.md` (sous-projet 1, livré avant)
**Étend :** `2026-09-21-mcp-hellodata-selection-design.md` (moteur BO, arbre de filtres, proxy `/download`)

Sous-projet 2 de la fonctionnalité « campagnes acheteurs via Claude ».

> **Amendement du 2026-10-04 — contrat fixé par le wrapper.** Le wrapper
> (`apps-microservices/mcp-hellodata-service`) est implémenté ; le BO et le
> webhook FRONT doivent respecter ceci :
>
> - **Transport, BO et webhook :** `POST {base}/index.php?action=<nom>`,
>   `Authorization: Bearer <jeton>` (`HELLODATA_TOKEN` pour le BO,
>   `HELLODATA_WEBHOOK_TOKEN` pour le webhook), corps JSON, réponse dans
>   l'enveloppe `{code, response}` ; une erreur rend
>   `{code, response: {erreur, message}}` avec un statut HTTP non 2xx, et
>   `erreur` remonte tel quel au LLM. Actions : `recup_acheteur`,
>   `bilan_campagnes` (BO), `enregistrer_reponses` (webhook).
> - **§ 6.1 — le CSV voyage dans la réponse.** « Le BO renvoie un handle »
>   devient : `recup_acheteur` renvoie le CSV complet dans le champ `csv`
>   (BOM compris), à côté des compteurs. Le wrapper le mémorise, émet le
>   jeton `/download` et ne renvoie au LLM que `url_csv`, jamais le
>   contenu. `selectionnes > 0` avec un `csv` vide est traité comme une
>   panne du moteur. Le corps envoyé au BO porte `cree_par` (e-mail de
>   l'appelant) au premier niveau, à côté de `campagne`, `n`, `filtre`.
> - **§ 6.3 :** `bilan_campagnes` reçoit `{}` ou `{"code": "…"}` et répond
>   `{"campagnes": [ … ]}`.
> - **Validations faites aussi par le wrapper, avant le réseau** (le moteur
>   les refait) : `n_hors_bornes`, `campagne_invalide` (code ≤ 64, nom
>   ≤ 255, canal `sms`/`appel`, date `AAAA-MM-JJ`), forme de l'arbre ;
>   `categorie_invalide`, `trop_de_reponses` (> 500), `corps_trop_gros`
>   (> 256 Ko), `code_campagne_invalide`, `telephone_manquant`. La place
>   des feuilles `hist_*` (`hist_hors_et_racine`) reste jugée par le
>   compilateur du moteur.
> - **Constat du 2026-10-04 :** sur le BO de dev, `/admin/mcp/hellodata`
>   existe mais est **vide**, et `/admin/mcp` n'existe pas en production :
>   le moteur du sous-projet 0 n'est pas déployé. Les extensions de ce
>   document supposent ce moteur ; il doit être livré d'abord.
> - **À valider :** le CSV porte `telephone_normalise` pour tout appelant
>   autorisé, alors que `echantillon` / `export_csv` réservent `mobile` à
>   l'admin (précondition 5 non tranchée).

> **Amendement du 2026-10-05 — deux décisions de l'utilisateur.**
>
> - **§ 7 — chaque appel continue la campagne, par exclusion.** Pour une
>   campagne existante, `recup_acheteur` lit d'abord, sur le lien annuaire BO
>   (tables `edgb2b` seulement), toutes les fiches rattachées à un numéro déjà
>   réservé dans cette campagne (`historique_campagne_acheteur_doublon_ia`
>   joint à `historique_campagne_suivi_ia`), plus les `id_acheteur` réservés
>   eux-mêmes. Le parcours `DESC` de `acheteur` repart toujours du sommet avec
>   `AND A.id_acheteur NOT IN (<entiers castés>)` (clause omise si la liste est
>   vide ; jamais de jointure entre les deux liens). Les fiches couvertes ne
>   comptent donc plus dans la borne de 100 000, et un appel avec un AUTRE filtre
>   sur la même campagne retrouve les candidats situés au-dessus des réservations
>   précédentes. Le contrôle par numéro `deja_dans_campagne` reste le filet
>   (nouvelle fiche d'un numéro réservé, pas encore rattachée). Au-delà de
>   200 000 fiches couvertes, l'appel est refusé (`campagne_trop_volumineuse`) :
>   ouvrir une nouvelle campagne. Une campagne neuve part de la fiche la plus
>   récente. *Correction le même jour : une première version reprenait sous le
>   plus petit `id_acheteur` réservé ; ce plancher ignorait le filtre (un autre
>   filtre perdait les candidats au-dessus) et, `id_acheteur` étant la fiche
>   active, pouvait rescanner sans fin la même plage après la borne de 100 000.*
>   Recontacter après un délai reste le rôle des feuilles `hist_*` dans une
>   campagne ultérieure.
> - **§ 8 — STOP l'emporte quelle que soit la campagne.** `negative_stop`
>   signifie « ne plus me contacter » : définitif. Quand la catégorie
>   effective d'une réponse est `negative_stop` (explicite ou forcée par le
>   filet `^\s*STOP`) et que le numéro normalisé existe dans
>   `historique_campagne_acheteur_ia` sans être dans la campagne citée,
>   `statut_contact` passe quand même à `ne_plus_contacter` (même transaction),
>   le numéro reste listé dans `hors_campagne`, aucune ligne de suivi n'est
>   écrite, `mis_a_jour` ne compte toujours que les suivis mis à jour, et
>   `stop_force` compte le filet STOP s'il a joué. `ResultatReponses` est
>   inchangé. Un numéro inconnu (`inconnus`) n'est jamais touché.
>   `negative_contactable` = « non », recontactable dans une campagne
>   ultérieure après le délai choisi dans Claude.

> **Amendement du 2026-10-05 (bis) — le CSV est servi par le BO.** Le
> `/download/{jeton}` du wrapper n'a pas de route publique (service
> `expose:` seulement) : les liens rendus au LLM étaient morts. Décision de
> l'utilisateur : le CSV est servi par `/admin/mcp/hellodata/download.php`,
> en GET, **sans session BO ni Bearer**, sur présentation d'un **ticket signé
> qui expire** (15 min), et **régénéré** à chaque téléchargement (aucun
> fichier au repos).
>
> - Ticket = `base64url(gzdeflate(JSON))` . `.` . `base64url(HMAC-SHA256)`,
>   clé dérivée du jeton existant (`hash_hmac('sha256', 'mcp-hellodata-download',
>   _MCP_HELLODATA_TOKEN_, true)`) : pas de nouveau secret. Le JSON porte `exp`
>   et tous les paramètres (droit aux colonnes restreintes compris) : le porteur
>   du lien ne peut rien changer. Altéré ou malformé → 403, expiré → 410, le
>   contenu n'est jamais renvoyé. Un ticket de plus de 6000 caractères n'est pas
>   émis (`lien_trop_long`) : Apache coupe la ligne de requête vers 8190 octets.
> - `export` garde son corps et sa sentinelle et ajoute l'en-tête
>   `X-Hellodata-Lien: <url>` ; le téléchargement rend la même page, à l'octet
>   près, sans la sentinelle.
> - `recup_acheteur` ajoute le champ `url_csv` (vide sans sélection) ; le
>   ticket porte `id_campagne` et la plage `id_suivi` des réservations de
>   l'appel, le CSV est refait depuis `edgb2b` puis `acheteur` (requêtes
>   séparées), mêmes colonnes. § 6.1 et § 9 (« le wrapper émet le jeton
>   `/download` ») ne valent plus que comme repli quand le moteur ne fournit
>   pas de lien.
> - Le wrapper rend ce lien au LLM ; `HELLODATA_PUBLIC_URL` n'est plus
>   nécessaire une fois `download.php` déployé.

---

## 1. Besoin

Un utilisateur veut piloter ses campagnes SMS / appel depuis Claude :

1. Il demande `n` acheteurs pour une campagne, filtrés sur `acheteur` et
   croisés avec l'historique (ex. « ceux qui ont répondu non il y a plus de
   deux mois »). La campagne est créée si elle n'existe pas.
2. Il récupère la liste (CSV) et la transmet au prestataire — **hors Claude**.
3. Il revient avec les réponses du prestataire, que Claude classe et
   enregistre dans l'historique.

Les acheteurs sont **dédoublonnés par numéro de téléphone** : un numéro est
une identité de campagne, quelle que soit la fiche `acheteur` qui le porte.

---

## 2. Décisions

| # | Question | Décision |
|---|---|---|
| C1 | Canal | SMS / appel. Un acheteur sans numéro valide n'entre **jamais** dans une campagne |
| C2 | Alimentation des tables d'identité | **Au fil de l'eau**, pendant `recup_acheteur` : pas de chargement initial, pas de cron |
| C3 | Répartition des écritures | **BO** : sélection + inscription (identité, doublons, campagne, suivi « envoyé »). **FRONT webhook** : réponses (suivi + statut de contact) |
| C4 | Classement des réponses | **Claude classe**, l'outil valide les 3 valeurs ; filet `STOP` côté webhook |
| C5 | Réservation | Une ligne de suivi « envoyé » est écrite **dès la sélection** |
| C6 | Volume | `n` ≤ 2000 par appel ; au-delà, appels répétés sur la même campagne |
| C7 | Nombre de tables | **4** (la demande dit « 3 » en en-tête mais en décrit 4) |

---

## 3. Vue d'ensemble

```
Claude
  │ hellodata_recup_acheteur / hellodata_bilan_campagnes / hellodata_enregistrer_reponses
  ▼
mcp-gateway-service      accès : admin OU grant server_authorizations (sous-projet 1)
  ▼
mcp-hellodata-service    contrat MCP, proxy /download, cree_par = X-End-User-Email
  ├── HTTPS + Bearer HELLODATA_TOKEN ──────────► BO  /admin/mcp/hellodata/
  │                                                  recup_acheteur, bilan_campagnes
  │                                                  lit acheteur, écrit les 4 tables
  └── HTTPS + Bearer HELLODATA_WEBHOOK_TOKEN ──► FRONT /partenaires_externes/mcp/hellodata/
                                                     enregistrer_reponses
                                                     écrit suivi + statut_contact
```

---

## 4. Modèle de données (MySQL 8, base `hpdata`)

```sql
-- 1 ligne = 1 numéro de téléphone normalisé (l'identité de campagne)
CREATE TABLE historique_campagne_acheteur_ia (
  id_acheteur_ia      INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  telephone_normalise VARCHAR(20)  NOT NULL,           -- format 0XXXXXXXXX
  statut_contact      ENUM('contactable','ne_plus_contacter') NOT NULL DEFAULT 'contactable',
  date_creation       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  date_maj            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_tel (telephone_normalise)
);

-- chaque fiche acheteur rattachée à son numéro ; la plus récente est active
CREATE TABLE historique_campagne_acheteur_doublon_ia (
  id_acheteur            INT          NOT NULL PRIMARY KEY,  -- acheteur.id_acheteur
  id_acheteur_ia         INT UNSIGNED NOT NULL,
  date_creation_acheteur DATETIME     NOT NULL,              -- copie de acheteur.date_creation_a
  est_actif              TINYINT(1)   NOT NULL DEFAULT 0,
  KEY k_numero_actif (id_acheteur_ia, est_actif)
);

CREATE TABLE historique_campagne_ia (
  id_campagne   INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  code          VARCHAR(64)  NOT NULL,       -- clé naturelle : « créer si absente »
  nom           VARCHAR(255) NOT NULL,
  canal         ENUM('sms','appel') NOT NULL,
  prestataire   VARCHAR(255) NOT NULL DEFAULT '',
  message       TEXT NULL,
  date_campagne DATE NOT NULL,
  cree_par      VARCHAR(255) NOT NULL,       -- e-mail de l'appelant MCP
  date_creation DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_code (code)
);

CREATE TABLE historique_campagne_suivi_ia (
  id_suivi        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  id_acheteur_ia  INT UNSIGNED NOT NULL,
  id_acheteur     INT          NOT NULL,     -- fiche active au moment de l'envoi
  id_campagne     INT UNSIGNED NOT NULL,
  date_campagne   DATETIME     NOT NULL,     -- sélection = envoi
  reponse_brute   TEXT NULL,
  categorie       ENUM('positive','negative_contactable','negative_stop') NULL,
  tag             ENUM('oui','non') GENERATED ALWAYS AS
                    (CASE WHEN categorie IS NULL THEN NULL
                          WHEN categorie = 'positive' THEN 'oui' ELSE 'non' END) STORED,
  date_historique DATETIME NULL,             -- réception de la réponse
  UNIQUE KEY uq_campagne_numero (id_campagne, id_acheteur_ia),
  KEY k_numero_date (id_acheteur_ia, date_historique)
);
```

### 4.1 Invariants

- **Un numéro au plus par campagne** (`uq_campagne_numero`) : la base arbitre
  même si deux conversations sélectionnent en même temps.
- **Le tag oui/non** est une colonne générée depuis `categorie` : il ne peut
  pas la contredire.
- **Une fiche appartient à un seul numéro** (PK `id_acheteur`). Si le numéro
  d'une fiche change, le parcours suivant la détache de l'ancien numéro, la
  rattache au nouveau et recalcule `est_actif` sur les deux.
- **Un seul `est_actif = 1` par numéro** : la fiche de plus grand
  `id_acheteur` (départage par `date_creation_acheteur` si besoin).
- **`ne_plus_contacter` est définitif** côté automatique (droit
  d'opposition) : seule une intervention manuelle en BO le lève.

Les catégories :

| Réponse | `categorie` | `tag` | `statut_contact` |
|---|---|---|---|
| Positive | `positive` | oui | inchangé |
| Négative, d'autres campagnes restent possibles | `negative_contactable` | non | inchangé |
| Négative, ne veut plus rien recevoir | `negative_stop` | non | → `ne_plus_contacter` |

---

## 5. Normalisation du numéro

`telephone_normaliser(string) : ?string` — renvoie `0XXXXXXXXX` ou `null` :

1. ne garder que les chiffres et un `+` initial ;
2. `+33…` / `0033…` → `0…` ;
3. exiger `^0[1-9][0-9]{8}$` ;
4. rejeter la liste noire : dix chiffres identiques, `0123456789`, et toute
   entrée ajoutée à la constante `TELEPHONES_FACTICES` ;
5. pour `canal = sms`, n'accepter que `06` / `07` (filtre appliqué à la
   sélection, pas à la normalisation — un fixe reste une identité valide pour
   une campagne `appel`).

La fonction est **dupliquée** dans le BO et le FRONT (arborescences
distinctes, pas de dossier commun) ; les deux copies exécutent **le même
fichier de jeux de test** `telephone.cas.php`, pour qu'elles ne puissent pas
diverger silencieusement.

Mesure du 2026-09-28 sur un échantillon de `acheteur` : environ un million de
`telephone_mobile_a` vides, 704 `0000000000`, et des numéros répétés des
centaines de fois (standards, numéros génériques). L'outil `bdd` masquant les
numéros, leur format réel **n'a pas pu être audité** : la liste noire est à
compléter à la recette.

---

## 6. Outils MCP

Noms backend ; le gateway ajoute `hellodata_`. Les trois outils existants
(`compter`, `echantillon`, `export_csv`) sont inchangés.

### 6.1 `recup_acheteur` (BO)

Entrée :

```json
{
  "campagne": { "code": "relance-btp-2026-10", "nom": "Relance BTP octobre",
                "canal": "sms", "prestataire": "…", "message": "…",
                "date_campagne": "2026-10-05" },
  "n": 500,
  "filtre": { "operateur": "ET", "conditions": [ … ] }
}
```

- `campagne.code` absent en base → la campagne est créée (`cree_par` = e-mail
  de l'appelant, fourni par le wrapper). Présent → réutilisée ; si `canal` ou
  `date_campagne` diffèrent de la ligne existante → erreur
  `campagne_incoherente` (pas de mise à jour silencieuse).
- `n` : 1 à 2000, sinon `n_hors_bornes`.
- `filtre` : l'arbre existant (§ 4.3 de la spec du 2026-09-21), enrichi des
  feuilles d'historique du § 6.4.

Sortie :

```json
{
  "id_campagne": 12, "campagne_creee": true,
  "selectionnes": 500,
  "exclus": { "ne_plus_contacter": 31, "critere_historique": 210,
              "deja_dans_campagne": 0, "telephone_invalide": 1840 },
  "fiches_parcourues": 2581, "epuise": true,
  "url_csv": "https://…/download/<jeton>"
}
```

CSV : `telephone_normalise, id_acheteur, civilite, nom, prenom,
raison_sociale, cp, ville`. Livré par le proxy `/download` existant (jeton
15 min).

### 6.2 `enregistrer_reponses` (FRONT webhook)

```json
{ "code_campagne": "relance-btp-2026-10",
  "reponses": [ { "telephone": "06…", "reponse_brute": "STOP",
                  "categorie": "negative_stop" } ] }
```

≤ 500 réponses par appel. Sortie : `{ mis_a_jour, inconnus: [...],
hors_campagne: [...], stop_force: n }`. Claude découpe un fichier plus gros
en plusieurs appels.

### 6.3 `bilan_campagnes` (BO)

Liste les campagnes (option `code` pour une seule) : `code, nom, canal,
date_campagne, cree_par, envoyes, positive, negative_contactable,
negative_stop, sans_reponse`. Sert à retrouver le `code` quand l'utilisateur
revient dans une autre conversation.

### 6.4 Feuilles d'historique

Ajoutées à `criteres.php`, combinables en ET / OU / NON avec les critères
`acheteur` :

| Feuille | Valeur | Sens |
|---|---|---|
| `hist_jamais_contacte` | `true` | aucun suivi pour ce numéro |
| `hist_derniere_categorie` | liste de catégories | catégorie de la réponse la plus récente |
| `hist_derniere_reponse_il_y_a_plus_de_jours` | entier ≥ 1 | `date_historique` la plus récente antérieure à `NOW() - X jours` |
| `hist_campagne` | `{codes: [...], inclure: bool}` | présent (ou absent) dans ces campagnes |

Exemple — « répondu non il y a plus de 2 mois » :
`ET(hist_derniere_categorie=[negative_contactable],
hist_derniere_reponse_il_y_a_plus_de_jours=60)`.

**Exclusions toujours appliquées**, non désactivables : `ne_plus_contacter`,
numéro déjà dans cette campagne, numéro invalide (ou non mobile en `sms`).

---

## 7. Algorithme de `recup_acheteur`

1. **Parcours** par lots de 500 :
   `WHERE <filtre acheteur compilé> AND A.telephone_mobile_a <> ''
   AND A.id_acheteur < :curseur ORDER BY A.id_acheteur DESC`.
   Les feuilles `hist_*` sont **retirées** de cette compilation (elles ne
   portent pas sur `acheteur`) et évaluées à l'étape 4.
2. **Normalisation** de chaque numéro (§ 5) ; invalide → compté, ignoré.
3. **Inscription**, une transaction par lot :
   `INSERT … ON DUPLICATE KEY UPDATE` sur `acheteur_ia`, rattachement de la
   fiche dans `doublon_ia` (détachement si son numéro a changé), recalcul de
   `est_actif` pour les numéros touchés.
4. **Évaluation de l'historique** sur les `id_acheteur_ia` du lot :
   exclusions fixes, puis feuilles `hist_*`. C'est seulement ici que
   l'identité téléphonique est connue.
5. **Réservation** : `INSERT IGNORE` d'une ligne de suivi par numéro retenu
   (fiche active, `date_campagne = NOW()`), arrêt à `n`.
6. **Borne** : au plus 100 000 fiches parcourues par appel. Atteinte →
   `epuise = false`, Claude peut rappeler (les réservés sont exclus
   d'office au rappel).

Propriété du parcours `DESC` : la première fiche rencontrée pour un numéro
est la plus récente ; `est_actif` n'a à être recalculé que quand une fiche
créée après un parcours antérieur apparaît.

Un échec en cours de parcours conserve les lots déjà validés et renvoie
`epuise = false` avec le compte réel des sélectionnés.

**Retrait d'une feuille `hist_*` sous un `NON` ou un `OU`.** Retirer une
feuille d'un `ET` est sûr (le reste du filtre est un sur-ensemble, affiné à
l'étape 4). Sous un `OU` ou un `NON`, le retrait change le sens. Règle : le
compilateur refuse (`hist_hors_et_racine`) toute feuille `hist_*` qui n'est
pas un enfant direct du `ET` racine, ou la racine elle-même. Les
combinaisons OU/NON restent possibles **entre** feuilles `hist_*` dans un
sous-groupe dédié, lui-même enfant du `ET` racine et évalué entièrement à
l'étape 4.

**Précondition à vérifier avant de coder :** la spec du 2026-09-21 filtre sur
`A.bloquage_a = 0`, colonne absente de la description de `acheteur` renvoyée
par l'outil `bdd` le 2026-09-28. Confirmer, sur le serveur, si la colonne
existe (masquage de l'outil) ou si le moteur référence une colonne absente.

---

## 8. Webhook FRONT — `partenaires_externes/mcp/hellodata/`

- **Appelant unique** : le wrapper Go, jamais le prestataire. Bearer propre
  `HELLODATA_WEBHOOK_TOKEN`, `auth.php` copié du BO (comparaison
  `hash_equals`, refus si jeton non configuré).
- **Entrée** : POST JSON, corps ≤ 256 Ko, ≤ 500 réponses, `categorie` dans
  les 3 valeurs exactes (`categorie_invalide` sinon), `reponse_brute`
  tronquée à 2000 caractères.
- **Rapprochement** par ligne :

  | Cas | Effet |
  |---|---|
  | Numéro inconnu de `acheteur_ia` | `inconnus`, rien écrit |
  | Connu, absent de la campagne | `hors_campagne`, rien écrit |
  | Suivi trouvé | `reponse_brute`, `categorie`, `date_historique = NOW()` ; renvoi identique = même résultat |
  | `negative_stop` | en plus `statut_contact = ne_plus_contacter` |
  | `reponse_brute` correspond à `^\s*STOP` | catégorie forcée à `negative_stop`, compté dans `stop_force` |

- Une transaction par appel.

---

## 9. Wrapper — `mcp-hellodata-service`

- 3 outils ajoutés à `internal/tools/registry.go`, implémentés à côté de
  `selection.go`.
- `recup_acheteur` et `bilan_campagnes` passent par `hellodata.Client`
  existant ; `enregistrer_reponses` par un nouveau client webhook.
- Nouvelles variables, **obligatoires** au démarrage :
  `HELLODATA_WEBHOOK_URL`, `HELLODATA_WEBHOOK_TOKEN` (référencées
  `${…}` dans `docker-compose.yml`, valeurs réelles dans le `.env` non
  tracké — dépôt public).
- `cree_par` vient de `X-End-User-Email`, **jamais** des arguments de
  l'outil.
- Accès : celui du sous-projet 1 (admin ou grant), inchangé.
- `url_csv` : le BO renvoie un handle, le wrapper émet le jeton `/download`,
  comme `export_csv`.
- La ligne « 3 tools » du gateway (`fetchHellodataTools`) et le CLAUDE.md du
  wrapper passent à 6 outils.

---

## 10. Tests

**PHP** (scripts `test/*.test.php`, harnais `_assert.php`, BO et FRONT) :

1. `telephone.cas.php` exécuté des deux côtés : formats `+33`, `0033`,
   espaces / points, longueur, liste noire, contrôle positif.
2. `est_actif` : fiche plus récente, fiche créée après un parcours, numéro
   qui change de fiche.
3. Compilation : les feuilles `hist_*` sont retirées du SQL `acheteur` et
   évaluées sur l'historique ; exemple « non il y a plus de 60 jours » ;
   refus `hist_hors_et_racine`.
4. Webhook : les 5 cas du tableau du § 8, filet STOP, `ne_plus_contacter`
   non levé par une réponse positive ultérieure.
5. `campagne_incoherente`, `n_hors_bornes`, `categorie_invalide`, corps
   trop gros.

**Go** (`go test ./...`, `go vet ./...`) : schémas des 3 outils, `cree_par`
pris dans l'en-tête et ignoré dans les arguments, client webhook (Bearer,
erreurs HTTP), refus pour un non-autorisé, variables obligatoires.

**Recette dev** : `recup_acheteur` (n = 20) → CSV → `enregistrer_reponses`
→ `bilan_campagnes` ; puis second `recup_acheteur` sur la même campagne : aucun
des 20 numéros ne ressort.

---

## 11. Déploiement

1. DDL des 4 tables — manuel, dev puis prod.
2. BO et FRONT PHP — SFTP dev, puis MEP prod ; spec `.md` seule en PR,
   conformément à `site/CLAUDE.md`.
3. Wrapper (et gateway si besoin) — **après** le sous-projet 1.

---

## 12. Hors périmètre

- Envoi réel des campagnes (fait par le prestataire, hors Claude).
- Écran BO de gestion des campagnes ou de levée manuelle de
  `ne_plus_contacter` (la levée se fait en SQL tant qu'aucun écran n'existe).
- Campagnes e-mail (C1).
