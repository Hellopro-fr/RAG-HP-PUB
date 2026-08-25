# Runbook GTM / GA4 — tracking HUB (pas à pas)

> Conteneur **GTM-PBBSTMC** · Propriété GA4 **G-DQTV4SHNME**
> Durée : ~45 min. Ne rien publier avant l'étape D.

**Ordre imposé.** Les dimensions personnalisées GA4 **ne sont pas rétroactives** : les
événements reçus avant leur déclaration ne seront jamais exploitables pour ces dimensions.
D'où GA4 (A) avant GTM (B), et publication (D) seulement après recette (C).

**Décisions déjà prises** (2026-08-06) : le paramètre s'appelle `email_check_result` (et non
`result`), et `hub_form_submission` sera marqué key event à l'étape E.

---

# A. GA4 — déclarer les 11 dimensions

**A1.** Ouvrir <https://analytics.google.com> → sélectionner la propriété **G-DQTV4SHNME**.

**A2.** En bas à gauche, cliquer sur **Admin** (la roue crantée).

**A3.** Colonne « Affichage des données » → **Définitions personnalisées**.

**A4.** Onglet **Dimensions personnalisées** → compter les lignes existantes.
La limite est de **50** dimensions de portée Événement. On en ajoute 11.
→ Si le total dépasserait 50, **s'arrêter et me le dire**.

**A5.** Bouton bleu **Créer des dimensions personnalisées**, en haut à droite.
Pour chaque ligne du tableau : remplir les 3 champs, **Enregistrer**, puis recommencer.

| Nom de la dimension | Portée | Paramètre d'événement |
|---|---|---|
| HUB – Groupe | Événement | `hub_group` |
| HUB – Page ID | Événement | `hub_page_id` |
| HUB – URI page | Événement | `hub_page_uri` |
| HUB – Emplacement CTA | Événement | `entry_point` |
| HUB – Étape | Événement | `step_name` |
| HUB – Étape (id métier) | Événement | `step_id` |
| HUB – Chemin de conversion | Événement | `lead_path` |
| HUB – Contact connu | Événement | `user_known_status` |
| HUB – Verdict e-mail | Événement | `email_check_result` |
| HUB – Bloc source | Événement | `source_block` |
| HUB – Déclencheur téléchargement | Événement | `download_trigger` |

⚠️ Le champ **Paramètre d'événement** doit être saisi **exactement** comme ci-dessus :
minuscules, underscores, sans espace. Une faute de frappe donne une dimension toujours vide,
sans aucun message d'erreur.

**A6.** Dans la liste, chercher **`page_template`**.
- Présente → rien à faire.
- Absente → la créer : nom `Type de page`, portée Événement, paramètre `page_template`.
Sans elle, impossible de séparer les pages HUB (`page_hub`) des pages conseils.

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
`hub_group`, `hub_page_id`, `hub_page_uri`, `lead_path`, `user_known_status`,
`product_category5` (avec un **underscore**, pas un point).

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

Segmentation : dimension **HUB – Page ID**, pour comparer les 3 verticales dans un seul
rapport.

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
