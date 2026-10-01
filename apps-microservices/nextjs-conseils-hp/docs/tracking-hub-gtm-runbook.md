# Runbook GTM / GA4 — tracking HUB (pas à pas)

> Conteneur **GTM-PBBSTMC** · Propriété GA4 **G-DQTV4SHNME**
> Durée : ~45 min. Ne rien publier avant l'étape D.

**Ordre imposé.** Les dimensions personnalisées GA4 **ne sont pas rétroactives** : les
événements reçus avant leur déclaration ne seront jamais exploitables pour ces dimensions.
D'où GA4 (A) avant GTM (B), et publication (D) seulement après recette (C).

**Décisions déjà prises** (2026-08-06) : le paramètre s'appelle `email_check_result` (et non
`result`), et `hub_form_submission` sera marqué key event à l'étape E.

**Révision du 2026-08-24 — le quota GA4 est presque plein.** Cette étape demandait 11
dimensions ; il n'en reste que **3 disponibles** (47 créées sur 50, portée Événement).
Le plan a été refait en conséquence : 3 à créer, 4 déjà couvertes, 4 abandonnées,
2 renvoyées vers BigQuery. Le raisonnement complet est en annexe, à la fin de ce
document — le lire avant de s'écarter de la liste ci-dessous.

---

# A. GA4 — déclarer les 3 dimensions

**A1.** Ouvrir <https://analytics.google.com> → sélectionner la propriété **G-DQTV4SHNME**.

**A2.** En bas à gauche, cliquer sur **Admin** (la roue crantée).

**A3.** Colonne « Affichage des données » → **Définitions personnalisées**.

**A4.** Onglet **Dimensions personnalisées** → vérifier le compteur via **Informations sur
les quotas** (en haut à droite). Au 2026-08-24 : **47 créées sur 50** en portée Événement.
→ S'il reste moins de 3 emplacements, **s'arrêter** : il faudra d'abord archiver des
dimensions mortes avec l'équipe analytics (cf. annexe).

**A5.** Bouton bleu **Créer des dimensions personnalisées**, en haut à droite.
Pour chaque ligne : remplir les 3 champs, **Enregistrer**, puis recommencer.

| Nom de la dimension | Portée | Paramètre d'événement | Ce qu'elle permet |
|---|---|---|---|
| HUB – Groupe | Événement | `hub_group` | Séparer les tunnels `projet` / `guide` / `engagement`. `hub_guide_download` est émis par les DEUX : sans elle, le tunnel guide paraît deux fois plus performant. |
| HUB – Emplacement CTA | Événement | `hub_entry_point` | Savoir laquelle des 6 portes convertit (`hero`, `banner_guide`, `cta_final`, `bloc_thematique`, `popup_scroll`, `sticky_mobile`). C'est la dimension qui décide de ce qu'on garde. |
| HUB – Chemin de conversion | Événement | `hub_lead_path` | Distinguer `complet` (vrai lead), `reconnu` (lead sans nouvelles coordonnées) et `deja_converti` (re-téléchargement, **pas** une conversion). Sans elle, on surestime. |

