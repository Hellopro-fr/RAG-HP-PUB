# Documentation des Événements GTM

Ce document décrit tous les événements GTM (Google Tag Manager) utilisés dans l'application de demande de devis.

---

## Architecture des Événements

L'architecture repose sur **un événement principal** (`devis_funnel_formulaire`) qui track toutes les étapes du funnel, et **des événements secondaires** pour des actions spécifiques hors funnel.

---

## Événement Principal : `devis_funnel_formulaire`

Cet événement unique track toute la progression de l'utilisateur dans le funnel de demande de devis.

### Structure de base

```javascript
{
  event: 'devis_funnel_formulaire',

  // Progression
  step_index: number,        // Index de l'étape (0, 1, 2...)
  step_name: string,         // Nom de l'étape
  step_number: number,       // Numéro de l'étape (step_index + 1)
  step_type: string,         // Type d'étape

  // Contexte funnel
  funnel_devisplus: boolean, // true si funnel devis+
  funnel_context: string,    // 'direct', 'dynamic', 'static'
  rubrique_id: number,       // ID de la rubrique
  rubrique_name: string,     // Nom de la rubrique
  page_location_uri: string, // URL de la page
  abtest1: string,           // Variante A/B test

  // Type de parcours (voir section "Parcours utilisateur")
  flow_type: string | null,  // 'principal' | 'pas_assez_produits' | 'pas_trouve_recherchez' | null

  // Identifiants
  user_id: string,           // ID utilisateur (persistant localStorage)
  session_id: string,        // ID session (sessionStorage)

  // + données additionnelles selon l'étape
}
```

### Types d'étapes (step_type)

| step_type | Description |
|-----------|-------------|
| `init` | Initialisation du funnel |
| `question` | Étape de question du questionnaire |
| `choix-propart` | Choix professionnel/particulier |
| `selection` | Sélection des fournisseurs |
| `contact` | Formulaire de contact |
| `conversion` | Soumission finale |

### Types de parcours (flow_type)

Le champ `flow_type` permet d'identifier le parcours emprunté par l'utilisateur. Il est `null` pour les premières étapes (avant le branchement) puis défini une fois le parcours déterminé.

| flow_type | Déclencheur | Description |
|-----------|-------------|-------------|
| `principal` | Arrivée sur `/selection` | Parcours standard avec sélection de produits |
| `pas_assez_produits` | Redirection automatique vers `/something-to-add` | Pas assez de produits correspondants, l'utilisateur décrit son besoin |
| `pas_trouve_recherchez` | Clic "Pas trouvé ce que vous cherchez ?" sur `/selection` | L'utilisateur a vu les produits mais n'a pas trouvé son besoin |
| `null` | Avant le branchement | Parcours pas encore déterminé (questionnaire, profil) |

#### Schéma des parcours

```
                    questionnaire-start (flow_type: null)
                              │
                              ▼
                      choix-propart (flow_type: null)
                              │
               ┌──────────────┴──────────────┐
               ▼                              ▼
      assez de produits              pas assez de produits
               │                              │
               ▼                              ▼
    selection-produits              description-besoin
   (flow_type: 'principal')    (flow_type: 'pas_assez_produits')
               │                              │
    ┌──────────┴──────────┐                   ▼
    ▼                     ▼         formulaire-contact-simple
 continue         clique "pas trouvé"         │
    │                     │                   ▼
    ▼                     ▼             submit-success
formulaire-contact   description-besoin
    │            (flow_type: 'pas_trouve_recherchez')
    ▼                     │
submit-success            ▼
                 formulaire-contact-simple
                          │
                          ▼
                    submit-success
```

### Étapes détaillées (step_name)

#### Initialisation
| step_name | step_type | Description |
|-----------|-----------|-------------|
| `funnel-start` | `init` | Début du funnel |

#### Questionnaire
| step_name | step_type | Description |
|-----------|-----------|-------------|
| `1ere-question` | `question` | Affichage première question |
| `2eme-question` | `question` | Affichage deuxième question |
| `Neme-question` | `question` | Affichage N-ème question |
| `questionnaire-complete` | `question` | Fin du questionnaire |

**Données additionnelles pour les questions :**
```javascript
{
  question_id: number,       // ID de la question
  question_title: string,    // Titre de la question
  total_questions: number,   // Nombre total de questions (pour questionnaire-complete)
  time_spent_seconds: number // Temps passé (pour questionnaire-complete)
}
```

#### Choix Pro/Part
| step_name | step_type | Description |
|-----------|-----------|-------------|
| `choix-propart` | `choix-propart` | Affichage page profil |
| `choix-propart-selected` | `choix-propart` | Sélection du type de profil |
| `profile-complete` | `choix-propart` | Profil complété |

