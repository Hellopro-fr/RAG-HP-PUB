# Métadonnées SEO des 3 pages HUB

> Fournies et validées par l'équipe le **2026-08-06**. Source de vérité pour les
> champs `meta` et `hero.titleParts` de `data/hub/*.ts`.
>
> Statut : **1000 appliquée**. 1001 et 1002 en attente de leur contenu — les
> métadonnées ci-dessous sont à reporter telles quelles à la création des fichiers.

---

## Règles communes

**Le `title` part VERBATIM.** `generateMetadata` utilise `title: { absolute: page.meta.title }`
(`app/hub/[hubSlug]/page.tsx:68`), ce qui court-circuite le template `%s | HelloPro` du root
layout. Le suffixe « | Hellopro » fait donc partie de la chaîne à saisir — le retirer en
croyant qu'il est dupliqué produirait un title sans marque.

**Le H1 est découpé en fragments**, celui marqué `accent: true` s'affichant en orange. Un seul
fragment accentué par page, portant le mot-clé principal.

**L'URL est dérivée, jamais saisie** : `hubCanonicalPath()` compose `/<slug>-<id>-projet.html`
à partir de `slug` et `id`. Elle alimente aussi la dimension GA4 `hub_page_uri`.

---

## 1000 — Élevage de poules pondeuses ✅ appliquée

| Champ | Valeur |
|---|---|
| URL | `/lancer-elevage-poules-pondeuses-1000-projet.html` |
| `slug` | `lancer-elevage-poules-pondeuses` |
| H1 | Lancer son élevage de **poules pondeuses** : du projet à la première ponte |
| `meta.title` | Créer un élevage de poules pondeuses \| Hellopro |
| `meta.description` | Créez votre élevage de poules pondeuses sans faux pas : normes, bâtiment, matériel, rentabilité. Guide gratuit et conseiller dédié à votre écoute. |

```ts
titleParts: [
  { text: 'Lancer son élevage de ' },
  { text: 'poules pondeuses', accent: true },
  { text: ' : du projet à la première ponte' },
],
```

---

## 1001 — Food truck ⏳ en attente de contenu

| Champ | Valeur |
|---|---|
| URL | `/ouvrir-food-truck-1001-projet.html` |
| `slug` | `ouvrir-food-truck` |
| H1 | Ouvrir un **food truck** rentable étape par étape |
| `meta.title` | Ouvrir un food truck : guide complet étape par étape \| Hellopro |
| `meta.description` | Lancez votre food truck sans rien oublier : démarches, matériel, emplacement, budget. Guide gratuit à télécharger, accompagnement sans engagement. |

```ts
titleParts: [
  { text: 'Ouvrir un ' },
  { text: 'food truck', accent: true },
  { text: ' rentable étape par étape' },
],
```

⚠️ **Le slug a changé** : le brief initial disait `creer-food-truck`, arbitré le 2026-08-06
en `ouvrir-food-truck` (cohérent avec `ouvrir-laverie-automatique` et avec le H1). Rien n'étant
en ligne, aucune redirection n'est nécessaire — mais ne plus y toucher après mise en ligne.

ℹ️ `title` de 62 caractères : Google le tronquera probablement après « étape par étape », et
« | Hellopro » ne sera pas affiché dans le snippet. Signalé et **accepté** — on applique la
valeur fournie.

---

## 1002 — Laverie automatique ⏳ en attente de contenu

| Champ | Valeur |
|---|---|
| URL | `/ouvrir-laverie-automatique-1002-projet.html` |
| `slug` | `ouvrir-laverie-automatique` |
| H1 | Ouvrir une **laverie automatique** : budget, rentabilité et étapes clés |
| `meta.title` | Ouvrir une laverie automatique : guide complet \| Hellopro |
| `meta.description` | Lancez votre projet de laverie automatique : budget, matériel, emplacement, réglementation et revenus prévisionnels. Guide gratuit et accompagnement dédié. |

```ts
titleParts: [
  { text: 'Ouvrir une ' },
  { text: 'laverie automatique', accent: true },
  { text: ' : budget, rentabilité et étapes clés' },
],
```

⚠️ **Une première version portait par erreur la description des poules pondeuses**
(« Créez votre élevage de poules pondeuses sans faux pas… »). Corrigée le 2026-08-06. La
valeur ci-dessus est la bonne — vérifier qu'aucune copie de l'ancienne ne subsiste ailleurs.

---

## Reste à fournir pour 1001 et 1002

Le fil d'ariane conditionne `product.category1` / `category5` dans GA4
(cf. `GtmFooterScripts.buildUserCategoryScript`) : le **dernier item avant le titre de page**
devient `category5`. Il faut donc, pour chaque page, les deux niveaux de rubrique — et de
préférence les libellés EXACTS du méga-menu, sinon les pages HUB formeront une catégorie à
part au lieu de s'agréger avec le reste du périmètre.

À fournir également : les 4 blocs thématiques, les articles conseils à lier, les visuels, le
questionnaire (4 questions) et le contenu éditorial SEO.
