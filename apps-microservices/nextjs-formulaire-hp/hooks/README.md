# React Hooks pour API (avec React Query)

Ce dossier contient les hooks React personnalisés pour interagir avec l'API backend.

**Tous les hooks utilisent React Query** pour le caching, la revalidation automatique et la gestion optimale des états.

## 📁 Structure

```
hooks/
├── api/
│   ├── useQuestions.ts         # Hooks pour les questions
│   ├── useSuppliers.ts         # Hooks pour les fournisseurs
│   ├── useCompanies.ts         # Hooks pour la recherche SIREN
│   ├── useLeadSubmission.ts    # Hook pour envoyer des leads
│   └── index.ts                # Export centralisé
├── use-toast.ts                # Hook toast UI
└── README.md                   # Ce fichier
```

## 🎯 Hooks disponibles

### Questions

#### `useQuestions()`
Récupère toutes les questions depuis l'API avec cache automatique.

```typescript
import { useQuestions } from '@/hooks/api';

const { data: questions, isLoading, error, refetch } = useQuestions();
```

**Retour (React Query):**
- `data`: `Question[] | undefined` - Liste des questions
- `isLoading`: `boolean` - État de chargement
- `error`: `Error | null` - Erreur éventuelle
- `refetch`: `() => void` - Fonction pour recharger
- `isError`: `boolean` - Si une erreur est survenue
- `isSuccess`: `boolean` - Si le chargement a réussi

**Cache:** 1 heure (staleTime)

---

### Fournisseurs

#### `useSuppliers()`
Récupère tous les fournisseurs.

```typescript
import { useSuppliers } from '@/hooks/api';

const { data: suppliers, isLoading, error } = useSuppliers();
```

---

#### `useRecommendedSuppliers(answers: UserAnswers)`
Récupère les fournisseurs recommandés basés sur les réponses utilisateur.

```typescript
import { useRecommendedSuppliers } from '@/hooks/api';
import { useFlowStore } from '@/lib/stores/flow-store';

const { userAnswers } = useFlowStore();
const { data, isLoading, error } = useRecommendedSuppliers(userAnswers);

// data contient { recommended: Supplier[], others: Supplier[] }
const recommended = data?.recommended || [];
const others = data?.others || [];
```

**Cache:** Les données sont mises en cache par combinaison de réponses

---

### Lead Submission

#### `useLeadSubmission()`
Hook pour envoyer des demandes de devis.

```typescript
import { useLeadSubmission } from '@/hooks/api';

const { mutate, isPending, error, isSuccess } = useLeadSubmission();

const handleSubmit = (data: LeadData) => {
  mutate(data, {
    onSuccess: () => {
      router.push('/confirmation');
    },
    onError: (error) => {
      toast.error('Erreur: ' + error.message);
    }
  });
};
```

**Note:** C'est une **mutation** (POST), pas une query (GET).

---

### Companies (Recherche SIREN)

#### `useCompanies(query: string)`
Hook pour rechercher des entreprises par SIREN.

```typescript
import { useCompanies } from '@/hooks/api';

const [query, setQuery] = useState('');
const { data: companies, isLoading } = useCompanies(query);
```

---

## 💡 Exemples d'utilisation

### Exemple 1: Charger des questions

```typescript
'use client';

import { useQuestions } from '@/hooks/api';

export default function QuestionnairePage() {
  const { data: questions, isLoading, error, refetch } = useQuestions();

  if (isLoading) {
    return <div>Chargement des questions...</div>;
  }

  if (error) {
    return (
      <div>
        <p>Erreur: {error.message}</p>
        <button onClick={() => refetch()}>Réessayer</button>
      </div>
    );
  }

  return (
    <div>
      {questions?.map((q) => (
        <div key={q.id}>
          <h3>{q.question}</h3>
          {q.answers.map((a) => (
            <button key={a.id}>{a.text}</button>
          ))}
        </div>
      ))}
    </div>
  );
}
```

### Exemple 2: Fournisseurs recommandés