**Données additionnelles :**
```javascript
{
  profile_type: string,      // 'professional' | 'individual'
  has_company: boolean,      // A une entreprise
  country_id: number,        // ID du pays
  location: string           // Localisation
}
```

#### Sélection produits
| step_name | step_type | Description |
|-----------|-----------|-------------|
| `selection-produits` | `selection` | Affichage page sélection |
| `product-click` | `selection` | Clic sur carte produit |
| `product-selection` | `selection` | Changement sélection |
| `comparison-modal` | `selection` | Ouverture modal comparaison |

**Données additionnelles :**
```javascript
{
  recommended_count: number,  // Nombre de produits recommandés
  total_count: number,        // Nombre total de produits
  product_id: string,         // ID produit
  product_name: string,       // Nom produit
  match_score: number,        // Score de correspondance
  action: string,             // 'view_details' | 'toggle_select' | 'ajouter' | 'retirer'
  total_selected: number,     // Nombre de produits sélectionnés
  is_first_add: boolean,      // true uniquement lors du premier ajout de la session
  is_first_remove: boolean,   // true uniquement lors du premier retrait de la session
  products_compared: string[], // IDs des produits comparés
  products_count: number      // Nombre de produits comparés
}
```

#### Formulaire de contact (parcours principal)
| step_name | step_type | Description |
|-----------|-----------|-------------|
| `formulaire-contact` | `contact` | Affichage formulaire (parcours principal) |
| `champ-coordonnees-N` | `contact` | Remplissage champ N |
| `validation-error` | `contact` | Erreur de validation |

#### Parcours alternatif (description du besoin)
| step_name | step_type | flow_type | Description |
|-----------|-----------|-----------|-------------|
| `description-besoin` | `contact` | `pas_assez_produits` ou `pas_trouve_recherchez` | Page "Votre besoin" - description libre |
| `formulaire-contact-simple` | `contact` | `pas_assez_produits` ou `pas_trouve_recherchez` | Formulaire de coordonnées simplifié |

**Données additionnelles pour `description-besoin` :**
```javascript
{
  is_first_view: boolean    // Première vue de la session
}
```

**Données additionnelles :**
```javascript
{
  selected_count: number,     // Nombre de fournisseurs sélectionnés
  field_name: string,         // Nom du champ
  field_index: number,        // Index du champ
  is_valid: boolean,          // Formulaire valide
  missing_fields: string[],   // Champs manquants
  errors_count: number,       // Nombre d'erreurs
  errors: Array<{             // Détail des erreurs
    field: string,
    type: string,
    message: string
  }>
}
```

#### Conversion
| step_name | step_type | Description |
|-----------|-----------|-------------|
| `submit-success` | `conversion` | Soumission réussie |
| `submit-error` | `conversion` | Erreur de soumission |

**Données additionnelles :**
```javascript
{
  lead_id: string,            // ID du lead créé
  suppliers_count: number,    // Nombre de fournisseurs
  profile_type: string,       // Type de profil
  conversion: boolean,        // true si succès
  error_type: string,         // Type d'erreur (si erreur)
  error_message: string       // Message d'erreur (si erreur)
}
```

---

## Événements Secondaires

Ces événements trackent des actions spécifiques hors du funnel principal.

### `recherche_entreprise`

Recherche d'entreprise (SIREN/SIRET).

```javascript
{
  event: 'recherche_entreprise',
  query_length: number,       // Longueur de la recherche
  results_count: number       // Nombre de résultats
}
```

### `page_vue_critere`

Ouverture du modal de modification des critères.

```javascript
{
  event: 'page_vue_critere',
  user_id: string,
  session_id: string,
  is_first_view: boolean,     // Première vue de la session
  timestamp: string           // ISO 8601
}
```

### `critere_modifie`

Modification effective des critères.

```javascript
{
  event: 'critere_modifie',
  user_id: string,
  criteria_count: number,     // Nombre de critères
  modified_fields: string[],  // Champs modifiés
  timestamp: string
}
```

### `vue_page_votre_besoin` *(DEPRECATED)*

> **⚠️ DEPRECATED** : Cet événement est remplacé par `devis_funnel_formulaire` avec `step_name: 'description-besoin'`.

Arrivée sur la page `/something-to-add` - Étape 1: "Votre besoin" (affichée quand il y a peu de produits correspondant à la recherche).

### `vue_page_vos_coordonnees` *(DEPRECATED)*

> **⚠️ DEPRECATED** : Cet événement est remplacé par `devis_funnel_formulaire` avec `step_name: 'formulaire-contact-simple'`.

Passage à l'étape 2: "Vos coordonnées" sur la page `/something-to-add`.

### `vue_modal_produit`

Ouverture du modal fiche produit.

