# Guide d'intégration API

Ce document explique comment utiliser les services API et hooks React pour récupérer les données dynamiquement.

## 📋 Table des matières

1. [Configuration](#configuration)
2. [Services API disponibles](#services-api-disponibles)
3. [Hooks React](#hooks-react)
4. [Exemples d'utilisation](#exemples-dutilisation)
5. [Structure des données](#structure-des-données)

---

## ⚙️ Configuration

### Variables d'environnement

Créez un fichier `.env.local` à la racine du projet :

```env
# URL de base de l'API
NEXT_PUBLIC_API_BASE_URL=https://api.hellopro.fr/v1
```

Si cette variable n'est pas définie, l'API utilisera `/api` par défaut (API routes Next.js).

---

## 🔌 Services API disponibles

### Questions Service

Fichier : `lib/api/services/questions.service.ts`

```typescript
// Récupérer toutes les questions
const response = await fetchQuestions();

// Récupérer une question par ID
const response = await fetchQuestionById(1);
```

### Suppliers Service

Fichier : `lib/api/services/suppliers.service.ts`

```typescript
// Récupérer tous les fournisseurs
const response = await fetchSuppliers();

// Récupérer un fournisseur par ID
const response = await fetchSupplierById("supplier-123");

// Récupérer les fournisseurs recommandés basés sur les réponses
const response = await fetchRecommendedSuppliers(userAnswers);

// Rechercher des fournisseurs
const response = await searchSuppliers({ q: "pont élévateur" });
```

### Format de réponse

Toutes les fonctions API retournent un objet `ApiResponse<T>` :

```typescript
interface ApiResponse<T> {
  data: T | null;
  error: string | null;
  status: number;
}
```

---

## 🪝 Hooks React

Les hooks facilitent l'utilisation des services API dans les composants React.

### useQuestions

Récupère toutes les questions depuis l'API.

```typescript
import { useQuestions } from '@/hooks';

function MyComponent() {
  const { questions, loading, error, refetch } = useQuestions();

  if (loading) return <div>Chargement...</div>;
  if (error) return <div>Erreur : {error}</div>;

  return (
    <div>
      {questions.map(q => (
        <div key={q.id}>{q.question}</div>
      ))}
    </div>
  );
}
```

### useQuestion

Récupère une question spécifique par son ID.

```typescript
import { useQuestion } from '@/hooks';

function QuestionDetail({ questionId }: { questionId: number }) {
  const { question, loading, error, refetch } = useQuestion(questionId);

  if (loading) return <div>Chargement...</div>;
  if (error) return <div>Erreur : {error}</div>;
  if (!question) return <div>Question non trouvée</div>;

  return <div>{question.question}</div>;
}
```

### useRecommendedSuppliers

Récupère les fournisseurs recommandés basés sur les réponses utilisateur.

```typescript
import { useRecommendedSuppliers } from '@/hooks';
import { useFlowStore } from '@/lib/stores/flow-store';

function SupplierSelection() {
  const { userAnswers } = useFlowStore();
  const { recommended, others, loading, error, refetch } = useRecommendedSuppliers(userAnswers);

  if (loading) return <div>Chargement...</div>;
  if (error) return <div>Erreur : {error}</div>;

  return (
    <div>
      <h2>Recommandés ({recommended.length})</h2>
      {recommended.map(supplier => (
        <SupplierCard key={supplier.id} {...supplier} />
      ))}

      <h2>Autres résultats ({others.length})</h2>
      {others.map(supplier => (
        <SupplierCard key={supplier.id} {...supplier} />
      ))}
    </div>
  );
}
```

### useSupplierSearch

Hook pour rechercher des fournisseurs.

```typescript
import { useSupplierSearch } from '@/hooks';

function SupplierSearchComponent() {
  const { suppliers, loading, error, search } = useSupplierSearch();
  const [query, setQuery] = useState('');

  const handleSearch = () => {
    search(query);
  };

  return (
    <div>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Rechercher..."
      />
      <button onClick={handleSearch}>Rechercher</button>

      {loading && <div>Recherche en cours...</div>}
      {error && <div>Erreur : {error}</div>}

      {suppliers.map(supplier => (
        <div key={supplier.id}>{supplier.productName}</div>
      ))}
    </div>
  );
}
```

---

## 💡 Exemples d'utilisation

### Exemple 1 : Composant NeedsQuestionnaire avec API

**Avant (données statiques) :**

```typescript
import { QUESTIONS_DATA } from '@/data/questions';

function NeedsQuestionnaire() {
  const questions = QUESTIONS_DATA;
  // ...
}
```

**Après (données dynamiques) :**

```typescript
import { useQuestions } from '@/hooks';

function NeedsQuestionnaire() {
  const { questions, loading, error } = useQuestions();

  if (loading) {
    return <LoadingSpinner />;
  }

  if (error) {
    return <ErrorMessage message={error} />;
  }

  // Le reste du composant reste identique
  // ...
}
```

### Exemple 2 : SupplierSelectionModal avec API

**Avant (données statiques) :**

```typescript
const RECOMMENDED_SUPPLIERS = [/* ... */];
const OTHER_SUPPLIERS = [/* ... */];

function SupplierSelectionModal() {
  const suppliers = [...RECOMMENDED_SUPPLIERS, ...OTHER_SUPPLIERS];
  // ...
}
```

**Après (données dynamiques) :**

```typescript
import { useRecommendedSuppliers } from '@/hooks';
import { useFlowStore } from '@/lib/stores/flow-store';

function SupplierSelectionModal() {
  const { userAnswers } = useFlowStore();
  const { recommended, others, loading, error } = useRecommendedSuppliers(userAnswers);

  if (loading) {
    return <MatchingLoader />;
  }

  if (error) {
    return <ErrorMessage message={error} />;
  }

  const suppliers = [...recommended, ...others];
  // Le reste du composant reste identique
  // ...
}
```

---

## 📊 Structure des données

### Question

```typescript
interface Question {
  id: number;
  question: string;
  description?: string;
  answers: Answer[];
  multipleChoice: boolean;
  category?: string;
}

interface Answer {
  id: string;
  text: string;
  secondaryText?: string;
  image?: string;
}
```

### Supplier

```typescript
interface Supplier {
  id: string;
  productName: string;
  supplierName: string;
  rating: number;
  distance: number;
  matchScore: number;
  image: string;
  images: string[];
  media?: MediaItem[];
  isRecommended: boolean;
  isCertified?: boolean;
  matchGaps: string[];
  description: string;
  descriptionHtml?: string;
  specs: ProductSpec[];
  supplier: SupplierInfo;
  price?: PriceInfo;
}
```

### UserAnswers

```typescript
type UserAnswers = Record<number, string[]>;

// Exemple:
const userAnswers = {
  1: ["2-colonnes"],
  2: ["4T"],
  3: ["traverse-superieure"],
  4: ["400V"],
  5: ["ile-de-france"]
};
```

---

## 🔄 Fallback sur données locales

**Tous les services API incluent un fallback automatique** vers les données statiques locales si :
- L'API n'est pas disponible
- Une erreur réseau se produit
- Le timeout est atteint (30 secondes par défaut)

Cela garantit que l'application fonctionne toujours, même sans connexion API.

---

## 🚀 Prochaines étapes

Pour activer les appels API dynamiques dans vos composants :

1. **Remplacer les imports statiques** par les hooks appropriés
2. **Gérer les états de chargement** avec des spinners/skeletons
3. **Afficher les erreurs** de manière conviviale
4. **Tester avec l'API réelle** une fois qu'elle est disponible

### Composants à mettre à jour :

- ✅ `NeedsQuestionnaire.tsx` → utiliser `useQuestions()`
- ✅ `QuestionScreen.tsx` → utiliser `useQuestion(questionId)`
- ✅ `SupplierSelectionModal.tsx` → utiliser `useRecommendedSuppliers(userAnswers)`
- ✅ `ProductDetailModal.tsx` → utiliser `useSupplier(supplierId)` si nécessaire

---

## 📝 Notes importantes

1. **Environnement de développement** : Sans configuration API, les données locales seront utilisées
2. **Production** : Configurez `NEXT_PUBLIC_API_BASE_URL` pour pointer vers l'API réelle
3. **Cache** : Considérez l'utilisation de React Query ou SWR pour le caching avancé
4. **Optimisation** : Les hooks actuels sont simples. Pour des besoins avancés (cache, revalidation), utilisez SWR ou React Query

---

## 🛠️ Debugging

Pour voir les appels API dans la console :

```typescript
// Dans lib/api/client.ts, ajoutez des console.log
console.log('API Request:', url);
console.log('API Response:', data);
```

Pour forcer l'utilisation des données locales pendant le développement :

```typescript
// Dans .env.local
NEXT_PUBLIC_API_BASE_URL=/api-disabled
```

Cela forcera les services à utiliser le fallback local.
