# MCP HelloData — MEP PHP du 2026-10-09 : import de campagnes, colonnes, simulation, leads

Complète `MCP_HELLODATA_PHP_2026-10-05.md` (qui reste la référence du moteur :
style de production, jetons, liens, vérifications serveur). Ce document ne décrit
que **le delta** du 2026-10-09.

Déploiement manuel par SFTP/FTP, selon `site/CLAUDE.md` : les `.php` ne sont
**pas** dans git (`site/admin/` et `site/partenaires_externes/` sont ignorés, le
dépôt est public et le moteur porte le schéma interne d'`acheteur`) ; seul ce
document passe en PR. Comme pour la MEP du 2026-10-05, le code n'est pas recopié
ici : la liste des fichiers ci-dessous porte une empreinte SHA-256 pour vérifier
que le fichier déposé est bien celui qui a été testé.

- Origine : demande d'un utilisateur du MCP (2026-10-09) — historiser les campagnes SMS
  envoyées hors MCP (les 6 du 2026-10-07 : `EDF_20261007_P1..P3`, `HYU_20261007_P1..P3`,
  47 retours) et suivre l'étape « lead transmis ».
- Spec : `docs/superpowers/specs/2026-10-09-mcp-hellodata-import-et-leads-design.md`.
- Wrapper Go qui appelle ce code : `apps-microservices/mcp-hellodata-service`, branche
  `features/mcp-hellodata-import-campagnes` (`internal/hellodata/types.go` : source de vérité du format).
- Base de départ : la version **déployée le 2026-10-05** (copie de référence :
  worktree `mcp-hellodata-campagnes`, `site/admin/mcp/hellodata/` et
  `site/partenaires_externes/mcp/hellodata/`). La copie de `site/admin/mcp/hellodata/`
  du checkout principal date du 2026-09-21 : **ne pas partir d'elle**.

## Ce qui change

| Outil MCP | Côté | Changement |
|---|---|---|
| `hellodata_inscrire_contacts` | BO | **Nouvelle action** `inscrire_contacts` : inscrit une liste déjà envoyée (numéros ou `id_acheteur`), à sa date réelle, rend les inconnus / invalides |
| `hellodata_recup_acheteur` | BO | `colonnes` (même catalogue et même droit que l'export) et `simulation` (aucune écriture) ; sortie + `simulation` |
| `hellodata_bilan_campagnes` | BO | Compteur `leads_transmis` |
| `hellodata_enregistrer_reponses` | FRONT | `date_reponse` optionnelle (date réelle d'une réponse saisie après coup) |
| `hellodata_marquer_leads` | FRONT | **Nouvelle action** `marquer_leads` : pose `date_lead_transmis` sur un suivi de réponse positive |

Sans les nouveaux paramètres, `recup_acheteur`, `enregistrer_reponses` et
`download.php` se comportent exactement comme le 2026-10-05 (vérifié : CSV
historique et lien de téléchargement identiques à l'octet près).

## Ordre de MEP

Chaque étape suppose la précédente faite et vérifiée.

1. **DDL** (dev, puis prod) — `bilan_campagnes` et `marquer_leads` lisent la colonne :
   déposé avant elle, le nouveau `bilan_campagnes` répond `500 erreur_interne`
   (vérifié localement, voir les tests).
2. **BO** — les 7 fichiers BO ci-dessous.
3. **FRONT** — les 5 fichiers FRONT ci-dessous.
4. **Recette dev** (§ Tests post-déploiement), puis MEP prod : mêmes étapes 1 à 3.
5. **Wrapper Go** (`mcp-hellodata-service`) **après** le PHP de prod : déployé avant,
   `inscrire_contacts` et `marquer_leads` rendent `404 action_inconnue`, et
   `simulation` serait ignorée par l'ancien `recup_acheteur`, qui **réserverait pour de
   vrai** (le wrapper le détecte et le dit — `avertissement: simulation_non_supportee` —
   mais la réservation est faite).
6. Gateway : un admin rafraîchit le serveur hellodata (`/servers` → découvrir) pour que
   la base du gateway enregistre les 8 outils. Aucun code gateway à déployer.

Aucun nouveau jeton, aucun nouveau secret, aucune nouvelle inclusion prod.

## DDL

```sql
ALTER TABLE edgb2b.historique_campagne_suivi_ia
  ADD COLUMN date_lead_transmis DATETIME NULL AFTER date_historique;
```

Colonne nullable, sans défaut, aucune ligne existante modifiée. La table était vide en
production le 2026-10-09 (`bdd_list_tables` : 0 ligne) : l'opération est immédiate.
Si des campagnes ont été saisies d'ici la MEP, elle reste rapide (`ADD COLUMN … AFTER`
est en `ALGORITHM=INSTANT` à partir de MySQL 8.0.29 ; avant, reconstruction de la table,
de la taille du suivi). Retour arrière :
`ALTER TABLE edgb2b.historique_campagne_suivi_ia DROP COLUMN date_lead_transmis;`
— seulement après avoir redéposé le PHP du 2026-10-05.

## Fichiers à déposer

Ne **jamais** déposer de dossier `test/` ni de `jeton_dev.php`. Les fichiers
« copie identique » des deux côtés (`telephone.php`, `fonctions_mcp_hellodata.php`)
ne changent **pas** et restent identiques entre BO et FRONT.

Empreintes : 16 premiers caractères de `sha256sum`, à comparer avant dépôt.

### BO — `/admin/mcp/hellodata/`

| Fichier | État | SHA-256 (16) | Rôle |
|---|---|---|---|
| `admin/mcp/hellodata/campagne_bdd.php` | **nouveau** | `2f9e20e5c2911583` | Ouverture de campagne, identité / rattachement / `est_actif` (déplacés tels quels depuis `recup_acheteur.php`, partagés avec `inscrire_contacts`), lignes CSV aux colonnes choisies, garde InnoDB de la simulation |
| `admin/mcp/hellodata/actions/inscrire_contacts.php` | **nouveau** | `6d159f2172b736f4` | Action `inscrire_contacts` |
| `admin/mcp/hellodata/index.php` | modifié | `68c8e2a85822b215` | Route `inscrire_contacts` |
| `admin/mcp/hellodata/campagne.php` | modifié | `9e16fb683d6d3c2e` | Validation de `colonnes` et de `contacts`, en-tête CSV paramétrable |
| `admin/mcp/hellodata/actions/recup_acheteur.php` | modifié | `7c71de621b349712` | `colonnes`, `simulation` ; code d'identité et d'ouverture de campagne déplacé dans `campagne_bdd.php` |
| `admin/mcp/hellodata/download.php` | modifié | `1bd3f6829f96565f` | Ticket `recup` portant `colonnes` : le lien rend les mêmes colonnes |
| `admin/mcp/hellodata/actions/bilan_campagnes.php` | modifié | `91172b3824bfefce` | `leads_transmis` |

### FRONT — `/partenaires_externes/mcp/hellodata/`

| Fichier | État | SHA-256 (16) | Rôle |
|---|---|---|---|
| `partenaires_externes/mcp/hellodata/leads.php` | **nouveau** | `8b586587a486cfdf` | Validation des leads |
| `partenaires_externes/mcp/hellodata/actions/marquer_leads.php` | **nouveau** | `7ffde54ab9c99ca2` | Action `marquer_leads` |
| `partenaires_externes/mcp/hellodata/index.php` | modifié | `e2063c1e3f98da03` | Route `marquer_leads` |
| `partenaires_externes/mcp/hellodata/reponses.php` | modifié | `ddb9ec8fa0e52641` | Validation de `date_reponse` (et `mcp_hd_date_saisie_valider`, partagée avec les leads) |
| `partenaires_externes/mcp/hellodata/actions/enregistrer_reponses.php` | modifié | `0e7c311d8baccb78` | `date_historique` = `date_reponse` si fournie |

Les deux diffs triviaux, pour lecture :

```diff
# admin/mcp/hellodata/index.php
+	case 'inscrire_contacts':
+		require_once($_SERVER['DOCUMENT_ROOT']."admin/mcp/hellodata/actions/inscrire_contacts.php");
+		break;

# partenaires_externes/mcp/hellodata/index.php
+	case 'marquer_leads':
+		require_once($_SERVER['DOCUMENT_ROOT']."partenaires_externes/mcp/hellodata/actions/marquer_leads.php");
+		break;
```

## Comportement et contrat

- **`inscrire_contacts`** (BO) — entrée `{campagne: {code, nom, canal, prestataire?, message?, date_campagne}, contacts: [{telephone} | {id_acheteur}], cree_par}`, 1 à 2000 contacts, exactement un identifiant par contact (`contact_invalide` sinon). `date_campagne` = date d'envoi, refusée si postérieure à `CURDATE()` du serveur MySQL (`date_future`) ; campagne créée si son code est inconnu, `409 campagne_incoherente` si `canal` ou `date_campagne` diffèrent. Rapprochement : un numéro est normalisé (`telephone_normaliser`) puis cherché par égalité sur `acheteur.telephone_mobile_a` (index) ; un `id_acheteur` donne le numéro de sa fiche. Identité, rattachement et `est_actif` par **le même code** que `recup_acheteur`. Un numéro sans fiche active → `inconnus` ; invalide ou non mobile en `sms` → `invalides` ; deux fois dans la liste → une inscription, `doublons_liste` ; `ne_plus_contacter` → **inscrit quand même** (l'envoi a eu lieu) et listé. Suivi `INSERT IGNORE` daté `<date_campagne> 00:00:00` ; renvoi identique → `deja_dans_campagne`. `bloquage_a` n'est **pas** filtré : on enregistre un envoi, pas une sélection. Une transaction ; en cas d'erreur, rien n'est inscrit (la campagne, si elle vient d'être créée, reste vide et sera réutilisée). Sortie `{id_campagne, campagne_creee, inscrits, deja_dans_campagne, doublons_liste, inconnus, invalides, ne_plus_contacter}`, les listes avec les valeurs **telles que reçues**.
- **`recup_acheteur` + `colonnes`** — même catalogue (`mcp_hd_sql_catalogue_colonnes`) et même droit (`colonnes_restreintes_autorisees`) que l'export ; CSV = `telephone_normalise` puis les colonnes demandées (doublons retirés), lues sur la **fiche active**. Le ticket de `download.php` porte les colonnes et le droit ; `download.php` les revalide. Refus (`colonne_inconnue`, `colonne_restreinte`) **avant** toute création de campagne.
- **`recup_acheteur` + `simulation: true`** — même parcours, mêmes exclusions, mêmes feuilles `hist_*`, mêmes réservations, mais chaque lot se termine par un **`ROLLBACK`** au lieu d'un `COMMIT` : aucune ligne écrite (vérifié par comptage des 4 tables), campagne inconnue non créée, ni CSV ni lien, `simulation: true` en sortie. Seul le booléen JSON `true` simule. Si une des trois tables écrites n'est pas InnoDB, refus `409 simulation_indisponible` avant toute écriture (sur MyISAM, le rollback ne défait rien).
- **`enregistrer_reponses` + `date_reponse`** — `AAAA-MM-JJ` (→ minuit) ou `AAAA-MM-JJ HH:MM:SS` ; refusée (`date_reponse_invalide`) si future (horloge MySQL) ou antérieure au jour d'envoi du suivi. Les dates sont jugées **avant** la transaction : une seule date fausse refuse l'appel entier, rien n'est écrit. Sans `date_reponse` : `NOW()`, comme avant.
- **`marquer_leads`** (FRONT) — `{code_campagne, leads: [{telephone, date_transmission?}]}`, ≤ 500. Seul un suivi de catégorie `positive` est marqué (`non_positifs` sinon, réponse absente comprise) ; inconnus / hors campagne listés, rien écrit pour eux. Même numéro deux fois → compté une fois. `date_transmission` : même forme et mêmes refus que `date_reponse` (`date_transmission_invalide`). Sortie `{marques, inconnus, hors_campagne, non_positifs}`.
- **`bilan_campagnes`** — `leads_transmis` = suivis dont `date_lead_transmis` n'est pas nul.

## Tests locaux (passés le 2026-10-09)

Pile Docker locale persistante, données synthétiques (adresses `@example.test`,
faux numéros) : MySQL 8.0 avec `hpdata.acheteur` et les 4 tables de campagne dans
`edgb2b`, deux comptes distincts (hpdata en lecture seule ; annuaire BO limité à
`edgb2b`, base par défaut autre), `php -S` derrière un routeur qui pose un
`DOCUMENT_ROOT` à barre finale comme Ecritel, **sur PHP 7.0.33 et PHP 8.2.33**.
Le harnais n'est pas versionné.

Comme en 2026-10-05, `fonctions/fonctions_hellopro.php` est **le vrai fichier de
production** (sauvegarde FTP du 2026-09-22) : échappement par
`hellopro_traitement_donnee_annuaire_bo` / `hellopro_traitement_donnee_hellopro_data`,
notification par `hellopro_mysql_error`. Seules ses deux inclusions sont simulées :
`fonctions_mail.php` (`mail_personnel`, l'envoi est capturé dans un fichier) et
`fonctions_cryptage.php` (vide : le moteur n'appelle aucune fonction de cryptage).

- `php -l` des 26 fichiers du moteur (BO et FRONT, nouveaux compris) sur 7.0 et 8.2 : aucune erreur.
- **80 assertions HTTP contre MySQL, sur chacune des deux versions de PHP** : refus de
  `inscrire_contacts` avant écriture (date future, deux identifiants, `id_acheteur` en
  chaîne, liste vide, 2001 contacts, canal, `cree_par` absent) ; inscription nominale
  (numéro au format `+33 6 …`, `id_acheteur` dont le numéro est saisi avec espaces,
  fixe en `sms`, fiche sans numéro, `id_acheteur` absent, numéro absent de la base,
  doublon de liste, `ne_plus_contacter`, fiche bloquée) avec les compteurs, les listes
  et l'état de la base (date réelle, fiche active = la plus récente, `est_actif`
  unique, `ne_plus_contacter` non levé) ; idempotence ; `campagne_incoherente` ;
  `date_reponse` (futur, avant envoi, format, date impossible : appel entier refusé),
  minuit pour une date seule, `NOW()` sans date, filet STOP intact ; `marquer_leads`
  (refus, campagne inconnue, positif / non / sans réponse / inconnu / fixe, doublon,
  renvoi, date enregistrée) ; `bilan_campagnes` avec `leads_transmis` ; simulation
  (mêmes décisions qu'une sélection, rien écrit, campagne non créée, campagne existante,
  chaîne `"true"` ≠ booléen) ; garde InnoDB (table passée en MyISAM → `409`, rien écrit) ;
  `colonnes` (inconnue, restreinte sans droit, refus avant création, en-tête, fiche
  active, doublon retiré, `download.php` identique à l'octet près) ; sans `colonnes`,
  CSV et lien historiques identiques ; non-régression `comptage`, `echantillon`,
  `export` ; routeurs (actions inconnues, accès direct aux `actions/*.php` → 404,
  mauvais jeton et jeton de l'autre côté → 401).
- **Dépendance à la DDL, contrôle négatif** : colonne retirée, `bilan_campagnes` sur
  une campagne existante → `500 erreur_interne` en JSON, et le vrai `hellopro_mysql_error`
  construit le mail d'alerte (seules erreurs SQL du passage : les deux attendues, une par
  version de PHP).
- **Recette du paquet de MEP** (`recette_dev.sh`, 15 contrôles) : 15/15 sur PHP 8.2 et 7.0 ;
  contre le PHP du 2026-10-05, 12 échecs et code retour 1.
- **Contrat** : le client Go du wrapper (`internal/hellodata`) appelle les deux serveurs
  PHP et décode `simulation`, `colonnes`, `inscrire_contacts`, `date_reponse`,
  `date_future`, `date_reponse_invalide`, `marquer_leads` et `leads_transmis`.
- **Les tests peuvent échouer** (mutations sur une copie) : simulation qui fait `COMMIT`
  → « rien écrit » échoue ; inscription datée `NOW()` → « date réelle » échoue et les
  réponses du lendemain sont refusées comme antérieures à l'envoi (le défaut même de la
  demande d'origine) ; leads sans contrôle `positive` → 3 assertions échouent.

## Tests post-déploiement (sur dev)

Avec `BO=https://<hôte BO dev>/admin/mcp/hellodata/index.php`,
`FRONT=https://<hôte FRONT dev>/partenaires_externes/mcp/hellodata/index.php`,
`T` et `W` les deux jetons (en-tête `X-Hellodata-Token` si `Authorization` ne passe pas,
voir la MEP du 2026-10-05). Remplacer `<mobile connu>` par un mobile présent dans
`acheteur` sous la forme `0XXXXXXXXX`.

```bash
# 0. DDL faite
#    SHOW COLUMNS FROM edgb2b.historique_campagne_suivi_ia LIKE 'date_lead_transmis';

# 1. Simulation : compteurs, simulation=true, rien écrit (compter les lignes des 4 tables avant/après)
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=recup_acheteur" \
  -d '{"campagne":{"code":"recette-sim-2026-10","nom":"Recette sim","canal":"sms","date_campagne":"2026-10-09"},
       "n":20,"cree_par":"recette@example.test","simulation":true,
       "filtre":{"critere":"region","comparateur":"dans","valeur":[6]}}'

# 2. Sélection réelle avec colonnes, puis le lien
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=recup_acheteur" \
  -d '{"campagne":{"code":"recette-col-2026-10","nom":"Recette col","canal":"sms","date_campagne":"2026-10-09"},
       "n":5,"cree_par":"recette@example.test","colonnes":["raison_sociale","siret"],
       "filtre":{"critere":"region","comparateur":"dans","valeur":[6]}}'

# 3. Import d'une liste déjà envoyée, deux fois
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=inscrire_contacts" \
  -d '{"campagne":{"code":"recette-import-2026-10","nom":"Recette import","canal":"sms","date_campagne":"2026-10-07"},
       "cree_par":"recette@example.test",
       "contacts":[{"telephone":"<mobile connu>"},{"telephone":"0699999999"},{"telephone":"0144000000"}]}'

# 4. Réponse datée, puis lead, puis bilan
curl -s -X POST -H "Authorization: Bearer $W" "$FRONT?action=enregistrer_reponses" \
  -d '{"code_campagne":"recette-import-2026-10","reponses":[{"telephone":"<mobile connu>","reponse_brute":"oui","categorie":"positive","date_reponse":"2026-10-08 10:00:00"}]}'
curl -s -X POST -H "Authorization: Bearer $W" "$FRONT?action=marquer_leads" \
  -d '{"code_campagne":"recette-import-2026-10","leads":[{"telephone":"<mobile connu>","date_transmission":"2026-10-09"}]}'
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=bilan_campagnes" -d '{"code":"recette-import-2026-10"}'
```

Attendus :
0. Une ligne `date_lead_transmis datetime YES`.
1. `simulation: true`, `csv` et `url_csv` vides, aucune campagne `recette-sim-2026-10` créée, les comptes des 4 tables inchangés.
2. `csv` d'en-tête `telephone_normalise;raison_sociale;siret` ; `url_csv` téléchargé = le même fichier.
3. Premier appel : `inscrits` = 1, `inconnus` = `["0699999999"]` (si absent de la base), `invalides` = `["0144000000"]` ; second appel : `inscrits` = 0, `deja_dans_campagne` = 1.
4. `mis_a_jour` = 1 ; `marques` = 1 ; au bilan `envoyes` = 1, `positive` = 1, `leads_transmis` = 1 ; en base, `date_campagne` = `2026-10-07 00:00:00`, `date_historique` = `2026-10-08 10:00:00`, `date_lead_transmis` = `2026-10-09 00:00:00`.

Après la recette, supprimer les lignes des campagnes `recette-*-2026-10` dans
`edgb2b.historique_campagne_suivi_ia` et `edgb2b.historique_campagne_ia`. Les
identités et rattachements créés restent valables (alimentés au fil de l'eau, par conception).

## Reprise des campagnes du 2026-10-07 (après la MEP prod et le wrapper)

Depuis Claude, pour chacune des 6 campagnes, dans cet ordre :

1. `hellodata_inscrire_contacts` avec `date_campagne = 2026-10-07` et la liste envoyée au
   routeur (2000 contacts par appel au plus, rappeler sur le même code au-delà) ;
   relire `inconnus` et `invalides` avec l'utilisateur.
2. `hellodata_enregistrer_reponses` des retours de cette campagne, avec leur `date_reponse`.
3. `hellodata_marquer_leads` pour les leads déjà transmis, avec leur `date_transmission`.
4. `hellodata_bilan_campagnes` pour contrôler.

**Ne pas saisir les retours avant l'étape 1** : sans inscription, ils reviennent tous
`inconnus` et rien n'est écrit, STOP compris.

## Retour arrière

Redéposer les 8 fichiers modifiés depuis la copie du 2026-10-05 et supprimer les 4
nouveaux (`campagne_bdd.php`, `actions/inscrire_contacts.php`, `leads.php`,
`actions/marquer_leads.php`) ; redéployer le wrapper précédent. La colonne
`date_lead_transmis` peut rester (nullable, ignorée par le code du 2026-10-05). Les
campagnes et suivis inscrits par `inscrire_contacts` restent des données valides.

## Points d'attention

- **Numéros hors format compact** : la recherche par numéro est une égalité sur
  `telephone_mobile_a` au format `0XXXXXXXXX`. Mesure du 2026-10-09 : 57 737 fiches (≈ 3,4 %
  des numéros renseignés) sont saisies autrement et reviennent `inconnus` par numéro —
  sauf si une sélection passée les a déjà rattachées. Les retrouver par `id_acheteur`.
- **Numéros absents de la base** : non stockés (le suivi exige un `id_acheteur`). Un STOP
  d'un tel numéro n'est pas mémorisé (question ouverte n° 1 de la spec).
- **Simulation et concurrence** : la simulation pose les mêmes verrous qu'une sélection,
  le temps de chaque lot, avant de les relâcher par le rollback. Deux simulations ou une
  simulation et une sélection sur les mêmes numéros s'attendent comme deux sélections.
- **Lead** : seul un suivi `positive` peut être marqué (question ouverte n° 4 de la spec).