```javascript
{
  event: 'vue_modal_produit',
  user_id: string,
  session_id: string,
  is_first_view: boolean,
  product_id: string,         // ID du produit
  product_name: string,       // Nom du produit
  supplier_id: string,        // ID du fournisseur
  timestamp: string
}
```

### `utilisateur_identifie`

Identification de l'utilisateur avec ses informations.

```javascript
{
  event: 'utilisateur_identifie',
  user_id: string,
  session_id: string,
  email: string,              // Email de l'utilisateur
  profile_type: string,       // Type de profil
  company_name: string,       // Nom de l'entreprise
  timestamp: string
}
```

### `abandon_funnel`

Abandon du funnel à une étape.

```javascript
{
  event: 'abandon_funnel',
  user_id: string,
  session_id: string,
  step: string,               // Nom de l'étape abandonnée
  step_number: number,        // Numéro de l'étape
  time_spent_seconds: number, // Temps passé avant abandon
  last_action: string,        // Dernière action
  device_type: string,        // 'mobile' | 'tablet' | 'desktop'
  screen_width: number,
  screen_height: number,
  user_agent: string,
  timestamp: string
}
```

### `device_info`

Informations sur l'appareil (début de session).

```javascript
{
  event: 'device_info',
  user_id: string,
  session_id: string,
  device_type: string,        // 'mobile' | 'tablet' | 'desktop'
  screen_width: number,
  screen_height: number,
  user_agent: string,
  timestamp: string
}
```

### `source_trafic`

Sources de trafic (paramètres UTM).

```javascript
{
  event: 'source_trafic',
  user_id: string,
  session_id: string,
  utm_source: string,         // Source UTM ou 'direct'
  utm_medium: string,         // Medium UTM ou 'none'
  utm_campaign: string,       // Campagne UTM ou 'none'
  utm_term: string,           // Terme UTM
  utm_content: string,        // Contenu UTM
  referrer: string,           // Document referrer ou 'direct'
  landing_page: string,       // URL de la landing page
  timestamp: string
}
```

---

## Identifiants Utilisateur

### user_id

- **Stockage** : `localStorage` (clé: `hp_user_id`)
- **Format** : `user_{timestamp}_{random}`
- **Persistance** : Permanent (survit aux sessions)

### session_id

- **Stockage** : `sessionStorage` (clé: `hp_session_id`)
- **Format** : `session_{timestamp}_{random}`
- **Persistance** : Durant la session (effacé à la fermeture)

---

## Fonctions Disponibles

### Funnel principal

| Fonction | Description |
|----------|-------------|
| `trackFunnelStart()` | Démarre le funnel |
| `trackQuestionView(index, data)` | Affichage d'une question |
| `trackQuestionAnswered(index, id, title, answers, isMulti)` | Réponse à une question |
| `trackQuestionnaireComplete(total, time)` | Fin questionnaire |
| `trackProfileView()` | Affichage page profil |
| `trackProfileTypeSelected(type)` | Sélection type profil |
| `trackProfileComplete(type, hasCompany, countryId, location)` | Profil complété |
| `trackSelectionPageView(recommended, total)` | Page sélection |
| `trackProductCardClick(id, name, score, action)` | Clic produit |
| `trackProductSelectionChange(id, action, total)` | Sélection changée |
| `trackComparisonModalView(ids)` | Modal comparaison |
| `trackContactFormView(count)` | Formulaire contact |
| `trackContactFieldFilled(name, index)` | Champ rempli |
| `trackFormSubmitAttempt(valid, missing)` | Tentative soumission |
| `trackFormValidationErrors(count, errors)` | Erreurs validation |
| `trackLeadSubmitted(id, count, type)` | Lead soumis |
| `trackLeadSubmissionError(type, message)` | Erreur soumission |

### Gestion du parcours (flow_type)

| Fonction | Description |
|----------|-------------|
| `setFlowType(flowType)` | Définir le type de parcours ('principal', 'pas_assez_produits', 'pas_trouve_recherchez') |
| `getFlowType()` | Récupérer le type de parcours actuel |

### Parcours alternatif (description du besoin)

| Fonction | Description |
|----------|-------------|
| `trackCustomNeedPageView()` | Page "Description besoin" → `devis_funnel_formulaire` { step_name: 'description-besoin' } |
| `trackCustomNeedContactView()` | Formulaire coordonnées simplifié → `devis_funnel_formulaire` { step_name: 'formulaire-contact-simple' } |

### Événements secondaires

| Fonction | Description |
|----------|-------------|
| `trackCompanySearch(query, results)` | Recherche entreprise |
| `trackModifyCriteriaModalView()` | Modal critères |
| `trackCriteriaModified(count, fields)` | Critères modifiés |
| `trackProductModalView(productId, productName, supplierId)` | Modal produit |
| `trackFunnelAbandonment(step, number, time, action)` | Abandon funnel |
| `trackDeviceInfo()` | Info appareil |
| `trackTrafficSource()` | Source trafic |