**Convention de préfixe** (arbitrée le 2026-08-24, à l'occasion de cette création) :

- **préfixe `hub_`** → paramètre PROPRE au HUB, dimension GA4 dédiée ;
- **sans préfixe** → paramètre DÉLIBÉRÉMENT partagé avec le funnel devis historique
  (`step_name`, `step_index`, `user_known_status`), dont la dimension existe depuis 2022.

Le préfixe rend visible, dans la liste GA4, ce qui appartient au HUB. Le code applique la
même règle (`lib/analytics/hub.ts`, interface `HubEventParams`), et un test la verrouille.

⚠️ Le champ **Paramètre d'événement** doit être saisi **exactement** comme ci-dessus :
minuscules, underscores, sans espace. Une faute de frappe donne une dimension toujours vide,
sans aucun message d'erreur.

**A6. Ne rien créer pour ces quatre-là — elles existent déjà.**

| Paramètre poussé par le HUB | Dimension existante | Créée le |
|---|---|---|
| `step_name` | `step_name` — « Etapes des différents tunnel (contact, devis, …) » | 26 oct. 2022 |
| `step_index` | `step_index` — « Etapes des différents tunnels (contact, devis) » | 26 oct. 2022 |
| `user_known_status` | `user_known_status` — « Statut user (connu ou non) » | 26 oct. 2022 |
| `page_template` | `page_template` — « Template de page » | 26 oct. 2022 |

Ce n'est pas une coïncidence : `lib/analytics/hub.ts` reprend délibérément le vocabulaire
du funnel devis historique (`questionStepName()` produit `1ere-question`, `2eme-question`…
comme `pushQuoteFormFunnel`). Ces quatre dimensions sont donc exploitables **dès la
publication, sans consommer d'emplacement**.

`page_template` est la plus importante des quatre : c'est elle qui isole les pages HUB
(`page_hub`) du reste du site dans tous les rapports.

⚠️ **Ne pas les recréer sous un autre nom.** GA4 refuserait le doublon de paramètre, et un
second essai « HUB – Étape » sur `step_name` échouerait — ou pire, consommerait un
emplacement pour rien s'il visait un paramètre légèrement différent.

---

# B. GTM — importer la configuration

Le fichier `docs/gtm-hub-import.json` crée **25 variables + 1 déclencheur + 1 tag** d'un coup.

**B1.** Ouvrir <https://tagmanager.google.com> → conteneur **GTM-PBBSTMC**.

**B2.** Menu de gauche → **Administration** → colonne Conteneur → **Importer un conteneur**.

**B3.** **Sélectionner un fichier de conteneur** → choisir `docs/gtm-hub-import.json`.

**B4.** Choisir un espace de travail : **Nouveau** → le nommer `Tracking HUB`.

⚠️ **Ne pas importer dans `Default Workspace`**, pour deux raisons.

La première est le retour en arrière : l'espace par défaut **ne peut pas être supprimé**.
Annuler l'import y demanderait de révoquer les 28 modifications une par une, alors qu'un
espace dédié se jette d'un clic.

La seconde est plus gênante : des modifications non publiées dans `Default Workspace` sont
embarquées par **la prochaine publication de n'importe qui**. Un collègue qui publie un
correctif sans regarder le détail mettrait le tracking HUB en ligne avec — potentiellement
avant la recette, ou avant que les dimensions GA4 de l'étape A n'existent.

**B5.** Option d'importation : ☑ **Fusionner**.

Le sous-choix (« Écraser » ou « Renommer » les éléments en conflit) ne concerne que les
éléments portant le **même nom** qu'un existant. Aucun des nôtres n'entre en collision
(préfixes `DL - `, `GA4 - HUB events`, `HUB - tous les evenements`), donc les deux options
donnent le même résultat. « Écraser » est préférable pour une éventuelle ré-importation
corrective : elle mettra à jour les éléments HUB au lieu d'en créer des doublons.

⚠️ **Ne PAS choisir « Remplacer »** (l'option du dessus, hors « Fusionner ») : celle-là
remplacerait l'espace de travail entier, donc tout le tracking devis et conseils.

**B6.** Vérifier l'aperçu. Il doit annoncer **0 Modifications · 28 Ajoutées · 0 Suppressions**
(26 variables + 1 balise + 1 déclencheur).

**C'est ce « 0 modification / 0 suppression » qui garantit que rien d'existant n'est touché.**
Si des modifications ou suppressions apparaissent, **annuler et me le dire**.

ℹ️ L'import n'écrit que dans l'espace de travail : **rien n'est en ligne** tant que l'étape D
n'est pas faite.

**B7.** Vérifier que la variable intégrée **Event** est active :
`Variables` → section « Variables intégrées » → **Configurer** → cocher **Event** si absente.
Sans elle, le tag n'a pas de nom d'événement et n'enverra rien d'exploitable.

**B8.** Vérifier le tag importé : `Tags` → **GA4 - HUB events** → l'ouvrir.
- Nom de l'événement = `{{Event}}`
- ID de mesure = `G-DQTV4SHNME`
- Déclenchement = `HUB - tous les evenements`
- 26 paramètres dans le tableau

> **Si l'import échoue** (fichier refusé) : tout est créable à la main, la liste exacte des
> variables et du tag est dans `docs/tracking-hub-gtm.csv`. Me le signaler, je détaille.

## Comment revenir en arrière

| Situation | Marche à suivre |
|---|---|
| Import fait, **pas encore publié** | `Espaces de travail` → `Tracking HUB` → menu **⋮** → **Supprimer l'espace de travail**. Les 28 éléments disparaissent, aucune trace. |
| **Déjà publié** | `Versions` → sélectionner la version précédente → **Publier**. Le conteneur revient à son état antérieur. |
| Import fait dans `Default Workspace` par erreur | L'espace par défaut ne se supprime pas : révoquer les modifications une par une dans la liste des modifications de l'espace de travail. |

---

# C. Recette — en prévisualisation, AVANT de publier

**C1.** Dans GTM, bouton **Prévisualiser** (en haut à droite) → saisir l'URL de recette →
**Connect**. Un nouvel onglet s'ouvre avec le bandeau Tag Assistant.

**C2.** Dans un autre onglet : GA4 → **Admin** → **DebugView**.

**C3.** Sur la page, **accepter les cookies** — sinon le Consent Mode bloque l'envoi vers GA4
et le DebugView restera vide (les événements seront quand même visibles dans Tag Assistant).

**C4.** Dérouler les 4 contrôles ci-dessous. Ce sont ceux qui échouent en silence.

| # | Action | Où regarder | Attendu |
|---|---|---|---|
| 1 | Charger la page HUB | DebugView | **exactement un** `page_view` — ni zéro, ni deux |
| 2 | Charger une page conseils classique | DebugView | **un** `page_view`, `page_template = conseils` — l'existant ne doit pas bouger |
| 3 | Questionnaire complet, **puis** clic sur un CTA guide | Tag Assistant → onglet **Variables** de l'événement guide | ni `step_name`, ni `answer_label`, ni `steps_answered` — aucune valeur du parcours précédent |
| 4 | Parcours HUB complet | Tag Assistant → liste des événements | aucun `quote_form_funnel`, `quote_funnel_validation`, `Popup_Appel_Offre`, `eec.add` |

**C5.** Vérifier dans DebugView qu'un `hub_form_submission` porte bien ses paramètres :
`hub_group`, `hub_page_id`, `hub_page_uri`, `hub_lead_path`, `user_known_status`,
`product_category5` (avec un **underscore**, pas un point).

⚠️ **C5bis — le contrôle qui attrape la panne silencieuse.** Sur ce même événement,
vérifier que le nom du paramètre est bien `hub_lead_path` et **non** `lead_path`, et
`hub_entry_point` et **non** `entry_point`. GA4 rattache une valeur à sa dimension par
correspondance STRICTE de nom : une divergence ne produit aucune erreur, seulement une
dimension à `(not set)` pour toujours. C'est exactement le piège qu'on a évité le
2026-08-24, les dimensions ayant été créées avec le préfixe alors que le code envoyait
encore les noms courts.

**C6.** Le reste des 36 scénarios est dans `docs/tracking-hub-recette.csv`. Me dire quand
l'étape D est faite : je les rejoue tous et je te donne le verdict ligne par ligne.

---

# D. Publier

**D1.** GTM → bouton **Envoyer** (en haut à droite).

**D2.** Nom de la version : `Tracking HUB - 21 evenements`
Description : `Ajout du tracking des pages HUB projet. 25 variables, 1 declencheur ^hub_, 1 tag GA4 vers G-DQTV4SHNME. Aucun tag existant modifie.`

**D3.** **Publier**.

⚠️ Publier de préférence à une heure creuse, et **recharger une page conseils classique juste
après** pour vérifier que rien n'a bougé. C'est le seul lot qui touche un conteneur partagé.

---

# E. GA4 — exploitation

**E1. Marquer la conversion.**
`Admin` → `Événements` (ou `Données` → `Événements`) → chercher `hub_form_submission` →
activer l'interrupteur **Marquer comme événement clé**.
⚠️ L'événement n'apparaît dans cette liste **qu'après avoir été reçu au moins une fois**.
Faire donc au moins une conversion de test après l'étape D.

À savoir : cela ajoute les leads HUB au total « conversions » de la propriété. Le total reste
décomposable par nom d'événement, et le marquage est réversible à tout moment.

**E2. Créer l'entonnoir.**
`Explorer` → `Exploration en entonnoir`. Étapes, dans l'ordre :

1. `hub_form_view`
2. `hub_form_start`
3. `hub_form_step`
4. `hub_form_email_submit`
5. `hub_email_check`
6. `hub_form_submission`

Segmentation : dimension standard **Chemin de page + chaîne de requête**, pour comparer les
3 verticales dans un seul rapport. (Et non « HUB – Page ID », abandonnée le 2026-08-24 :
elle faisait doublon avec cette dimension standard, que GA4 fournit sans consommer de
quota. Les trois chemins sont `/lancer-elevage-poules-pondeuses-1000-projet.html`,
`/ouvrir-food-truck-1001-projet.html`, `/ouvrir-laverie-automatique-1002-projet.html`.)

Pour ne garder que les pages HUB, ajouter un filtre **`page_template` = `page_hub`** —
c'est le rôle de cette dimension, qui existait déjà dans la propriété.

⚠️ **Huit événements commencent par `hub_form_`, un seul est la conversion.** Dans la liste
alphabétique, `hub_form_submission` voisine avec `hub_form_email_submit` et
`hub_form_coordinates_submit`. Prendre le mauvais en dernière étape ne lève aucune erreur —
seulement un taux de conversion faux, et plus flatteur que la réalité.

**E3. Conservation des données.**
`Admin` → `Conservation des données` → passer à **14 mois** si ce n'est pas déjà le cas.
Le défaut de 2 mois fait perdre la première cohorte d'un POC jugé à 3 mois.

**E4. Deux dénominateurs à ne pas se tromper** (détail dans `docs/tracking-hub.md`) :
- abandon aux coordonnées → dénominateur = `hub_email_check` avec `email_check_result = unknown`,
  **pas** `hub_form_email_submit` ;
- conversion de la pop-up → compter en **sessions** ou **utilisateurs**, jamais en nombre
  d'événements (`sessionStorage` est par onglet, GA4 compte à travers les onglets).

---

# Annexe — pourquoi 3 dimensions et non 11

> Ajoutée le 2026-08-24, après avoir constaté que la propriété était à **47 dimensions
> créées sur 50** en portée Événement, avant toute intervention HUB.

## Le raisonnement

Le plan initial demandait 11 dimensions. Trois emplacements restaient. Plutôt que de
sacrifier huit mesures, on a repris la liste ligne à ligne — et il s'est avéré qu'elle
contenait des redondances qu'un quota confortable avait laissées passer.

**Quatre paramètres étaient déjà couverts** (`step_name`, `step_index`,
`user_known_status`, `page_template`), parce que le code HUB reprend délibérément le
vocabulaire du funnel devis historique. Gratuit.

**Trois étaient des doublons** :

- `hub_page_id` et `hub_page_uri` répètent la dimension standard **Chemin de page**, que
  GA4 fournit nativement. Un paramètre personnalisé ne se justifie que pour ce que GA4 ne
  peut pas déduire seul — l'URL, il la connaît.
- `step_id` (id métier : `budget`, `vehicule`…) répond à « quelle question fait fuir »,
  quand `step_name` répond à « quelle position fait fuir ». La seconde formulation se
  compare entre les trois verticales, la première non. On garde celle qui se compare.
- `email_check_result` est le verdict brut du serveur, `user_known_status` sa traduction
  métier. La seconde existe déjà et est gratuite.

**Deux sont partis en BigQuery** : `source_block` (quel bloc envoie du trafic vers les
articles) et `download_trigger` (le téléchargement automatique fonctionne-t-il). Ce sont
des questions d'analyse ponctuelle, pas de pilotage quotidien.

**Restaient exactement trois** : `hub_group`, `hub_entry_point`, `hub_lead_path`.
(Les deux derniers s'appelaient `entry_point` et `lead_path` jusqu'à leur création
en GA4 : le préfixe a été ajouté à ce moment-là, et répercuté dans le code.)

## Pourquoi BigQuery change la donne

L'export BigQuery est **actif** sur cette propriété (projet `big-query-ga4-387913`).
Chaque événement y est exporté avec son champ `event_params`, qui contient **tous** les
paramètres, sans notion de quota ni de déclaration préalable.

La non-rétroactivité des dimensions ne concerne donc que l'**interface** GA4. Les 26
paramètres HUB seront intégralement disponibles en SQL dès la publication, y compris ceux
qu'on renonce à déclarer.

D'où la règle qui a guidé l'arbitrage : **déclarer ce dont a besoin quelqu'un qui ouvre
GA4 et clique ; laisser à BigQuery ce dont a besoin quelqu'un qui écrit du SQL.**

## Ce qu'on a écarté, et pourquoi

Deux dimensions existantes étaient sémantiquement réutilisables : `funnel_context` (« de
quel tunnel s'agit-il ? La valeur est basée sur le point de départ » — très proche
d'`hub_entry_point`) et `form_type` (proche de `form_id`).

Écartées volontairement. Réutiliser une dimension, c'est verser ses valeurs dans le même
seau que le funnel devis historique : tout rapport existant qui ne filtre pas par nom
d'événement se met à mélanger HUB et legacy. On gagne un emplacement et on abîme un
tableau de bord dont quelqu'un d'autre dépend. Le compte tombant juste sans cela, le
risque n'avait pas lieu d'être pris.

## Le sujet qui reste ouvert

**47 dimensions sur 50, ce n'est pas tenable durablement** — le prochain projet sera
bloqué pour de bon. Plusieurs semblent liées à des parcours anciens (`add_to_cart_type`,
`add_to_cart_wording`, `characteristic_infos`, `contains_form`, `optimize_experiment_id` et
`optimize_variant_id` — Google Optimize est arrêté depuis 2023).

L'archivage d'une dimension libère son emplacement. Mais c'est un ménage à mener avec
l'équipe qui les a créées, pas une décision à prendre dans l'urgence d'une mise en ligne :
archiver une dimension encore utilisée casse silencieusement les rapports qui s'en servent.
À porter comme un sujet à part entière.