```typescript
'use client';

import { useRecommendedSuppliers } from '@/hooks/api';
import { useFlowStore } from '@/lib/stores/flow-store';

export default function SelectionPage() {
  const { userAnswers } = useFlowStore();
  const { data, isLoading, error } = useRecommendedSuppliers(userAnswers);

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error.message} />;

  const recommended = data?.recommended || [];
  const others = data?.others || [];

  return (
    <div>
      <section>
        <h2>Recommandés pour vous ({recommended.length})</h2>
        {recommended.map((supplier) => (
          <SupplierCard key={supplier.id} {...supplier} />
        ))}
      </section>

      <section>
        <h2>Autres résultats ({others.length})</h2>
        {others.map((supplier) => (
          <SupplierCard key={supplier.id} {...supplier} />
        ))}
      </section>
    </div>
  );
}
```

### Exemple 3: Envoyer un lead

```typescript
'use client';

import { useLeadSubmission } from '@/hooks/api';
import { useRouter } from 'next/navigation';
import { toast } from '@/hooks/use-toast';

export default function ContactForm() {
  const router = useRouter();
  const { mutate: submitLead, isPending } = useLeadSubmission();

  const handleSubmit = (data: ContactFormData) => {
    submitLead(data, {
      onSuccess: () => {
        toast({ title: 'Demande envoyée avec succès!' });
        router.push('/confirmation');
      },
      onError: (error) => {
        toast({
          title: 'Erreur',
          description: error.message,
          variant: 'destructive'
        });
      }
    });
  };

  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      handleSubmit(formData);
    }}>
      {/* Champs du formulaire */}
      <button type="submit" disabled={isPending}>
        {isPending ? 'Envoi...' : 'Envoyer'}
      </button>
    </form>
  );
}
```

---

## 🔄 Avantages de React Query

### Cache automatique
Les données sont mises en cache. Si vous naviguez et revenez, les données sont **instantanément** disponibles.

### Revalidation en arrière-plan
Les données sont automatiquement rafraîchies en arrière-plan pour rester à jour.

### Gestion optimale des états
- `isLoading`: Premier chargement
- `isFetching`: Rafraîchissement en arrière-plan
- `isError`: Erreur survenue
- `isSuccess`: Données chargées avec succès

### Retry automatique
En cas d'erreur réseau, React Query réessaye automatiquement.

### Optimistic updates
Vous pouvez mettre à jour l'UI immédiatement avant la réponse du serveur.

---

## 🛠️ Configuration React Query

React Query doit être configuré dans l'application. Vérifier que vous avez un `QueryClientProvider` :

```typescript
// app/layout.tsx ou app/providers.tsx
'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const queryClient = new QueryClient();

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}
```

---

## 📚 Documentation React Query

Pour aller plus loin avec React Query :
- [Documentation officielle](https://tanstack.com/query/latest)
- [Guide de migration](https://tanstack.com/query/latest/docs/react/guides/migrating-to-react-query-4)
- [DevTools](https://tanstack.com/query/latest/docs/react/devtools)

---

## 🆚 Différence avec les hooks basiques

| Aspect | Hooks basiques (useState) | Hooks React Query |
|--------|---------------------------|-------------------|
| Cache | ❌ Non | ✅ Automatique |
| Revalidation | ❌ Manuelle | ✅ Automatique |
| Loading states | ⚠️ À gérer | ✅ Intégré |
| Retry | ❌ Non | ✅ Automatique |
| Optimistic UI | ❌ Complexe | ✅ Simple |
| DevTools | ❌ Non | ✅ Oui |
| Performance | ⚠️ Moyenne | ✅ Excellente |

**Conclusion:** Utilisez toujours les hooks dans `hooks/api/` qui utilisent React Query.

---

## 🐛 Debugging

### React Query DevTools

Installez les DevTools pour visualiser le cache :

```bash
npm install @tanstack/react-query-devtools
```

```typescript
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';

<QueryClientProvider client={queryClient}>
  {children}
  <ReactQueryDevtools initialIsOpen={false} />
</QueryClientProvider>
```

### Logs personnalisés

```typescript
const { data, isLoading, error } = useQuestions();

console.log('Questions:', data);
console.log('Loading:', isLoading);
console.log('Error:', error);
```

---

## 📖 Ressources

- [Documentation API](../docs/API_INTEGRATION.md)
- [Checklist de migration](../docs/API_MIGRATION_CHECKLIST.md)
- [Exemple de migration](../docs/EXAMPLE_MIGRATION.md)
- [React Query Docs](https://tanstack.com/query/latest)

---

**Dernière mise à jour:** 2026-01-18
**Package:** @tanstack/react-query
