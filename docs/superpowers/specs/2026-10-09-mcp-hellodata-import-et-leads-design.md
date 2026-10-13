# MCP HelloData — import de campagnes, colonnes de recup_acheteur, leads transmis

**Date :** 2026-10-09
**Branche :** `features/mcp-hellodata-import-campagnes` (depuis `features/mcp-hellodata-grant-contacts`)
**Statut :** conception — rien n'est implémenté
**Étend :** `2026-09-28-mcp-hellodata-campagnes-design.md` (tables, normalisation, `recup_acheteur`, webhook)
**Origine :** demande d'un utilisateur du MCP (2026-10-09) — historiser toutes les campagnes SMS clients (EDF, Hyundai…), y compris celles envoyées hors MCP, et suivre la chaîne envoyé → réponse → lead transmis.

---

## 1. Besoin

1. **Inscrire une liste fournie** (numéros mobiles ou `id_acheteur`) dans une campagne, avec la **date réelle d'envoi**, et savoir quels numéros sont inconnus de la base. Premier cas : les 6 campagnes du 2026-10-07 (`EDF_20261007_P1..P3`, `HYU_20261007_P1..P3`) et leurs 47 retours.
2. **Statut « lead transmis »** avec la date de transmission au client.
3. **Enregistrer la campagne au moment de l'extraction**, dédoublonnée — sans passer par `export_csv`, qui ne trace rien.

## 2. État constaté (2026-10-09, lecture seule)

- `hellodata_bilan_campagnes` → `{"campagnes": []}` ; les 4 tables `historique_campagne_*` (base `edgb2b`) ont **0 ligne**. `historique_campagne_acheteur_ia` ne se remplit que pendant `recup_acheteur` : aujourd'hui **tout numéro est inconnu** du webhook, qui n'écrirait rien (pas même un STOP) pour les 47 retours.
- `historique_campagne_suivi_ia.date_campagne = NOW()` à la réservation et `date_historique = NOW()` à la réponse : un historique saisi après coup serait daté du jour de saisie, et `hist_derniere_reponse_il_y_a_plus_de_jours` serait faussé.
- `acheteur.telephone_mobile_a` est **indexé** (B-tree, cardinalité ≈ 1,5 M). Sur 5 624 194 fiches : 3 938 683 vides, 1 627 774 au format compact `^0[1-9][0-9]{8}$` (dont 1 617 460 mobiles `06`/`07`), **57 737 dans un autre format**. Une recherche par égalité sur le numéro normalisé couvre donc ≈ 96,6 % des numéros renseignés ; les autres reviennent `inconnus`.
- `echantillon` / `export_csv` sont des lectures pures : ni la campagne ni l'historique ne sont écrits (seule trace : une ligne de log du wrapper `demandeur=… lignes=…`).
- La copie locale du moteur (`site/admin/mcp/hellodata/`, non trackée) date du 2026-09-21 et ne contient ni `recup_acheteur`, ni `bilan_campagnes`, ni le webhook : **récupérer la version déployée sur Ecritel avant de coder**.

## 3. Décisions

| # | Question | Décision |
|---|---|---|
| D1 | Où enregistrer « à l'extraction » ? | **`recup_acheteur` reste le seul outil qui écrit l'historique.** `echantillon` / `export_csv` restent des lectures pures (décision utilisateur du 2026-10-09, option B) |
| D2 | Pourquoi pas un paramètre `campagne` sur `export_csv` ? | Un appel d'exploration marquerait des contacts comme shootés sans annulation automatique ; l'export pagine par fiche alors qu'une campagne compte un numéro = un contact ; `uq_campagne_numero` ne garantit le dédoublonnage qu'au point d'écriture |
| D3 | Ce qui manquait à `recup_acheteur` pour remplacer l'export | Le choix des colonnes (§ 4.1) et un aperçu sans écriture (§ 4.2) |
| D4 | Campagnes déjà envoyées | Nouvel outil **`inscrire_contacts`** (§ 5), distinct de `recup_acheteur` : pas de parcours, pas de borne `n`, pas d'exclusion — il enregistre un fait |
| D5 | « Lead transmis » | **Colonne** `date_lead_transmis` sur le suivi, **pas** une 4e valeur de `categorie` : `categorie` est le classement de la réponse et alimente `tag`, `bilan` et `hist_derniere_categorie` ; l'écraser perdrait le `positive` qui précède le lead |
| D6 | Date des réponses saisies après coup | Champ optionnel `date_reponse` sur `enregistrer_reponses` (§ 6) |

