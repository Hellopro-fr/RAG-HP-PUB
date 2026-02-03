# 🚀 Guide de Migration API - NextJS App

## 📋 Résumé Exécutif

Toute l'infrastructure pour récupérer les données dynamiquement depuis une API est **prête et fonctionnelle**.

Les données actuelles sont statiques (codées en dur dans le code). Pour les rendre dynamiques, il suffit de :
1. Configurer l'URL de l'API
2. Remplacer les imports statiques par les hooks React Query
3. Tester

**Temps estimé : 2-3 heures pour tout migrer**

---

## ✅ Ce qui est déjà fait

### 1. Services API (lib/api/services/)
- ✅ **questions.service.ts** - Récupérer les questions
- ✅ **suppliers.service.ts** - Récupérer les fournisseurs
- ✅ **companies.service.ts** - Recherche SIREN
- ✅ **location.service.ts** - Codes postaux & villes
- ✅ **leads.service.ts** - Envoyer les demandes de devis

Tous incluent un **fallback automatique** sur les données locales si l'API ne répond pas.

### 2. Hooks React avec React Query (hooks/api/)
- ✅ **useQuestions.ts** - Hook avec cache automatique pour questions
- ✅ **useSuppliers.ts** - Hook avec cache pour fournisseurs
- ✅ **useCompanies.ts** - Hook pour recherche SIREN
- ✅ **useLeadSubmission.ts** - Hook mutation pour envoyer leads

**Avantage React Query :**
- ✅ Cache automatique
- ✅ Revalidation en arrière-plan
- ✅ Retry automatique en cas d'erreur
- ✅ Optimistic UI
- ✅ DevTools pour debugging

### 3. Configuration
- ✅ **Client HTTP** avec gestion timeout & erreurs
- ✅ **Endpoints** centralisés et configurables
- ✅ **Types TypeScript** stricts
- ✅ **React Query** configuré et prêt

### 4. Documentation complète
- ✅ **API_INTEGRATION.md** - Guide complet d'utilisation
- ✅ **API_MIGRATION_CHECKLIST.md** - Plan de migration
- ✅ **EXAMPLE_MIGRATION.md** - Exemple concret
- ✅ **hooks/README.md** - Documentation des hooks React Query
- ✅ **.env.local.example** - Template de configuration

---

## 🎯 Comment activer les données dynamiques

### Étape 1 : Configuration (2 min)

Créer le fichier `.env.local` à la racine :

```bash
cd C:\Users\Tsihoarana\Documents\Hellopro\VSCODE\nextjsapp-formulaireV1
cp .env.local.example .env.local
```

Éditer `.env.local` :

```env
# URL de votre API backend
NEXT_PUBLIC_API_BASE_URL=https://api.hellopro.fr/v1
```

### Étape 2 : Migrer les composants

#### Exemple : NeedsQuestionnaire (15 min)

**AVANT (données statiques) :**
```typescript
import { QUESTIONS_DATA } from '@/data/questions';

function NeedsQuestionnaire() {
  const questions = QUESTIONS_DATA;
  // ...
}
```

**APRÈS (données dynamiques avec React Query) :**
```typescript
import { useQuestions } from '@/hooks/api';

function NeedsQuestionnaire() {
  const { data: questions, isLoading, error, refetch } = useQuestions();

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error.message} onRetry={() => refetch()} />;

  // Le reste du code reste identique
  // ...
}
```

#### Exemple : SupplierSelectionModal (20 min)

**AVANT :**
```typescript
const RECOMMENDED_SUPPLIERS = [/* données statiques */];
const OTHER_SUPPLIERS = [/* données statiques */];
```

**APRÈS :**
```typescript
import { useRecommendedSuppliers } from '@/hooks/api';
import { useFlowStore } from '@/lib/stores/flow-store';

function SupplierSelectionModal() {
  const { userAnswers } = useFlowStore();
  const { data, isLoading, error } = useRecommendedSuppliers(userAnswers);

  if (isLoading) return <MatchingLoader />;
  if (error) return <ErrorState error={error.message} />;

  const recommended = data?.recommended || [];
  const others = data?.others || [];

  // Utiliser recommended et others au lieu des constantes
}
```

### Étape 3 : Tester (30 min)

```bash
npm run dev
```

1. **Tester avec API** : Vérifier que les données sont chargées
2. **Tester sans API** : Mettre une mauvaise URL pour vérifier le fallback
3. **Tester les erreurs** : Vérifier les messages d'erreur

---

## 📁 Fichiers à modifier

### Priorité HAUTE (obligatoire)

| Fichier | Hook à utiliser | Temps |
|---------|----------------|-------|
| `components/flow/NeedsQuestionnaire.tsx` | `useQuestions()` | 15 min |
| `components/flow/QuestionScreen.tsx` | `useQuestions()` | 10 min |
| `components/flow/SupplierSelectionModal.tsx` | `useRecommendedSuppliers(answers)` | 20 min |
| `components/flow/ContactForm.tsx` | `useLeadSubmission()` | 20 min |

**Total : 65 min**

### Priorité MOYENNE (optionnel)

| Fichier | Hook à utiliser | Temps |
|---------|----------------|-------|
| `components/flow/ContactFormSimple.tsx` | `useLeadSubmission()` | 15 min |

