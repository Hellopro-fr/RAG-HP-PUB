# Plan de tracking — pages HUB « projet »

> Périmètre : `conseils.hellopro.fr/<slug>-<id>-projet.html` (template `components/hub/`).
> Version consolidée du **2026-08-05**. Remplace les versions précédentes.
> Fichiers compagnons : `tracking-hub-events.csv` (événements), `tracking-hub-gtm.csv`
> (paramétrage conteneur), `tracking-hub-recette.csv` (30 tests).
> Statut : **arbitré, prêt à implémenter.** Rien n'est encore codé.

---

## 1. Constat de départ (mesuré en recette, pas supposé)

Recette du 2026-08-04 sur `/lancer-elevage-poules-pondeuses-1000-projet.html` : questionnaire
déroulé de bout en bout, dialog guide ouvert et soumis, pop-up déclenchée au scroll.

**Ce qui fonctionne déjà** — poussé par `GtmFooterScripts` (transverse conseils) :

| Donnée | Valeur observée |
|---|---|
| `page_template` | `page_hub` (arbitré ; valait `hub` avant le 2026-08-05) |
| `product.category1` / `category5` | `Agriculture` / `Élevage-avicole` (dérivés du fil d'ariane) |
| `user.visitorLoginState` | `unlogged` |
| Conteneur GTM | `GTM-PBBSTMC` chargé |
| Consent Mode | fonctionnel — refus ⇒ les 4 signaux passent en `denied` |

**Ce qui manque :**

> Sur l'intégralité du parcours, **le code HUB n'a poussé aucun événement dans le dataLayer.**
> Les seuls événements captés — `gtm.click`, `gtm.linkClick`, `gtm.scrollDepth` — viennent des
> déclencheurs automatiques du conteneur. Aucun fichier de `components/hub/` n'importe quoi que
> ce soit de `lib/analytics/`.

Conséquence : **« le workflow HUB est-il rentable ? » est aujourd'hui sans réponse mesurable.**

---

## 2. Décision fondatrice : un vocabulaire dédié `hub_*`

**Les événements HUB ne réutilisent pas `quote_form_funnel`.**

Réutiliser ce nom aurait donné des leads HUB comptabilisés sans configuration : les tags
`demarrages_de_devis_all_forms` et `quote_funnel_validation` y sont déjà branchés. C'est
précisément pourquoi il faut s'en abstenir.

1. **Un lead HUB n'est pas un devis groupé.** Le questionnaire qualifie une intention, il ne
   met pas en relation avec des fournisseurs.
2. **Ça casserait une mesure existante.** L'analyse d'impact du template conseils compte ses
   leads sur `quote_funnel_validation`. Des leads HUB dedans la contamineraient sans que
   personne ne s'en aperçoive — les deux vivent sur le même sous-domaine.
3. `page_template = page_hub` isole les pages, mais **seulement si chaque rapport pense au
   filtre**. Un nom d'événement distinct rend l'oubli impossible.

⚠️ Cet argument porte sur le **nom de l'événement**, pas sur la propriété GA4 de destination.
La distinction a son importance — voir §7.

---

## 3. Le parcours réel — un aiguillage, pas une file d'attente

C'est le point que toute lecture naïve du code manque, et il conditionne la moitié des
événements. **Trois branches**, identiques dans les deux tunnels :

```
                                      ┌─ cookie hub_lead=1 présent ?
                                      │
              ┌── OUI ────────────────┴──► RACCOURCI : téléchargement direct du PDF
              │                            ni étape e-mail, ni appel API, PAS de lead
   clic CTA ──┤
              └── NON ──► étape e-mail ──► APPEL 1 ──► réponse serveur
                                                        ├─ contact CONNU ──► remerciement
                                                        │                    + PDF auto
                                                        │                    + bouton de repli
                                                        └─ contact INCONNU ─► coordonnées
                                                                              ──► APPEL 2
                                                                              ──► remerciement
```

Quatre conséquences non négociables sur le plan :

### 3.1 `user_known_status` vient de la réponse serveur, jamais du cookie

Le cookie n'est posé qu'après un enregistrement réussi **sur cette machine**. Un contact
déjà connu de Hellopro par un autre canal, ou revenu depuis un autre navigateur, serait
compté `Unknown` alors que le serveur le reconnaît et saute l'étape coordonnées. **Le cookie
sous-détecte ; seule la réponse de l'appel 1 fait foi.**

### 3.2 `hub_email_check` — la métrique la plus utile du lot

| Événement | Déclencheur | Paramètres |
|---|---|---|
| `hub_email_check` | réception de la réponse de l'APPEL 1 | `result` : `known` \| `unknown` |

Il donne la part de visiteurs déjà en base, et distingue donc **« le HUB apporte de nouveaux
contacts »** de **« le HUB fait re-remplir un formulaire à des gens déjà connus »**. Deux
résultats radicalement différents pour juger la rentabilité du workflow — et indiscernables
sans cet événement.

### 3.3 Le raccourci `hub_lead=1` ne produit pas de lead

**Implémenté** (`lib/hub/leadEmailCookie.ts`, API `isLeadKnown()` / `markLeadKnown()`).
Le cookie `hub_lead=1` signifie « ce navigateur a déjà soumis un lead ». Au clic sur un CTA
guide, `GuideDownloadDialog` va directement à l'écran de téléchargement : pas d'étape e-mail,
**pas d'appel API**, donc **aucun nouveau lead**.

Trois événements sont donc explicitement ABSENTS de ce parcours :

| Absent | Pourquoi |
|---|---|
| `hub_form_submission` | ce n'est pas une conversion, la personne l'était déjà |
| `hub_email_check` | aucun e-mail n'est soumis, le serveur n'est pas interrogé |
| `hub_form_view` | le dialog s'ouvre, mais **aucun formulaire n'est présenté** — compter cette vue écraserait le taux de conversion du tunnel guide |

Ce qui est émis : `hub_guide_shortcut`, puis `hub_guide_download` avec
`lead_path: 'deja_converti'`. Sans cette séparation, deux erreurs symétriques étaient
possibles — compter chaque re-téléchargement comme une conversion, ou n'émettre aucun
événement et perdre le signal d'usage du guide.

Note : le cookie stocke `1`, jamais l'adresse. Un cookie est renvoyé au serveur à chaque
requête du sous-domaine ; y mettre l'e-mail l'exposait sans nécessité.

### 3.4 Le taux d'abandon aux coordonnées a un dénominateur particulier

`hub_form_coordinates_submit` n'est émis que sur la branche **INCONNU**. Son dénominateur est
donc `hub_email_check` avec `result=unknown`, **pas** `hub_form_email_submit`. Rapporté au
total, le taux serait mécaniquement sous-estimé.

### 3.5 Pas d'événement « vue » quand un autre le porte déjà

Règle de non-redondance, appliquée après relecture du 2026-08-05. Un écran affiché par la
**même branche de code, dans le même tick** qu'un événement déjà émis ne mérite pas son propre
événement : ce serait deux noms pour un seul instant, et donc deux valeurs qui finiront par
diverger.

| Événement candidat | Verdict | Preuve |
|---|---|---|
| `hub_form_coordinates_view` | **supprimé des deux tunnels** | `useGuideLead.ts:109-112` et `AssistantForm.tsx:174-178` affichent l'étape dans la branche `200 / coordonnees_requises`, celle-là même qui déclenche `hub_email_check`. `result=unknown` **est** le signal « étape coordonnées affichée ». |
| `hub_form_email_view` — tunnel **guide** | **absent à raison** | Le dialog s'ouvre directement sur l'écran e-mail : `hub_form_view` et lui seraient simultanés. |
| `hub_form_email_view` — tunnel **projet** | **conservé** | Il suit la 4ᵉ question et constitue un écran distinct : entre `hub_form_step` de la dernière question et lui, un abandon est possible. ⚠️ La justification initiale — « il peut être sauté par `skipEmailStep` » — **ne vaut plus** : ce raccourci a été retiré du questionnaire, l'étape e-mail y est désormais TOUJOURS affichée. |

L'asymétrie entre les deux tunnels est voulue, mais elle n'était pas écrite — ce qui la rendait
indiscernable d'un oubli. C'est corrigé ici.

### 3.6 Deux événements manquaient réellement au tunnel guide

`hub_form_error` et `hub_form_abandon` n'y figuraient pas, et rien ne le justifiait :
`useGuideLead.ts:114` et `:118` ont exactement les mêmes branches d'erreur que le tunnel
projet, et on peut fermer le dialog guide ou la pop-up sans convertir.

L'abandon à l'étape coordonnées du guide est même **plus** intéressant que côté projet : on y
demande téléphone et code postal pour un simple PDF. C'est l'endroit du parcours où le rapport
entre ce qu'on exige et ce qu'on offre est le plus défavorable.

### 3.5 Le PDF est délivré dans les deux tunnels

Vérifié en recette : l'écran de remerciement du questionnaire **projet** propose lui aussi le
guide. `hub_guide_download` n'est donc pas réservé au tunnel guide — c'est `hub_group` qui dit
d'où vient le téléchargement.

---

### 3.7 Nommage de l'événement de conversion

`hub_form_submission` — renommé le 2026-08-05 (valait `hub_lead`).

⚠️ **Point de vigilance à la construction des entonnoirs GA4.** Huit événements commencent
désormais par `hub_form_` et un seul est la conversion. Dans la liste alphabétique de GA4,
`hub_form_submission` voisine avec `hub_form_email_submit` et
`hub_form_coordinates_submit`, qui sont des étapes intermédiaires. Vérifier deux fois la
dernière étape d'un entonnoir : se tromper ne produit aucune erreur, seulement un taux de
conversion faux — et plus élevé que la réalité, donc peu susceptible d'être remis en question.

---

### 3.7bis Le visiteur déjà converti n'émet QUE `hub_guide_download`

Scénario constaté en recette : questionnaire projet complété (donc cookie posé),
puis clic sur un CTA guide. Trois événements partaient — `hub_guide_download`,
`hub_email_check`, `hub_form_submission` — pour ce qui n'est qu'un
re-téléchargement par quelqu'un de déjà converti.

**Résolu à la source** depuis que le raccourci n'appelle plus l'API (§3.3) :
`send()` n'est plus invoqué du tout pour un visiteur déjà converti, donc aucun
événement de tunnel ne peut partir. L'option `alreadyConverted` qui neutralisait
ces événements côté tracking a été retirée avec le comportement qu'elle compensait.

Les seuls événements émis, `hub_guide_shortcut` et `hub_guide_download`
(`lead_path: 'deja_converti'`), gardent le re-téléchargement mesurable sans le
faire entrer dans l'entonnoir.

### 3.7ter Tous les paramètres sont poussés à chaque événement

**GTM fusionne les pushes dans un modèle de données unique : une clé absente
conserve la valeur du push précédent.** Constaté en recette — un
`hub_form_submission` du tunnel guide portait encore `step_name: "delai"`,
`answer_label` et `steps_answered: 4` du questionnaire projet rempli juste avant.

`pushHubEvent` pousse donc **toutes** les clés de `HubEventParams`, celles que
l'événement ne renseigne pas valant `undefined` — ce qui écrase la précédente. Le
tag GA4 n'envoie pas les paramètres `undefined` : la dimension est nettoyée sans
être transmise vide.

⚠️ Une clé ajoutée à `HubEventParams` doit l'être aussi dans `HUB_PARAM_KEYS`,
sinon elle ne sera jamais nettoyée. Le type `satisfies Record<keyof HubEventParams, 0>`
en fait une erreur de compilation.

### 3.8 `step_name` est GÉNÉRIQUE, `step_id` porte le métier

`step_name` vaut `1ere-question`, `2eme-question`, `3eme-question`… puis `email` et
`coordinates`. **Jamais l'id métier de la question.**

Raison : les trois pages HUB n'ont pas les mêmes questions. Avec `budget` ou
`volume`, un entonnoir GA4 ne peut pas superposer les verticales — chaque page
aurait ses propres noms d'étapes, donc trois rapports au lieu d'un, et aucune
comparaison possible entre l'élevage, le food-truck et la laverie. La **position**,
elle, est comparable.

Cette convention est aussi celle du funnel devis legacy (`pushQuoteFormFunnel`
émet déjà `1ere-question`) : un seul vocabulaire dans le conteneur.

L'information métier n'est pas perdue — elle part dans **`step_id`**
(`budget`, `volume`, `delai`…). Les deux dimensions répondent à deux questions
différentes : `step_name` à « à quelle position décroche-t-on, toutes pages
confondues », `step_id` à « quelle question tue le tunnel sur CETTE page ».

`last_step_name` de `hub_form_abandon` suit le même vocabulaire, sans quoi
abandons et affichages ne se croiseraient pas dans un même rapport.

---

## 4. Les trois groupes

| Groupe | Nature | Ce qu'il répond |
|---|---|---|
| **Projet** | tunnel — questionnaire du hero, 6 écrans, lead qualifié, `id_page_hub = 1000` | Combien de projets qualifiés, et à quelle étape on décroche |
| **Guide** | tunnel — un e-mail contre un PDF, 4 portes d'entrée, `id_page_hub = 2000` | Combien de guides, et depuis quel emplacement |
| **Engagement** | **pas un tunnel** — aucun point d'arrivée | Pourquoi les deux premiers convertissent ou non |

`hub_group` (`projet` \| `guide` \| `engagement`) est ajouté par le helper sur **tous** les
événements. `hub_lead_type`, présent dans une version antérieure, est supprimé : il portait la
même information sur les seuls événements où il s'appliquait, et deux paramètres synonymes
finissent toujours par diverger — l'un mis à jour, l'autre oublié, la divergence indétectable
en aval.

**Périmètre Engagement réduit à `hub_article_click`.** Les 20 liens sortants de la page 1000
pointent vers `conseils.hellopro.fr` et sont aujourd'hui invisibles. Si le HUB ne convertit pas
lui-même mais alimente des pages conseils qui, elles, convertissent, c'est le seul événement
capable de le montrer — et donc de justifier le workflow autrement que par ses propres leads.
`hub_nav_click`, `hub_section_view` et `hub_carousel_scroll` sont écartés : ils décrivent du
confort d'analyse, à rouvrir seulement s'il faut expliquer un taux décevant.

Liste complète des 20 événements : `tracking-hub-events.csv`.

---

## 5. Architecture d'implémentation

### 5.1 Un helper unique, aucun `dataLayer.push` dans les composants

Créer `lib/analytics/hub.ts`, miroir de `lib/analytics/gtm.ts` :

```ts
export function pushHubEvent(event: HubEventName, params?: HubEventParams): void
```

Les composants appellent ce helper, jamais `window.dataLayer.push` en direct : les paramètres
communs sont ajoutés en un seul endroit, et un `grep pushHubEvent` donne l'inventaire exhaustif
des points de mesure. C'est la règle qui a fait tenir `lib/analytics/gtm.ts` sur les pages
conseils.

⚠️ **Ne jamais appeler `gtag()` depuis un composant.** Le contrat est le dataLayer ; GTM route.
Un `gtag` direct contourne le Consent Mode du conteneur.

### 5.2 Paramètres communs — ajoutés automatiquement

| Paramètre | Source | Exemple |
|---|---|---|
| `hub_group` | `projet` \| `guide` \| `engagement` | `projet` |
| `hub_page_id` | `page.id` | `1000` |
| `hub_page_uri` | `hubCanonicalPath(page)` — URI **publique**, pas la route interne | `/lancer-elevage-poules-pondeuses-1000-projet.html` |
| `id_page_hub` | id effectif de l'appel API | `1000` / `2000` |
| `session_id` | `getHpSessionId()` — **helper existant réutilisé** | `session_1785854120765_a1b2c3d4e` |
| `product.category5` | lu du dataLayer, comme `getCategory5()` | `Élevage-avicole` |

`page_template`, le bloc `user` et `product.category1..5` sont **déjà poussés** : ne pas les
redéclarer, GTM les lit comme variables de page.

Réutiliser `getHpSessionId()` (fenêtre d'inactivité glissante de 30 min, `sessionStorage`
partagé avec le formulaire legacy) permet de recoller un visiteur qui remplit le questionnaire
projet **puis** télécharge le guide : deux leads, une session.

### 5.3 Le signal de conversion n'est pas le code HTTP

Observation de recette : l'appel 2 a renvoyé **HTTP 200** avec `statut: "enregistre"`, alors que
la spec annonce 201. Le code gère déjà les deux (`res.status === 201 || corps?.statut ===
'enregistre'`, `AssistantForm.tsx:168`).

**Le push `hub_form_submission` doit vivre dans cette branche exacte**, à côté du `setSubmitted(true)`, et
non être conditionné sur `res.status === 201` — sinon la conversion est perdue sur
l'environnement observé.

---

## 6. Ce qui ne doit jamais partir dans le dataLayer

**Aucune donnée personnelle, sous aucune forme, pas même hachée** : ni e-mail, ni téléphone, ni
nom, ni prénom, ni code postal, ni civilité.

Les libellés de réponses (`answer_label`) sont des **choix fermés** définis dans le fichier de
données, pas de la saisie libre : ils peuvent partir.

**Biais assumé** : sous consentement refusé, les pushes ont lieu mais GA4 ne transmet pas. Les
chiffres du POC sous-estiment le volume réel du taux de refus. À mesurer plutôt qu'à ignorer —
sans cette correction, un POC jugé « non rentable » peut ne l'être qu'en apparence.

---

## 7. GA4 — `G-DQTV4SHNME`, et les deux propriétés

### 7.1 Destination et page_view

Les événements `hub_*` partent sur **`G-DQTV4SHNME`**. Confirmé le 2026-08-05 : son tag de
configuration se déclenche bien sur `conseils.hellopro.fr` et pas seulement sur `www`.

`G-J3925VE86T` est **conservée**. Il faut seulement s'assurer que le `page_view` parte **aussi**
vers `G-DQTV4SHNME`.

⚠️ **Le point de vigilance principal du lot.** Ce réglage vit dans le tag de configuration, qui
s'applique à **tout `conseils.hellopro.fr`** — pas seulement aux pages HUB. Deux tests avant
mise en ligne, sur les deux types de page :

- DebugView `G-DQTV4SHNME` sur une page **HUB** : exactement **un** `page_view`.
- DebugView `G-DQTV4SHNME` sur une page **conseils** : exactement **un** `page_view`, et
  `page_template = conseils`.

Ni zéro (réglage manquant) ni deux (page_view émis par deux tags à la fois). Le `gtag('config',
'G-J3925VE86T')` de `GtmFooterScripts` lignes 62-64 n'alimente que sa propre propriété : il ne
crée pas de doublon sur `G-DQTV4SHNME`, mais il faut vérifier qu'aucun tag GTM ne fait déjà le
travail avant d'en ajouter un.

### 7.2 Les key events s'agrègent au niveau de la propriété

Marquer `hub_form_submission` comme key event l'ajoute au total « conversions » de `G-DQTV4SHNME`. Tout
rapport ou tableau de bord qui lit ce total sans détailler par nom d'événement comptera les
leads HUB. **C'est le seul vrai vecteur de contamination des rapports existants, et il ne
dépend pas du nom de l'événement.** Deux options : ne pas le marquer pendant le POC — les
rapports standard suffisent à compter un événement nommé — ou le marquer et prévenir les
lecteurs de ce total.

### 7.3 À vérifier avant de créer quoi que ce soit

- **Quota de dimensions** : 50 event-scoped par propriété, ce plan en demande 10.
- **`page_template` enregistrée** dans `G-DQTV4SHNME` — sans elle, impossible de segmenter.
- **Durée de conservation** (défaut 2 mois pour les explorations) : un POC jugé à 3 mois avec
  2 mois de conservation perd sa première cohorte.

### 7.4 Nommage de `product.category5`

Le legacy pousse la clé plate `'product.category5'`. Un nom de paramètre GA4 n'accepte que
lettres, chiffres et underscores : le point est invalide. La variable GTM lit
`product.category5` et le tag l'envoie sous le nom **`product_category5`**.

### 7.5 Conteneur GTM — le paramétrage est léger

Un déclencheur *Custom Event* en regex `^hub_`, **un seul** tag GA4 Event avec `{{Event}}`
comme nom d'événement, et les variables dataLayer. Vingt tags auraient le même comportement.
Détail complet : `tracking-hub-gtm.csv`.

---

## 8. Pop-up de capture : la session de l'app n'est pas la session GA4

La pop-up s'affiche **une fois par onglet** (`sessionStorage`), et réapparaît donc dans un
nouvel onglet ou un autre navigateur. GA4, lui, compte une session **à travers les onglets**
(30 min d'inactivité).

Conséquence de mesure : un visiteur qui ouvre trois onglets génère **trois**
`hub_guide_popup_view` dans **une seule** session GA4.

**Ne pas calculer le taux de conversion de la pop-up en `hub_lead / hub_guide_popup_view`** —
le dénominateur est gonflé. Utiliser « sessions avec l'événement » ou « utilisateurs », pas le
nombre d'événements. Les tests 22 et 23 de la recette documentent les deux comportements.

---

## 9. `page_template = "page_hub"` est un contrat

Valeur arbitrée le 2026-08-05, appliquée dans `HubTemplate.tsx` et verrouillée par
`__tests__/components/hub/HubTemplate.test.tsx`.

Des filtres et segments GA4 seront construits dessus. **La changer met les rapports à zéro sans
lever la moindre erreur** — pas d'exception, pas de log, juste des courbes plates. D'où
l'assertion sur la chaîne littérale dans le test, et non sur une constante importée du
composant qui suivrait le changement en silence.

À noter : les pages conseils émettent `conseils` et les pages HUB `page_hub`. La symétrie
serait `conseils`/`hub` ou `page_conseils`/`page_hub`. Valeur retenue telle que demandée ; si
l'homogénéité compte pour les rapports à venir, c'est maintenant qu'il faut trancher — après la
première collecte, changer coûte une reprise de tous les segments.

---

## 10. Ordre d'implémentation

| Lot | Contenu | Ce qu'on sait à la fin |
|---|---|---|
| 1 | `lib/analytics/hub.ts` + tests unitaires | rien — mais le socle est testable sans navigateur |
| 2 | Tunnel projet (§3, events 1-11) | combien de projets, où ça décroche |
| 3 | `hub_email_check` + `hub_form_submission` + `hub_form_abandon` sur les deux tunnels | part de contacts déjà connus, étape qui tue le tunnel |
| 4 | Tunnel guide avec `entry_point` et `hub_guide_shortcut` | quelle porte convertit, usage réel du guide |
| 5 | `hub_article_click` | si le HUB alimente les pages conseils |
| 6 | Conteneur GTM + GA4 + recette 30 tests | les chiffres sont fiables |

Les lots 1 à 3 suffisent à répondre à « combien de leads, et où ça décroche ». Le reste
répond à « pourquoi », et ne se justifie qu'une fois du volume observé.

---

## 11. Reporté, hors périmètre tracking

- **Barre sticky mobile** : icône de téléchargement pour un bouton qui ouvre le questionnaire.
  Revu plus tard ; `entry_point = sticky_mobile` reste prévu dans le plan.
- **PDF du guide** : `/seo_masterclass_detailed.pdf` (résidu du prototype Lovable) sera
  remplacé quand l'équipe aura terminé le livre. Aucun impact sur le plan.
