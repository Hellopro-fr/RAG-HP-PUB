# MCP HelloData — côté PHP (moteur BO + webhook FRONT) — 2026-10-04

Déploiement manuel par SFTP/FTP, selon `site/CLAUDE.md` : les `.php` ne sont
**pas** dans git (`site/admin/` et `site/partenaires_externes/` sont ignorés),
seul ce document passe en PR.

- Wrapper Go qui appelle ce code : `apps-microservices/mcp-hellodata-service`
  (PR #849 pour les outils de campagne).
- Specs : `docs/superpowers/specs/2026-09-21-mcp-hellodata-selection-design.md`
  (moteur), `2026-09-28-mcp-hellodata-campagnes-design.md` (campagnes, dont
  l'amendement du 2026-10-04 qui fixe le contrat).
- Plan suivi pour le moteur : `docs/superpowers/plans/2026-09-21-mcp-hellodata-selection.md`
  (Tasks A1–A8, avec l'amendement A8 « export paginé »).

## Contexte

Constat du 2026-10-04 par SFTP : `/admin/mcp/hellodata` existe sur le BO de
dev mais est **vide**, `/admin/mcp` n'existe pas en production, et le FRONT
n'a pas de `partenaires_externes/mcp/`. Le moteur du sous-projet 0 n'avait
donc jamais été déployé : ce lot le livre, avec les actions de campagne et le
webhook.

## Fichiers à déposer

Ne **jamais** déposer les dossiers `test/` : ils contiennent le harnais de
test et l'intégration locale (les tests refusent de s'exécuter hors CLI, mais
ils n'ont rien à faire sur un serveur web).

### BO — `/admin/mcp/hellodata/` (serveur `dev-write-prod` sur dev, MEP en prod)

| Fichier | Rôle |
|---|---|
| `index.php` | Routeur unique : Bearer, corps ≤ 256 Ko, dispatch |
| `routes.php` | Table des actions (`comptage`, `echantillon`, `export`, `recup_acheteur`, `bilan_campagnes`) |
| `config.php` | Lecture des réglages (`config.local.php`, puis environnement, puis défaut) |
| `auth.php` | Vérification du Bearer à temps constant |
| `reponse.php` | Enveloppe `{code, response}`, codes d'erreur stables, journal |
| `bdd.php` | Connexions mysqli et requêtes préparées |
| `arbre.php` | Forme et bornes de l'arbre de filtres |
| `criteres.php` | Liste blanche des 23 critères `acheteur` |
| `compilateur.php` | Arbre → `WHERE` paramétré |
| `requete.php` | Assemblage : dédoublonnage SIREN/SIRET, curseur, plafond 2000 |
| `cache.php` | Cache de comptage (5 min) sous `sys_get_temp_dir()` |
| `telephone.php` | Normalisation `0XXXXXXXXX` (copie **identique** côté FRONT) |
| `historique.php` | Feuilles `hist_*` : séparation de l'arbre et SQL d'historique |
| `campagne.php` | Fonctions pures de campagne (validation, lot, CSV) |
| `actions/comptage.php` | Comptage approché (plafond 10 000) ou exact |
| `actions/echantillon.php` | Lecture paginée par curseur |
| `actions/export.php` | Même sélection en CSV, sentinelle `# fin-export;<lignes>;<curseur>` |
| `actions/recup_acheteur.php` | Sélection + inscription dans une campagne |
| `actions/bilan_campagnes.php` | Campagnes et compteurs |

### FRONT — `/partenaires_externes/mcp/hellodata/` (serveur `dev-write-front` sur dev)

| Fichier | Rôle |
|---|---|
| `index.php` | Routeur du webhook : Bearer propre, POST seulement, corps ≤ 256 Ko |
| `routes.php` | Une action : `enregistrer_reponses` |
| `config.php` | Réglages côté FRONT (jeton du webhook) |
| `auth.php`, `reponse.php`, `bdd.php`, `telephone.php` | Copies identiques du BO |
| `reponses.php` | Validation des réponses, troncature à 2000 caractères, filet STOP |
| `actions/enregistrer_reponses.php` | Rapprochement et enregistrement, une transaction par appel |

## Configuration

Chaque réglage se lit dans cet ordre : constante définie dans un fichier
`config.local.php` posé **à la main** à côté de `index.php` (jamais dans
git), puis variable d'environnement (`SetEnv`), puis valeur par défaut.
Un `.php` servi par Apache s'exécute sans rien afficher : `config.local.php`
ne divulgue pas ce qu'il définit.

Modèle de `config.local.php` (BO) — remplacer les valeurs entre chevrons :

```php
<?php
define('MCP_HELLODATA_TOKEN', '<même valeur que HELLODATA_TOKEN du wrapper>');
// À confirmer sur le serveur (non vérifiable par l'agent) :
// define('HELLODATA_BDD_INCLUDE', 'no_read_access/connexion_bdd_hellopro_data.php');
// define('HELLODATA_BDD_LIEN', 'LINK_MYSQLI_HELLOPRO_DATA');
// define('HELLODATA_CAMPAGNE_BASE', 'edgb2b');
// Si le compte ci-dessus ne peut pas écrire dans edgb2b :
// define('HELLODATA_CAMPAGNE_BDD_INCLUDE', '<fichier de connexion avec droits d écriture>');
// define('HELLODATA_CAMPAGNE_BDD_LIEN', '<nom de la variable mysqli>');
```

Modèle de `config.local.php` (FRONT) :

```php
<?php
define('HELLODATA_WEBHOOK_TOKEN', '<même valeur que HELLODATA_WEBHOOK_TOKEN du wrapper>');
// define('HELLODATA_CAMPAGNE_BDD_INCLUDE', 'no_read_access/connexion_bdd_hellopro_data.php');
// define('HELLODATA_CAMPAGNE_BDD_LIEN', 'LINK_MYSQLI_HELLOPRO_DATA');
// define('HELLODATA_CAMPAGNE_BASE', 'edgb2b');
```

| Réglage | Défaut | Rôle |
|---|---|---|
| `MCP_HELLODATA_TOKEN` | vide → tout refusé | Bearer attendu par le BO |
| `HELLODATA_WEBHOOK_TOKEN` | vide → tout refusé | Bearer attendu par le webhook |
| `HELLODATA_BDD_INCLUDE` | `no_read_access/connexion_bdd_hellopro_data.php` | Fichier (relatif à `DOCUMENT_ROOT`) qui ouvre la connexion lisant `acheteur` |
| `HELLODATA_BDD_LIEN` | `LINK_MYSQLI_HELLOPRO_DATA` | Nom de la variable (ou constante) **mysqli** qu'il définit |
| `HELLODATA_CAMPAGNE_BDD_INCLUDE` / `_LIEN` | ceux de `acheteur` | Connexion qui lit et écrit les tables de campagne |
| `HELLODATA_CAMPAGNE_BASE` | `edgb2b` | Base des 4 tables `historique_campagne_*_ia` (noms qualifiés `edgb2b.table`) |

### À vérifier sur le serveur avant le premier test

Ces points n'ont **pas** pu être vérifiés par l'agent :

1. **Le fichier de connexion et le nom du lien.** Le défaut vient du plan (Task A5), sans vérification. La lecture de `no_read_access/` a été refusée au compte SFTP. Il faut un lien **mysqli**, pas `mysql_*`.
2. **`acheteur` dans la base par défaut de ce lien** : le moteur écrit `FROM acheteur` sans préfixe.
3. **Droits d'écriture sur `edgb2b`** pour la connexion de campagne : `INSERT`, `UPDATE`. Toutes les requêtes de campagne qualifient leurs tables (`edgb2b.historique_…`) et n'ont jamais besoin d'une jointure entre bases : `acheteur` et l'historique sont lus par des requêtes séparées.
4. **Tables en InnoDB** : les transactions par lot et par appel en dépendent.
5. **Version de PHP** : 7.0 au minimum, avec `mysqlnd` (pour `mysqli_stmt_get_result`). Le code est vérifié sans construction plus récente.
6. **Propagation de `Authorization`** : si un bon jeton rend quand même `401`, ajouter au `.htaccess` du dossier `SetEnvIf Authorization "(.*)" HTTP_AUTHORIZATION=$1`. Le routeur lit aussi `REDIRECT_HTTP_AUTHORIZATION`.

## Comportement et contrat

- **Sélection** (`comptage`, `echantillon`, `export`) : le plan de 2026-09-21, avec une correction. `echantillon` et `export` lisent une ligne de sonde pour savoir s'il reste une page. Le code du plan demandait `taille + 1` lignes, que l'assemblage refusait au-delà de 2000 : un export par défaut (2000 lignes) échouait toujours en `limite_invalide`. La ligne de sonde est maintenant ajoutée après le contrôle du plafond.
- **Codes d'erreur** : chaque exception porte son code en tête (`groupe_vide: …`), renvoyé tel quel (`{"erreur": "groupe_vide"}`) pour que le LLM corrige son appel. Un message MySQL ne sort jamais : il va au journal (`error_log`, préfixe `[mcp-hellodata]`).
- **`recup_acheteur`** (spec campagnes § 7) :
  - parcours par lots de 500, du plus grand `id_acheteur` au plus petit, au plus 100 000 fiches et 100 secondes par appel (`epuise = false` au-delà) ;
  - numéro lu dans `telephone_mobile_a`, la seule colonne de téléphone confirmée sur `acheteur`. En `sms`, seuls les 06/07 passent ; en `appel`, un fixe est valide ;
  - une transaction par lot : identité, rattachement des fiches, `est_actif` (la fiche de plus grand `id_acheteur` du numéro), puis réservation `INSERT IGNORE` (`uq_campagne_numero` arbitre deux conversations simultanées) ;
  - CSV renvoyé dans le champ `csv` (BOM, `;`) : `telephone_normalise;id_acheteur;civilite;nom;prenom;raison_sociale;cp;ville`, sur la fiche active ;
  - campagne existante avec un autre canal ou une autre date → `409 campagne_incoherente`.
- **Feuilles `hist_*`** : `hist_jamais_contacte`, `hist_derniere_categorie`, `hist_derniere_reponse_il_y_a_plus_de_jours`, `hist_campagne`. Une feuille `hist_*` sous un `OU` / `NON` mêlé à des critères `acheteur` est refusée (`hist_hors_et_racine`). Hors `recup_acheteur`, elle est refusée en `critere_historique_hors_campagne`. Un numéro sans réponse vaut « faux », pas NULL : `NON(dernière = non)` le laisse passer.
- **`enregistrer_reponses`** (spec § 8) :
  - numéro inconnu → `inconnus` ; connu mais hors campagne → `hors_campagne` ; rien n'est écrit pour l'un ni l'autre ;
  - un renvoi identique rend le même résultat ;
  - une réponse commençant par `STOP` (casse indifférente) devient `negative_stop` ;
  - `negative_stop` → `statut_contact = ne_plus_contacter`, jamais levé par une réponse ultérieure ;
  - campagne inconnue → `404 campagne_inconnue`.
- **Accès direct** : une action appelée sans passer par `index.php` (par exemple `…/actions/bilan_campagnes.php`) rend `404`. Elle ne s'exécute pas, ce qui contournerait le Bearer.

## Tests locaux (déjà passés le 2026-10-04)

Depuis la racine du dépôt :

```bash
php site/admin/mcp/hellodata/test/tout.php                 # 10 fichiers de tests unitaires
php site/partenaires_externes/mcp/hellodata/test/tout.php  # 3 fichiers
php site/admin/mcp/hellodata/test/routes.php               # routes = actions lues dans le client Go
node site/admin/mcp/hellodata/test/verifier_syntaxe.mjs site/admin/mcp/hellodata site/partenaires_externes/mcp/hellodata
sh site/admin/mcp/hellodata/test/integration/lancer.sh     # MySQL 8 jetable (Docker) + php -S : 56 assertions
```

`lancer.sh` crée la base (`test/integration/schema.sql` : `acheteur` réduit
et les 4 tables de la spec telles quelles), sert le BO et le FRONT par
`php -S`, et joue le scénario complet :
- comptage, pages 1 et 2, export ;
- deux appels de `recup_acheteur` sur la même campagne, qui ne ressortent aucun numéro deux fois ;
- un doublon et son `est_actif` ;
- un changement de numéro ;
- les feuilles d'historique ;
- le webhook (STOP, hors campagne, renvoi) ;
- l'aller-retour : un STOP reçu par le FRONT exclut le numéro de la sélection suivante du BO.

## Tests post-déploiement (sur dev)

Avec `BO=https://<hôte BO dev>/admin/mcp/hellodata/index.php`,
`FRONT=https://<hôte FRONT dev>/partenaires_externes/mcp/hellodata/index.php`,
`T` et `W` les deux jetons :

```bash
# 1. Auth : 401 sans jeton et avec un mauvais jeton, 200 avec le bon
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$BO?action=comptage" -d '{}'
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Authorization: Bearer mauvais' "$BO?action=comptage" -d '{}'
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=comptage" \
  -d '{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]}}'

# 2. Accès direct à une action : 404
curl -s -o /dev/null -w '%{http_code}\n' "${BO%index.php}actions/bilan_campagnes.php"

# 3. Échantillon page 1 puis page 2 (cursor = next_cursor) : aucun id_acheteur commun
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=echantillon" \
  -d '{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]},"taille":5}'

# 4. Export : dernière ligne « # fin-export;5;<id> »
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=export" \
  -d '{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]},"taille":5}' | tail -n 1

# 5. Campagne de recette (code dédié), 20 numéros, puis un second appel : aucun numéro en commun
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=recup_acheteur" \
  -d '{"campagne":{"code":"recette-2026-10","nom":"Recette","canal":"sms","date_campagne":"2026-10-05"},
       "n":20,"cree_par":"<votre e-mail>","filtre":{"critere":"region","comparateur":"dans","valeur":[6]}}'

# 6. Webhook : une réponse STOP sur un numéro du CSV, puis le bilan
curl -s -X POST -H "Authorization: Bearer $W" "$FRONT?action=enregistrer_reponses" \
  -d '{"code_campagne":"recette-2026-10","reponses":[{"telephone":"<numéro du CSV>","reponse_brute":"STOP","categorie":"positive"}]}'
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=bilan_campagnes" -d '{"code":"recette-2026-10"}'
```

Attendus :
1. `401`, `401`, puis `{"code":200,"response":{"count":…}}`.
2. `404`.
3. Aucun `id_acheteur` commun entre les deux pages.
4. Une dernière ligne de la forme `# fin-export;5;<id>`.
5. `selectionnes` = 20, `csv` non vide ; le second appel compte les 20 premiers en `exclus.deja_dans_campagne`.
6. `stop_force` = 1, puis `negative_stop` = 1 au bilan.

Après la recette, supprimer les lignes de la campagne `recette-2026-10` dans
`edgb2b.historique_campagne_suivi_ia` et `edgb2b.historique_campagne_ia`. Les
identités et les rattachements créés restent valables : ils sont alimentés au
fil de l'eau, par conception.

## Limites connues

- **Numéros factices** : la liste (`telephone_factices()`) est à compléter à la recette. Le format réel des numéros n'a pas pu être audité.
- **Droit au téléphone** : le CSV de `recup_acheteur` porte le numéro pour tout appelant autorisé (admin ou grant). La précondition 5 de la spec du 2026-09-21 n'est pas tranchée.
- **Critères disponibles** : 23 critères sur `acheteur` seulement. Les familles DI, emailing et rubrique attendent un schéma confirmé (plan, fin de la Phase A).
- **Sécurité, constaté pendant ce travail** : un ancien fichier de connexion portant un mot de passe de base de données en clair se trouve sous la racine web du BO de dev. Son emplacement a été transmis à l'équipe hors de ce dépôt public.