## 4. `recup_acheteur` — extensions

### 4.1 `colonnes` (optionnel)

- Même catalogue, même `enum` et mêmes restrictions que `export_csv` (`internal/tools/colonnes.go` ↔ `requete.php`) ; `email` / `mobile` exigent admin ou grant hellodata (`droitContacts`), transmis au moteur par `colonnes_restreintes_autorisees`, comme pour l'export.
- **Absent** → CSV actuel inchangé (`telephone_normalise;id_acheteur;civilite;nom;prenom;raison_sociale;cp;ville`) : rétro-compatible.
- **Présent** → `telephone_normalise` toujours en **première** colonne (identité de campagne, nécessaire pour rapprocher les réponses), puis les colonnes demandées dans l'ordre donné, lues sur la **fiche active** du numéro.
- Le ticket signé de `download.php` porte `colonnes` et le droit restreint, comme celui de l'export (borne `lien_trop_long` inchangée : les 26 noms tiennent largement).
- Description de l'outil : même consigne que `export_csv` — montrer la liste des colonnes à l'utilisateur et le laisser choisir.

### 4.2 `simulation` (booléen, défaut `false`)

- Même parcours, mêmes exclusions et feuilles `hist_*`, même dédoublonnage par numéro, **aucune écriture** : ni campagne, ni identité, ni rattachement, ni suivi. Le dédoublonnage du parcours se fait en mémoire ; l'identité existante (`statut_contact`, réservations de la campagne si son code existe) est lue sans être modifiée.
- Sortie : les compteurs habituels avec `selectionnes` = nombre qui **serait** réservé, `simulation: true`, **pas** d'`url_csv`.
- `campagne_incoherente` reste vérifié si le code existe.

### 4.3 Descriptions de `echantillon` / `export_csv`

Ajouter : « lecture seule, rien n'est enregistré dans l'historique ; pour une liste réellement envoyée, utiliser `hellodata_recup_acheteur` ».

## 5. Nouvel outil `inscrire_contacts` (BO)

`POST {base}/index.php?action=inscrire_contacts`, Bearer `HELLODATA_TOKEN`, enveloppe `{code, response}` habituelle ; `cree_par` au premier niveau, pris de `X-End-User-Email` par le wrapper.

Entrée :

```json
{
  "campagne": { "code": "EDF_20261007_P1", "nom": "EDF – Commerce alimentaire",
                "canal": "sms", "prestataire": "…", "message": "…",
                "date_campagne": "2026-10-07" },
  "contacts": [ { "telephone": "06…" }, { "id_acheteur": 1234567 } ]
}
```

- `campagne` : mêmes validations que `recup_acheteur` ; créée si absente, sinon `campagne_incoherente` si `canal` ou `date_campagne` diffèrent. `date_campagne` dans le futur → `date_future` (fait passé uniquement).
- `contacts` : 1 à 2000 éléments, chacun avec **exactement un** de `telephone` / `id_acheteur` (sinon `contact_invalide`). Au-delà, appels répétés sur la même campagne.

Rapprochement, par contact :

