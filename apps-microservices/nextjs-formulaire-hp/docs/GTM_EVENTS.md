# Documentation des Événements GTM

> **Source de vérité unique** : `lib/analytics/gtm.ts`.
> Ce document est aligné sur l'état réel du code. Toute fonction citée ici est exportée par `gtm.ts` et appelée au moins une fois dans l'application (sauf mention `[non utilisé]` ou `@deprecated`).

---

## Sommaire

1. [Architecture](#architecture)
2. [Événement principal `devis_funnel_formulaire`](#événement-principal--devis_funnel_formulaire)
3. [Événements secondaires](#événements-secondaires)
4. [Fonctions utilitaires](#fonctions-utilitaires)
5. [Identifiants user / session](#identifiants-user--session)
6. [Inventaire complet des fonctions exportées](#inventaire-complet-des-fonctions-exportées)
7. [Dead code & fonctions dépréciées](#dead-code--fonctions-dépréciées)
8. [GA4 & Hotjar](#ga4--hotjar)
9. [Configuration GTM recommandée](#configuration-gtm-recommandée)
10. [KPIs](#kpis)
11. [Tracking DB parallèle](#tracking-db-parallèle)

---

## Architecture

Trois canaux d'analytics coexistent :

| Canal | Source | Vocation | Statut |
|---|---|---|---|
| **GTM (dataLayer)** | `lib/analytics/gtm.ts` | Funnel marketing, mesure d'audience, conversion. Push direct vers `window.dataLayer`. | **Actif** — utilisé partout dans le funnel |
| **GA4 (gtag)** | `lib/analytics/ga4.ts` | Events GA4 directs (hors GTM). | **Inutilisé** — défini mais aucun appel dans le code |
| **Hotjar** | `lib/analytics/hotjar.ts` | Tagging session recordings, identification, sondages. | **Inutilisé** — défini mais aucun appel dans le code |

En parallèle, une couche de tracking interne `useDbTracking` (`hooks/tracking/useDbTracking.ts`) pousse des events vers `/api/tck` (PHP-side analytics DB). Cette couche est documentée en [Tracking DB parallèle](#tracking-db-parallèle).

Le funnel GTM repose sur **un événement principal** (`devis_funnel_formulaire`) émis à chaque étape, et **quelques événements secondaires** pour des contextes hors funnel.

---

## Événement principal : `devis_funnel_formulaire`

Émis par `trackQuoteFunnel()` ([gtm.ts:183](../lib/analytics/gtm.ts#L183)), appelé par toutes les fonctions `track*()` du funnel.

### Structure de base

```javascript
{
  event: 'devis_funnel_formulaire',

  // Progression — incrémentée à chaque étape par currentStepIndex (gtm.ts:219)
  step_index: number,        // Index séquentiel (0, 1, 2…)
  step_name: string,         // Voir tableau ci-dessous
  step_number: number,       // step_index + 1
  step_type: string,         // 'init' | 'question' | 'localisation' | 'choix-propart' | 'prix' | 'selection' | 'contact' | 'conversion'

  // Contexte funnel — setFunnelContext(...)
  rubrique_id: number,
  'product.category5': string,
  abtest2?: string,           // optionnel — provient du token URL, omis si absent
  page_template_gtm?: string, // optionnel — template GTM de la page d'entrée, depuis le token URL
  funnel_context?: string,    // optionnel — contexte funnel, depuis le token URL
  page_location_uri?: string, // optionnel — URI de la page d'entrée, depuis le token URL

  // Type de parcours
  flow_type: string | null,  // voir section "Types de parcours"

  // Identifiants
  user_id: string,
  session_id: string,

  // + champs additionnels selon l'étape (cf. tableau ci-dessous)
}
```

### Types d'étapes (`step_type`)

| step_type | Description |
|---|---|
| `init` | Initialisation et écran assurance |
| `question` | Étape du questionnaire dynamique |
| `localisation` | Page `/geo-zone` |
| `choix-propart` | Choix profil professionnel / particulier |
| `prix` | Page `/budget` (estimation + tranche) |
| `selection` | Page `/selection` et interactions sur la modale fournisseur |
| `contact` | Formulaire de contact (parcours principal ou alternatif) |
| `conversion` | Soumission finale (succès ou erreur) |

### Types de parcours (`flow_type`)

Défini par `setFlowType()` ([gtm.ts:165](../lib/analytics/gtm.ts#L165)). Reste `null` tant que le branchement n'a pas eu lieu.

| flow_type | Déclencheur |
|---|---|
| `null` | Parcours non encore déterminé (init, questionnaire, profil, geo-zone, budget) |
| `principal` | Arrivée sur `/selection` ([selection-client.tsx:31](../app/(flow)/selection/selection-client.tsx#L31)) |
| `pas_assez_produits` | Redirection automatique vers `/something-to-add` quand le matching renvoie trop peu de produits ([SomethingToAddForm.tsx](../components/flow/SomethingToAddForm.tsx)) |
| `pas_trouve_recherchez` | Clic "Pas trouvé ce que vous cherchez ?" sur `/selection` ([SupplierSelectionModal.tsx](../components/flow/SupplierSelectionModal.tsx)) |

```
                    funnel-start (flow_type: null)
                              │
                              ▼
                       assurance (variantes 0/1/null)
                              │
                              ▼
                      questionnaire (flow_type: null)
                              │
                              ▼
                       choix-propart (flow_type: null)
                              │
                              ▼
                        matching API
                              │
               ┌──────────────┴──────────────┐
               ▼                              ▼
        budget displayable             pas assez de produits
               │                              │
               ▼                              ▼
       selection-produits             description-besoin
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

### Étapes & payloads additionnels

| step_name | step_type | Fonction émettrice | Payload additionnel |
|---|---|---|---|
| `funnel-start` | `init` | `trackFunnelStart(context?)` | — |
| `assurance` | `init` | `trackAssuranceView()` | `is_first_view: boolean` |
| `assurance-complete` | `init` | `trackAssuranceComplete()` | — |
| `1ere-question`, `2eme-question`, … `Neme-question` | `question` | `trackQuestionView(questionIndex)` | — (le numéro est codé dans `step_name`) |
| `questionnaire-complete` | `question` | `trackQuestionnaireComplete(totalQuestions, timeSpentSeconds)` | `total_questions: number`, `time_spent_seconds: number` |
| `geo-zone` | `localisation` | `trackGeoZoneView()` | `is_first_view: boolean` |
| `geo-zone-complete` | `localisation` | `trackGeoZoneComplete()` | — |
| `choix-propart` | `choix-propart` | `trackProfileView()` | — |
| `choix-propart-complete` | `choix-propart` | `trackProfileComplete(profileType)` | `profile_type: string` |
| `budget` | `prix` | `trackBudgetView()` | — |
| `budget-complete` | `prix` | `trackBudgetComplete(budgetRange)` | `budget_range: string` |
| `budget-retour` | `prix` | `trackBudgetReturn(budgetRange)` | `budget_range: string \| null` |
| `selection-produits` | `selection` | `trackSelectionPageView(recommended, total)` | `recommended_count: number`, `total_count: number` |
| `product-selection` | `selection` | `trackProductSelectionChange(productId, action, totalSelected)` | `product_id: string`, `action: 'ajouter'\|'retirer'`, `total_selected: number`, `is_first_add?: boolean`, `is_first_remove?: boolean` |
| `vue-comparaison` | `selection` | `trackComparisonModalView()` **[non utilisé]** | `is_first_view: boolean` |
| `vue-criteres` | `selection` | `trackModifyCriteriaModalView()` | `is_first_view: boolean` |
| `criteres-modifies` | `selection` | `trackCriteriaModified(criteriaCount)` | `criteria_count: number` |
| `vue-produit` | `selection` | `trackProductModalView(productId)` | `product_id: string`, `is_first_view: boolean` |
| `formulaire-contact` | `contact` | `trackContactFormView(selectedSuppliersCount)` | `selected_count: number` |
| `description-besoin` | `contact` | `trackCustomNeedPageView()` | `is_first_view: boolean` |
| `formulaire-contact-simple` | `contact` | `trackCustomNeedContactView()` | — |
| `validation-error` | `contact` | `trackFormValidationErrors(errorsCount, errors?)` | `errors_count: number`, `errors?: Array<{field, type, message}>` |
| `submit-success` | `conversion` | `trackLeadSubmitted(suppliersCount, profileType, userKnownStatus)` | `nombre_fournisseur: number`, `profile_type: string`, `user_known_status: 'known'\|'unknown'`, `conversion: true` |
| `submit-error` | `conversion` | `trackLeadSubmissionError(errorType, errorMessage)` | `error_type: string`, `error_message: string`, `conversion: false` |

---

## Événements secondaires

Émis directement via `pushToDataLayer()` (sans passer par `trackQuoteFunnel`).

### `device_info`

Émis une fois par session par `trackDeviceInfo()` ([gtm.ts:534](../lib/analytics/gtm.ts#L534)), depuis `AnalyticsProvider`.

```javascript
{
  event: 'device_info',
  user_id: string,
  session_id: string,
  device_type: 'mobile' | 'tablet' | 'desktop',
  screen_width: number,
  screen_height: number,
  user_agent: string,
  timestamp: string  // ISO 8601
}
```

### `source_trafic`

Émis une fois par session par `trackTrafficSource()` ([gtm.ts:550](../lib/analytics/gtm.ts#L550)), depuis `AnalyticsProvider`. Parse les UTM params de l'URL.

```javascript
{
  event: 'source_trafic',
  user_id: string,
  session_id: string,
  utm_source: string,      // ou 'direct'
  utm_medium: string,      // ou 'none'
  utm_campaign: string,    // ou 'none'
  utm_term: string,
  utm_content: string,
  referrer: string,        // document.referrer ou 'direct'
  landing_page: string,
  timestamp: string
}
```

### `abandon_funnel` **[non utilisé]**

`trackFunnelAbandonment()` ([gtm.ts:509](../lib/analytics/gtm.ts#L509)) est exportée mais **jamais appelée** dans le code. Aucun mécanisme de détection d'abandon n'est branché aujourd'hui. À ré-évaluer ou supprimer.

```javascript
{
  event: 'abandon_funnel',
  user_id: string,
  session_id: string,
  step: string,
  step_number: number,
  time_spent_seconds: number,
  last_action: string,
  device_type, screen_width, screen_height, user_agent,
  timestamp: string
}
```

---

## Fonctions utilitaires

| Fonction | Rôle |
|---|---|
| `pushToDataLayer(event, data?)` ([gtm.ts](../lib/analytics/gtm.ts)) | Helper de bas niveau : `window.dataLayer.push({ event, ...data })`. Utilisé par toutes les fonctions de tracking et par `useDbTracking` (qui en récupère `getSessionId`). |
| `getSessionId(): string` | Récupère/crée le `hp_session_id` (sessionStorage). Réutilisé par `useDbTracking`. |
| `setFunnelContext(context)` / `getFunnelContext()` | Mémoise le contexte funnel (rubrique, abtest, etc.) pour l'inclure dans chaque event. `getFunnelContext()` est exportée mais **jamais appelée**. |
| `setFlowType(flowType)` / `getFlowType()` | Mémoise le `flow_type` courant. `getFlowType()` est exportée mais **jamais appelée**. |
| `resetTrackingState()` ([gtm.ts:85](../lib/analytics/gtm.ts#L85)) | Nettoyage F5 : supprime toutes les clés `hp_viewed_*` (déduplication `isFirstView`), réinitialise `hp_session_id`, et reset `funnelContext`/`currentStepIndex`/`currentFlowType`. Appelée par `FlowStorageReset.tsx`. |

Helpers internes (non exportés) : `getUserId()`, `isFirstView(key)`, `getDeviceType()`, `getDeviceInfo()`, et les variables d'état `currentStepIndex`, `funnelContext`, `currentFlowType`.

---

## Identifiants user / session

| Clé | Stockage | Format | Persistance |
|---|---|---|---|
| `hp_user_id` | `localStorage` | `user_{timestamp}_{random}` | Permanent (survit aux sessions) |
| `hp_session_id` | `sessionStorage` | `session_{timestamp}_{random}` | Durée de l'onglet — supprimé par `resetTrackingState()` au F5 |
| `hp_viewed_*` | `sessionStorage` | Booléen (`'true'`) | Clés de déduplication `isFirstView` — supprimées par `resetTrackingState()` au F5 |

---

## Inventaire complet des fonctions exportées

Source : `lib/analytics/index.ts` (qui ré-exporte `gtm.ts`).

### Funnel principal

| Fonction | Appelants (fichiers réels) |
|---|---|
| `trackFunnelStart()` (alias export `trackGTMFunnelStart`) | `NeedsQuestionnaire.tsx` |
| `trackAssuranceView()` | `AssurancePage.tsx` |
| `trackAssuranceComplete()` | `AssurancePage.tsx` |
| `trackQuestionView(questionIndex)` | `NeedsQuestionnaire.tsx` |
| `trackQuestionnaireComplete(total, time)` (alias `trackGTMQuestionnaireComplete`) | `NeedsQuestionnaire.tsx` |
| `trackGeoZoneView()` | `geo-zone-client.tsx` |
| `trackGeoZoneComplete()` | `geo-zone-client.tsx` |
| `trackProfileView()` | `ProfileTypeStep.tsx` |
| `trackProfileComplete(profileType)` | `ProfileTypeStep.tsx` |
| `trackBudgetView()` | `budget-client.tsx` |
| `trackBudgetComplete(budgetRange)` | `budget-client.tsx` |
| `trackBudgetReturn(budgetRange)` | `budget-client.tsx` |
| `trackSelectionPageView(recommended, total)` | `selection-client.tsx` |
| `trackProductSelectionChange(productId, action, total)` | `SupplierSelectionModal.tsx` |
| `trackModifyCriteriaModalView()` | `ModifyCriteriaForm.tsx` |
| `trackCriteriaModified(count)` | `ModifyCriteriaForm.tsx` |
| `trackProductModalView(productId)` | `ProductDetailModal.tsx` |
| `trackContactFormView(suppliersCount)` | `ContactForm.tsx` |
| `trackFormValidationErrors(count, errors?)` | `ContactForm.tsx`, `ContactFormSimple.tsx`, `CustomNeedForm.tsx` |
| `trackCustomNeedPageView()` | `SomethingToAddForm.tsx` |
| `trackCustomNeedContactView()` | `SomethingToAddForm.tsx`, `CustomNeedForm.tsx` |
| `trackLeadSubmitted(count, profileType, userKnownStatus)` (alias `trackGTMLeadSubmitted`) | `useLeadSubmission.ts` |
| `trackLeadSubmissionError(type, message)` | `useLeadSubmission.ts` |

### Hors funnel

| Fonction | Appelants |
|---|---|
| `trackDeviceInfo()` | `AnalyticsProvider.tsx` |
| `trackTrafficSource()` | `AnalyticsProvider.tsx` |

### Gestion du contexte

| Fonction | Appelants |
|---|---|
| `setFunnelContext(context)` | `NeedsQuestionnaire.tsx` |
| `setFlowType(flowType)` | `selection-client.tsx`, `SupplierSelectionModal.tsx` (x2), `SomethingToAddForm.tsx`, `CustomNeedForm.tsx` |
| `pushToDataLayer(event, data?)` | `useDbTracking.ts` (transit du session_id), interne |
| `resetTrackingState()` | `FlowStorageReset.tsx` |

---

## Dead code & fonctions dépréciées

| Fonction | Statut | Action recommandée |
|---|---|---|
| `getFunnelContext()` | Exportée, jamais appelée | Supprimer l'export ou justifier (utile debug ?) |
| `getFlowType()` | Exportée, jamais appelée | Supprimer — le `flowType` est récupéré via le store Zustand |
| `trackComparisonModalView()` | Exportée, jamais appelée. Pas de modale de comparaison active dans l'UI. | Supprimer ou implémenter la feature associée |
| `trackFunnelAbandonment()` | Exportée, jamais appelée. Aucune logique de détection d'abandon branchée. | Supprimer ou brancher un listener `pagehide`/`visibilitychange` |
| `trackQuestionNavigation()` | `@deprecated` dans le source | Conservée pour backward compat — pas d'appelant |
| `trackComparisonModalOpen()` | `@deprecated` dans le source — wrapper sur `trackComparisonModalView` (lui-même unused) | Supprimer la chaîne complète |
| `trackFormValidationError()` (singulier) | `@deprecated` — remplacée par `trackFormValidationErrors` (pluriel) | Conservée pour backward compat — pas d'appelant |

Fonctions documentées dans l'ancien doc et **qui n'ont jamais existé dans le code** (à oublier) :
- `trackProductCardClick`
- `trackQuestionAnswered`
- `trackProfileTypeSelected`
- `trackContactFieldFilled`
- `trackFormSubmitAttempt`

Events historiques marqués DEPRECATED dans l'ancien doc :
- `vue_page_votre_besoin` → remplacé par `devis_funnel_formulaire { step_name: 'description-besoin' }`
- `vue_page_vos_coordonnees` → remplacé par `devis_funnel_formulaire { step_name: 'formulaire-contact-simple' }`
- `vue_modal_produit` (raw) → remplacé par `devis_funnel_formulaire { step_name: 'vue-produit' }`
- `recherche_entreprise` (raw) → **n'existe plus**
- `page_vue_critere` (raw) → remplacé par `devis_funnel_formulaire { step_name: 'vue-criteres' }`
- `critere_modifie` (raw) → remplacé par `devis_funnel_formulaire { step_name: 'criteres-modifies' }`
- `utilisateur_identifie` (raw) → **n'existe plus**

---

## GA4 & Hotjar

### GA4 (`lib/analytics/ga4.ts`) — **inutilisé en production**

Fonctions définies, ré-exportées par `index.ts`, mais **aucune n'est appelée dans l'application** :

| Fonction | Signature |
|---|---|
| `trackEvent(action, category, label?, value?)` | Wrapper `gtag('event', action, …)` |
| `trackPageView(url, title?)` | `gtag('event', 'page_view', …)` |
| `trackFunnelStart()` (export `trackGA4FunnelStart`) | Alias `trackEvent('funnel_start', …)` |
| `trackQuestionnaireComplete(time)` (export `trackGA4QuestionnaireCompleteSimple`) | — |
| `trackLeadSubmitted(leadId, count)` (export `trackGA4LeadSubmittedSimple`) | — |
| `trackError(type, message)` | — |
| `trackGA4QuestionAnswered(questionId, answersCount)` | — |
| `trackGA4QuestionnaireComplete(total, time)` | — |
| `trackGA4ProfileComplete(profileType, hasCompany)` | — |
| `trackGA4SupplierSelection(supplierId, action, total)` | — |
| `trackGA4LeadSubmitted(leadId, suppliersCount, profileType)` | — |

GA4 reçoit malgré tout les events via la balise GTM (configurée côté GTM), donc l'absence d'appel direct est OK. Le module `ga4.ts` lui-même n'est plus nécessaire — candidat à suppression sauf intention claire de le rebrancher.

### Hotjar (`lib/analytics/hotjar.ts`) — **inutilisé en production**

Fonctions définies, ré-exportées, **aucune n'est appelée** :

| Fonction | Rôle |
|---|---|
| `hotjarEvent(name)` | `hj('event', name)` |
| `hotjarIdentify(userId, attrs?)` | `hj('identify', …)` |
| `hotjarStateChange(url)` | `hj('stateChange', url)` — pour SPA |
| `hotjarTagRecording(tags)` | `hj('tagRecording', tags)` |
| `hotjarTriggerSurvey(surveyId)` | `hj('trigger', surveyId)` |
| `tagHotjarUser(tag)` | Alias `hotjarTagRecording([tag])` |
| `HOTJAR_TAGS` (constante) | `STARTED_FUNNEL`, `COMPLETED_QUESTIONNAIRE`, `COMPLETED_PROFILE`, `USED_COMPARISON`, `CONVERTED` |

Le composant `<Hotjar />` ([components/analytics/](../components/analytics)) charge bien le script Hotjar via `app/layout.tsx`, donc le recording fonctionne. Mais aucun tagging ni identification n'est émis depuis l'app — candidat à brancher ou à supprimer.

---

## Configuration GTM recommandée

### Triggers

1. **Trigger Funnel** : `Event equals devis_funnel_formulaire`
2. **Trigger Conversion** : `Event equals devis_funnel_formulaire` AND `conversion equals true`
3. **Trigger Trafic Source** : `Event equals source_trafic` (1 hit par session)
4. **Trigger Device Info** : `Event equals device_info` (1 hit par session)

### Data Layer Variables

- `step_name`, `step_type`, `step_index`, `step_number`
- `flow_type`, `rubrique_id`, `product.category5`, `abtest2`
- `page_template_gtm`, `funnel_context`, `page_location_uri` (depuis le token URL)
- `conversion`, `profile_type`, `user_known_status`
- `user_id`, `session_id`

---

## KPIs

### Funnel principal

| KPI | Filtre |
|---|---|
| Arrivée funnel | `step_name = 'funnel-start'` |
| Vue assurance | `step_name = 'assurance'` |
| Vue Q1 | `step_name = '1ere-question'` |
| Complétion questionnaire | `step_name = 'questionnaire-complete'` |
| Arrivée profil | `step_name = 'choix-propart'` |
| Vue page budget | `step_name = 'budget'` |
| Choix tranche budget | `step_name = 'budget-complete'` |
| Arrivée sélection | `step_name = 'selection-produits'` |
| Arrivée formulaire | `step_name = 'formulaire-contact'` |
| Leads validés | `step_name = 'submit-success'` |
| Erreurs soumission | `step_name = 'submit-error'` |

### Déduplication (1ʳᵉ vue par session)

Les fonctions qui poussent un `is_first_view: boolean` permettent de compter à la fois le total et les vues uniques :

| step_name | Total | Unique |
|---|---|---|
| `assurance` | `COUNT(*)` | `COUNT(*) WHERE is_first_view = true` |
| `geo-zone` | `COUNT(*)` | `COUNT(*) WHERE is_first_view = true` |
| `vue-criteres` | `COUNT(*)` | `COUNT(*) WHERE is_first_view = true` |
| `vue-produit` | `COUNT(*)` | `COUNT(*) WHERE is_first_view = true` |
| `description-besoin` | `COUNT(*)` | `COUNT(*) WHERE is_first_view = true` |

Pour `product-selection` : `is_first_add` et `is_first_remove` jouent le même rôle.

### Analyse par parcours

| KPI | Filtre |
|---|---|
| Conversions parcours principal | `step_name = 'submit-success'` AND `flow_type = 'principal'` |
| Conversions parcours "pas assez produits" | `step_name = 'submit-success'` AND `flow_type = 'pas_assez_produits'` |
| Conversions parcours "pas trouvé" | `step_name = 'submit-success'` AND `flow_type = 'pas_trouve_recherchez'` |
| Redirections automatiques | `step_name = 'description-besoin'` AND `flow_type = 'pas_assez_produits'` |
| Clics "pas trouvé" | `step_name = 'description-besoin'` AND `flow_type = 'pas_trouve_recherchez'` |

---

## Tracking DB parallèle

En complément de GTM, l'application pousse des events vers une table de tracking interne via `useDbTracking()` ([hooks/tracking/useDbTracking.ts](../hooks/tracking/useDbTracking.ts)) → `POST /api/tck`. Cette couche est **distincte** de GTM (deux destinations, deux schémas) et est utilisée pour les analyses internes côté HelloPro.

Bail-out automatique sur `localhost` ([useDbTracking.ts:51](../hooks/tracking/useDbTracking.ts#L51)) — rien n'est envoyé en dev local.

Events DB observés dans le code (`event_type.event_name`) :

| Event DB | Émis depuis | Notes |
|---|---|---|
| `questionnaire.assurance_view` / `assurance_complete` | `AssurancePage.tsx` | Page assurance pré-Q1 |
| `questionnaire.*` (questions répondues) | `useDynamicQuestionnaire.ts` | `step_index = numéro de question` |
| `profile.geo_zone_view`, `profile.geo_zone_complete` | `geo-zone-client.tsx` | Voir convention `profile.*` |
| `profile.*` (autres) | `useProcessMatchingLogic.ts` (commenté) | À confirmer |
| `matching.success` / `matching.insufficient_results` | `useProcessMatching.ts` | step_index 2. Avant navigation — indépendant d'une vue de `/selection` |
| `matching.refetch` | `useProcessMatching.ts` | Refetch après modification des critères |
| `pricing.budget_view` | `budget-client.tsx` | Guard `sessionStorage hp_viewed_db_budget_view` (1× par session) |
| `pricing.budget_return` | `budget-client.tsx` | Clic "Précédent" depuis `/budget` |
| `selection.selection_view` | `selection-client.tsx` | Guard `sessionStorage hp_viewed_db_selection_view` — séparé de `matching.success`, mesure la vue effective de la page |
| `selection.select` / `selection.deselect` | `SupplierSelectionModal.tsx` | Action utilisateur sur un fournisseur |
| `contact.*`, `conversion.*` | `useLeadSubmission.ts` | Soumission de lead |

Convention anti-doublons : pour les events de vue de page sujets aux remounts React, utiliser une clé `sessionStorage` `hp_viewed_db_<event_name>` (préfixe `hp_viewed_` → nettoyé par `resetTrackingState()` au F5). Voir [budget-client.tsx:75-79](../app/(flow)/budget/budget-client.tsx#L75-L79) et [selection-client.tsx](../app/(flow)/selection/selection-client.tsx) comme références.

> Si tu cherches la doc complète du tracking DB (schéma de payload `/api/tck`, mapping `type_flow`/`type_dmd_categ`), commence par [useDbTracking.ts](../hooks/tracking/useDbTracking.ts) — il n'existe pas de doc séparée à ce jour.