**Total : 15 min**

---

## 🔍 Détails techniques

### Import des hooks

**TOUJOURS utiliser `@/hooks/api`** :

```typescript
// ✅ CORRECT - Utilise React Query
import { useQuestions, useRecommendedSuppliers } from '@/hooks/api';

// ❌ INCORRECT - N'existe plus
import { useQuestions } from '@/hooks';
```

### Structure de réponse React Query

```typescript
const {
  data,        // Les données (undefined pendant le chargement)
  isLoading,   // true pendant le premier chargement
  isFetching,  // true pendant le rafraîchissement
  error,       // Error object si erreur
  isError,     // boolean si erreur
  isSuccess,   // boolean si succès
  refetch,     // fonction pour recharger
} = useQuestions();
```

### Mutations (POST/PUT/DELETE)

Pour les mutations comme l'envoi de formulaire :

```typescript
const { mutate, isPending, error, isSuccess } = useLeadSubmission();

const handleSubmit = (data) => {
  mutate(data, {
    onSuccess: () => {
      // Succès
      router.push('/confirmation');
    },
    onError: (error) => {
      // Erreur
      toast.error(error.message);
    }
  });
};
```

---

## ✨ Avantages de React Query

### 🚀 Cache automatique
Une fois les données chargées, elles sont en cache. Navigation instantanée !

### 🔄 Revalidation automatique
Les données sont automatiquement rafraîchies en arrière-plan pour rester à jour.

### ⚡ Performance optimale
- Dedupe automatique des requêtes identiques
- Prefetching possible
- Lazy loading intégré

### 🛠️ DevTools inclus
Visualiser le cache et les requêtes en temps réel.

```bash
npm install @tanstack/react-query-devtools
```

---

## 📚 Documentation détaillée

1. **[hooks/README.md](../hooks/README.md)**
   - Documentation complète des hooks React Query
   - Exemples d'utilisation
   - Comparaison avec hooks basiques

2. **[API_INTEGRATION.md](./API_INTEGRATION.md)**
   - Guide complet d'utilisation
   - Structure des données
   - Services disponibles

3. **[API_MIGRATION_CHECKLIST.md](./API_MIGRATION_CHECKLIST.md)**
   - Plan de migration étape par étape
   - Tests recommandés

4. **[EXAMPLE_MIGRATION.md](./EXAMPLE_MIGRATION.md)**
   - Exemple concret de migration
   - Code avant/après

---

## 🎯 Plan d'action recommandé

### Phase 1 : Questions (30 min)
- [ ] Migrer `NeedsQuestionnaire.tsx` → `useQuestions()`
- [ ] Migrer `QuestionScreen.tsx` → `useQuestions()`
- [ ] Tester le questionnaire

### Phase 2 : Fournisseurs (30 min)
- [ ] Migrer `SupplierSelectionModal.tsx` → `useRecommendedSuppliers()`
- [ ] Tester la sélection

### Phase 3 : Formulaires (30 min)
- [ ] Migrer `ContactForm.tsx` → `useLeadSubmission()`
- [ ] Migrer `ContactFormSimple.tsx` → `useLeadSubmission()`
- [ ] Tester l'envoi

### Phase 4 : Tests finaux (30 min)
- [ ] Test flow complet
- [ ] Test avec API indisponible (fallback)
- [ ] Test performance

**Temps total : 2 heures**

---

## 🐛 Debugging

### Console développeur
Ouvrir F12 → Onglet "Network" pour voir les appels API

### React Query DevTools
Visualiser le cache en temps réel

### Forcer les données locales
```env
NEXT_PUBLIC_API_BASE_URL=/api-disabled
```

---

## ⚠️ Points importants

### Toujours utiliser hooks/api/
```typescript
// ✅ CORRECT
import { useQuestions } from '@/hooks/api';

// ❌ INCORRECT
import { useQuestions } from '@/hooks';
```

### Gestion des états
```typescript
// ✅ CORRECT - Vérifier isLoading et error
if (isLoading) return <Spinner />;
if (error) return <Error message={error.message} />;

// ❌ INCORRECT - Ne pas oublier les états
return <div>{data.map(...)}</div>; // Crash si data est undefined!
```

### Mutations vs Queries
```typescript
// GET - useQuery (hook auto)
const { data } = useQuestions();

// POST/PUT/DELETE - useMutation (manuel)
const { mutate } = useLeadSubmission();
mutate(data);
```

---

## 📊 Récapitulatif

| Aspect | Status |
|--------|--------|
| Infrastructure API | ✅ Complète |
| Hooks React Query | ✅ Prêts |
| Documentation | ✅ Complète |
| Configuration | ✅ Template fourni |
| Fallback | ✅ Automatique |
| Cache | ✅ React Query |
| TypeScript | ✅ Strict |

---

## 🎉 Conclusion

**L'infrastructure est complète et professionnelle !**

React Query offre :
- ✅ Cache automatique
- ✅ Revalidation en arrière-plan
- ✅ Retry automatique
- ✅ DevTools
- ✅ Performance optimale

**Il ne reste plus qu'à migrer les composants (2h de travail)**

---

**Status actuel :** ✅ Prêt pour la migration

**Package utilisé :** @tanstack/react-query

**Date :** 2026-01-18