| Cas | Effet | Sortie |
|---|---|---|
| `telephone` non normalisable (§ 5 de la spec campagnes), ou non mobile en `sms` | rien | `invalides` |
| `id_acheteur` absent de `acheteur` | rien | `inconnus` |
| `id_acheteur` dont le numéro n'est pas normalisable / pas mobile en `sms` | rien | `invalides` |
| `telephone` normalisé : identité existante dans `acheteur_ia` | réutilisée | — |
| `telephone` normalisé : sinon fiches `acheteur` avec `telephone_mobile_a = :normalise` (index) | identité créée, fiches rattachées, `est_actif` recalculé | — |
| Aucune fiche pour ce numéro | rien (le suivi exige `id_acheteur`) | `inconnus` |
| Numéro déjà dans la campagne | rien (`INSERT IGNORE`) | `deja_dans_campagne` |
| Numéro présent deux fois dans la liste | une seule inscription | `doublons_liste` |
| Numéro en `ne_plus_contacter` | **inscrit quand même** (l'envoi a eu lieu) | listé dans `ne_plus_contacter` |
| Sinon | suivi écrit, fiche active, `date_campagne = <date_campagne> 00:00:00` | `inscrits` |

- Les recherches ne posent **pas** `bloquage_a = 0` : on enregistre un envoi qui a eu lieu, pas une sélection.
- Une transaction par appel ; renvoi identique = même résultat (`deja_dans_campagne` au second passage).

Sortie :

```json
{ "id_campagne": 3, "campagne_creee": true, "inscrits": 412,
  "deja_dans_campagne": 0, "doublons_liste": 2,
  "inconnus": ["06…"], "invalides": ["01…"], "ne_plus_contacter": [] }
```

Les listes rendent les valeurs **telles que reçues** (pas normalisées), pour que l'utilisateur les retrouve dans son fichier.

## 6. `enregistrer_reponses` — `date_reponse` (optionnel)

- Par réponse : `date_reponse` au format `AAAA-MM-JJ` ou `AAAA-MM-JJ HH:MM:SS` → `date_historique`. Absent → `NOW()` (inchangé).
- Refus `date_reponse_invalide` si dans le futur ou antérieure à la date du suivi (`suivi.date_campagne`, jour compris).
- Le reste du contrat (`ResultatReponses`, filet STOP, STOP hors campagne) est inchangé.

## 7. Lead transmis

DDL (manuelle, dev puis prod) :

```sql
ALTER TABLE historique_campagne_suivi_ia
  ADD COLUMN date_lead_transmis DATETIME NULL AFTER date_historique;
```

Nouvel outil **`marquer_leads`** (FRONT webhook, comme toute écriture sur les réponses — décision C3), Bearer `HELLODATA_WEBHOOK_TOKEN` :

```json
{ "code_campagne": "EDF_20261007_P1",
  "leads": [ { "telephone": "06…", "date_transmission": "2026-10-08" } ] }
```

- ≤ 500 leads par appel ; `date_transmission` optionnelle (défaut `NOW()`), refusée si future.
- Un lead exige un suivi dans la campagne avec `categorie = 'positive'` ; sinon le numéro est rendu dans `non_positifs` et rien n'est écrit.
- Sortie : `{ marques, inconnus: [...], hors_campagne: [...], non_positifs: [...] }`. Renvoi identique = même résultat ; une nouvelle date remplace l'ancienne.
- `bilan_campagnes` gagne `leads_transmis` (suivis avec `date_lead_transmis` non nul).
- Feuille `hist_lead_transmis` : **hors périmètre** de ce lot, à ajouter si la sélection en a besoin.

## 8. Wrapper Go

- `registry.go` : `colonnes` + `simulation` sur `recup_acheteur` ; nouveaux outils `inscrire_contacts` (client BO) et `marquer_leads` (client webhook) ; `date_reponse` sur `enregistrer_reponses` ; descriptions de `echantillon` / `export_csv` (§ 4.3).
- Validations avant le réseau : bornes (2000 contacts, 500 leads), un seul identifiant par contact, formats et non-futur des dates, colonnes connues et restreintes.
- `cree_par` toujours de l'en-tête, jamais des arguments.
- Gateway : aucun code à changer — `fetchHellodataTools` (`scoped_gateway.go`) relit la liste en direct pour chaque appelant ; seul son commentaire « six tools » passe à huit. Après déploiement, un admin rafraîchit le serveur pour que `/servers` persiste les 8 outils (`hellodata_catalog.go`).
- `CLAUDE.md` du service : la table des outils (6 sur cette branche) passe à 8.

## 9. Tests

**PHP** (harnais `_assert.php`, BO et FRONT) : chaque ligne du tableau du § 5 ; `inscrire_contacts` deux fois de suite (idempotence) ; `ne_plus_contacter` inscrit mais jamais levé ; `simulation` n'écrit dans aucune des 4 tables (comptes avant/après) ; `colonnes` absent = CSV historique à l'octet près ; `email`/`mobile` refusés sans droit ; `date_reponse` future ou antérieure à l'envoi refusée ; `marquer_leads` refuse un non-positif ; `bilan.leads_transmis`.

**Go** (`go test ./...`, `go vet ./...`) : schémas des 8 outils, validations du § 8, `cree_par` ignoré dans les arguments.

**Recette dev** : `recup_acheteur` en simulation puis réel (mêmes compteurs, CSV avec colonnes choisies) ; `inscrire_contacts` d'une liste mêlant connus, inconnus, invalides et doublons ; `enregistrer_reponses` avec `date_reponse` ; `marquer_leads` ; `bilan_campagnes`.

## 10. Déploiement et reprise du 2026-10-07

1. DDL `date_lead_transmis` (dev puis prod).
2. BO (`inscrire_contacts`, `recup_acheteur` étendu) puis FRONT (`marquer_leads`, `date_reponse`) — SFTP dev, recette, MEP prod ; seul le `.md` en PR (`site/CLAUDE.md`).
3. Wrapper **après** le PHP (sinon les nouveaux outils rendent 404), puis rafraîchissement admin du serveur hellodata dans le gateway.
4. Reprise : pour chacune des 6 campagnes, `inscrire_contacts` avec `date_campagne = 2026-10-07` → contrôler `inconnus` / `invalides` avec l'utilisateur → `enregistrer_reponses` des 47 retours avec leur `date_reponse` → `marquer_leads` → `bilan_campagnes`.

**Ne pas saisir les 47 retours avant l'étape 4** : sans inscription préalable, tous reviennent `inconnus` et rien n'est écrit, STOP compris.

## 11. Estimation

| Lot | Charge |
|---|---|
| Récupération du PHP déployé + DDL | 0,5 j |
| BO : `inscrire_contacts` + tests | 1,5 j |
| BO : `colonnes` + `simulation` sur `recup_acheteur` (+ `download.php`) | 1 j |
| FRONT : `date_reponse`, `marquer_leads` ; BO : `bilan.leads_transmis` | 1 j |
| Wrapper + tests (gateway : commentaire seulement) | 0,5–1 j |
| Recette dev et reprise du 2026-10-07 | 0,5 j |
| **Total** | **≈ 5 à 5,5 j** |

Dépendances hors équipe : dépôt FTP par le développeur PHP, DDL manuelle.

## 12. Questions ouvertes

1. **Numéros inconnus de `acheteur`** : non stockés (`suivi.id_acheteur NOT NULL`). Un STOP venant d'un tel numéro est perdu ; si ce numéro entre plus tard dans `acheteur`, il pourra être shooté. Accepté, ou faut-il une identité sans fiche (`id_acheteur` nullable dans le suivi) ?
2. **Les 57 737 numéros hors format compact** ne sont pas trouvés par égalité. Normaliser ces fiches une fois (hors périmètre) ou accepter qu'ils reviennent `inconnus` ?
3. **Taille des 6 listes** du 2026-10-07 : au-delà de 2000 par campagne, plusieurs appels ; une liste de plusieurs milliers de numéros transite par la conversation.
4. **Lead sans réponse positive enregistrée** : la règle `non_positifs` convient-elle, ou un lead peut-il être transmis sans réponse classée ?
5. Héritées de la spec campagnes et toujours ouvertes : droit au `telephone_normalise` dans le CSV de `recup_acheteur` (précondition 5), `max_allowed_packet`, `max_execution_time`, colonne `bloquage_a`.
