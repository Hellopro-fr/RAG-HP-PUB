# HUB — visuels et fichiers en attente de livraison

Suivi des emplacements du template HUB laissés **volontairement vides** faute
d'asset livré, et des assets livrés mais **à remplacer**.

> État au 2026-08-07 : les trois pages sont complètes côté visuels. Il ne reste
> que **le PDF du guide**, commun aux trois, et une seconde photo pour le bandeau
> de la pop-up de la 1002 (qui réutilise pour l'instant celle du héros).

Règle du modèle de données (`data/hub/*.ts`) : un emplacement sans visuel n'a
PAS de champ `image`, jamais de chemin inventé. Les composants dégradent
proprement (aplat de couleur, icône). Il n'y a donc **aucune image cassée en
production** tant que cette liste n'est pas soldée — seulement des blocs plus
sobres que la maquette.

Le contrôle est automatique dans les deux sens (`__tests__/data/hub/registry.test.ts`) :

- toute image déclarée dans les données doit exister sur le disque ;
- tout fichier présent dans `public/images/hub/<slug>/` doit être référencé.

Conséquence pratique : **déposer un fichier ne suffit pas**, il faut le brancher
dans les données dans le même mouvement, sinon le test échoue en « image
orpheline ». C'est voulu — c'est ce qui a permis de repérer 5 vignettes livrées
et jamais affichées.

---

## Page 1001 — `ouvrir-food-truck` ✅ soldée le 2026-08-07

26 emplacements sur 26 : héros, bandeau pop-up, couverture du guide (PNG
détouré), CTA accompagnement, accompagnement expert, 16 vignettes d'articles dans
`articles/` et les 5 tuiles « grandes étapes » dans `etapes/`.

Deux points réglés en cours de route, à connaître pour les livraisons suivantes :

- **`pop-up-food-truck.jpg` était une capture d'écran de la pop-up elle-même** —
  le bandeau affichait donc une photo du modal à l'intérieur du modal. Remplacé
  par une photo de camion. Cadrage utile pour ce bandeau : **672 × 208 px** sur
  desktop (`h-52`), recadré `center 25%` → le sujet doit être dans la moitié
  haute, et le tiers gauche est partiellement masqué par la couverture du guide.
- **Les 5 tuiles ont été livrées avec espaces, accents et `&`** dans les noms de
  fichiers (« Réglementation & démarches.jpg »). Renommées en kebab-case ASCII.
  À demander directement dans ce format aux prochaines livraisons.

⚠️ Les libellés des tuiles diffèrent entre les pages : 1001 dit **« Cadrage du
projet »**, 1000 dit « Dimensionnement du projet ». Les fichiers ne sont pas
interchangeables.

---

## Page 1000 — `lancer-elevage-poules-pondeuses`

Aucun visuel manquant. Ses 5 tuiles `etapes/` sont pourvues.

---

## Page 1002 — `ouvrir-laverie-automatique` ✅ soldée le 2026-08-07

26 emplacements sur 26.

### À remplacer

`hero-laverie.jpg` sert **deux fois** : fond du héros et bandeau de la pop-up. Le
fichier prévu pour la pop-up (« Pop up Ouvrir une laverie automatique.jpg »)
était une **capture d'écran de la maquette de pop-up** — le modal photographié à
l'intérieur du modal, exactement l'erreur détectée sur la page 1001. Il a été
sorti du dépôt. Une seconde photo de laverie permettrait de différencier les deux
emplacements ; en l'état le rendu est correct, juste répétitif.

### Deux pièges rencontrés sur cette livraison

- **Noms de fichiers** : les 27 visuels portaient leur H1 en nom, avec espaces,
  accents, `&`, parenthèses et apostrophes typographiques. Renommés en kebab-case
  ASCII (vignettes d'articles nommées par id de page conseil).
- **6 vignettes inutilisables livrées** : articles **5406, 5396, 5410, 5392, 5395
  et 5400**. Ce sont les cartes latérales des blocs `overlay-*`, qui n'ont aucun
  emplacement image. Sorties du dépôt. Même erreur que sur la 1001 — à signaler
  en amont la prochaine fois.

---

## Le PDF du guide

Les guides vivent dans `public/guides/`, **nommés par slug de page** et en
kebab-case ASCII. Le nom que le visiteur voit dans son dossier Téléchargements
est déclaré séparément, dans `fileName` — ce qui permet de garder un chemin
robuste et un titre éditorial (« Livre blanc - … »).

Chaque page a **deux** références à renseigner : `assistant.success` (fin du
questionnaire) et `guideDialog.download` (tunnel guide).

| Page | Fichier | État |
|---|---|---|
| 1000 élevage | `public/guides/lancer-elevage-poules-pondeuses.pdf` | ✅ livré |
| 1002 laverie | `public/guides/ouvrir-laverie-automatique.pdf` | ✅ livré |
| 1001 food truck | `public/guides/ouvrir-food-truck.pdf` | ⏳ **placeholder** |

⚠️ La page 1001 sert encore `/seo_masterclass_detailed.pdf`, un document sans
rapport avec la verticale. C'est le seul point de cette liste qui soit un
engagement vis-à-vis du visiteur — il laisse son adresse en échange de ce
fichier — et non une question d'esthétique. À solder avant mise en ligne.

Deux limites à connaître :

- **Le PDF est un asset statique public.** Son URL est devinable, et rien
  n'empêche de le télécharger sans laisser d'e-mail. Conditionner l'accès
  supposerait une route API vérifiant le cookie — chantier à arbitrer.
- **Il part dans l'image Docker** (`COPY --from=builder /app/public ./public`),
  `.dockerignore` ne l'exclut pas. Le guide élevage pèse 26 Mo à lui seul :
  surveiller la taille de l'image, et envisager un stockage externe si les trois
  guides restent à ce format.

---

## Vignettes sorties du dépôt (à ne pas re-livrer)

Les cartes **latérales** des layouts `overlay-*` n'ont aucun emplacement image :
seule l'icône y est rendue. Les visuels des articles **5420, 5421, 5423, 5424 et
5425** ont donc été déplacés hors de `public/` (pas supprimés). Les re-déposer
ferait échouer le test « image orpheline » sans rien afficher de plus.

---

## Pièges de copie depuis Windows

L'Explorateur ajoute un flux ADS `<fichier>Zone.Identifier` à côté des fichiers
téléchargés. `readdirSync` le voit, le test le compte comme image orpheline et
échoue. Purge :

```bash
cd apps-microservices/nextjs-conseils-hp
find public -name '*Zone.Identifier' -delete
```