---

## Configuration GTM

### Triggers recommandés

1. **Trigger Funnel** : Event equals `devis_funnel_formulaire`
2. **Trigger Conversion** : Event equals `devis_funnel_formulaire` AND `conversion` equals `true`
3. **Trigger Abandon** : Event equals `abandon_funnel`

### Variables recommandées

- `step_name` - Data Layer Variable
- `step_type` - Data Layer Variable
- `step_index` - Data Layer Variable
- `flow_type` - Data Layer Variable
- `conversion` - Data Layer Variable
- `user_id` - Data Layer Variable
- `profile_type` - Data Layer Variable

---

## Exemple de flux complet

```
1. trackFunnelStart()
   → devis_funnel_formulaire { step_name: 'funnel-start', step_type: 'init' }

2. trackQuestionView(0)
   → devis_funnel_formulaire { step_name: '1ere-question', step_type: 'question' }

3. trackQuestionView(1)
   → devis_funnel_formulaire { step_name: '2eme-question', step_type: 'question' }

4. trackQuestionnaireComplete(3, 45)
   → devis_funnel_formulaire { step_name: 'questionnaire-complete', step_type: 'question' }

5. trackProfileView()
   → devis_funnel_formulaire { step_name: 'choix-propart', step_type: 'choix-propart' }

6. trackProfileComplete('professional', true, 1, 'Paris')
   → devis_funnel_formulaire { step_name: 'profile-complete', step_type: 'choix-propart' }

7. trackSelectionPageView(5, 12)
   → devis_funnel_formulaire { step_name: 'selection-produits', step_type: 'selection' }

8. trackContactFormView(3)
   → devis_funnel_formulaire { step_name: 'formulaire-contact', step_type: 'contact' }

9. trackLeadSubmitted('lead_123', 3, 'professional')
   → devis_funnel_formulaire { step_name: 'submit-success', step_type: 'conversion', conversion: true }
```

---

## KPIs et Requêtes GTM/GA4

### Funnel Principal

| KPI | Événement | Filtre |
|-----|-----------|--------|
| Nb arrivée funnel | `devis_funnel_formulaire` | `step_name = 'funnel-start'` |
| Nb arrivée Q1 (Q2 ancienne UX) | `devis_funnel_formulaire` | `step_name = '1ere-question'` |
| Nb arrivée Pro/Part | `devis_funnel_formulaire` | `step_name = 'choix-propart'` |
| Nb arrivée sélection | `devis_funnel_formulaire` | `step_name = 'selection-produits'` |
| Nb arrivée form coordonnées | `devis_funnel_formulaire` | `step_name = 'formulaire-contact'` |
| Nb leads validés | `devis_funnel_formulaire` | `step_name = 'submit-success'` |

### Événements Secondaires (avec déduplication)

| KPI | Événement | Total | Dédupliqué (unique) |
|-----|-----------|-------|---------------------|
| Affichage modifier critères | `page_vue_critere` | COUNT(*) | COUNT(*) WHERE `is_first_view = true` |
| Affichage besoin différent | `vue_page_votre_besoin` | COUNT(*) | COUNT(*) WHERE `is_first_view = true` |
| Affichage tableau comparatif | `comparison-modal` | COUNT(*) | COUNT(*) WHERE `is_first_view = true` |
| Affichage popup produit | `vue_modal_produit` | COUNT(*) | COUNT(*) WHERE `is_first_view = true` |
| Clics ajouter sélection | `product-selection` | COUNT(*) WHERE `action = 'ajouter'` | COUNT(*) WHERE `is_first_add = true` |
| Clics retirer sélection | `product-selection` | COUNT(*) WHERE `action = 'retirer'` | COUNT(*) WHERE `is_first_remove = true` |
| Modification effective critères | `critere_modifie` | COUNT(*) | COUNT(DISTINCT user_id) |

### Analyse par type de parcours (flow_type)

| KPI | Événement | Filtre |
|-----|-----------|--------|
| Conversions parcours principal | `devis_funnel_formulaire` | `step_name = 'submit-success'` AND `flow_type = 'principal'` |
| Conversions parcours "pas assez produits" | `devis_funnel_formulaire` | `step_name = 'submit-success'` AND `flow_type = 'pas_assez_produits'` |
| Conversions parcours "pas trouvé" | `devis_funnel_formulaire` | `step_name = 'submit-success'` AND `flow_type = 'pas_trouve_recherchez'` |
| Nb redirections automatiques | `devis_funnel_formulaire` | `step_name = 'description-besoin'` AND `flow_type = 'pas_assez_produits'` |
| Nb clics "pas trouvé" | `devis_funnel_formulaire` | `step_name = 'description-besoin'` AND `flow_type = 'pas_trouve_recherchez'` |
