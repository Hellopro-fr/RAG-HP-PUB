# Exemple de Migration : SupplierSelectionModal

Ce document montre **exactement** comment migrer le composant `SupplierSelectionModal.tsx` des données statiques vers l'API dynamique.

---

## 🔴 AVANT : Version avec données statiques

```typescript
// components/flow/SupplierSelectionModal.tsx
'use client';

import { useState, useMemo } from "react";
// ... autres imports

// ❌ DONNÉES STATIQUES CODÉES EN DUR
const RECOMMENDED_SUPPLIERS: Supplier[] = [
  {
    id: "1",
    productName: "Pont élévateur Pro 4000",
    supplierName: "ÉQUIPGARAGE",
    // ... toutes les données
  },
  // ... 3 autres fournisseurs
];

const OTHER_SUPPLIERS: Supplier[] = [
  {
    id: "5",
    productName: "Pont garage 2 colonnes",
    // ... toutes les données
  },
  // ... 7 autres fournisseurs
];

const ALL_SUPPLIERS = [...RECOMMENDED_SUPPLIERS, ...OTHER_SUPPLIERS];

interface SupplierSelectionModalProps {
  userAnswers?: Record<number, string[]>;
  onBackToQuestionnaire?: () => void;
}

const SupplierSelectionModal = ({ userAnswers }: SupplierSelectionModalProps) => {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    new Set(RECOMMENDED_SUPPLIERS.map((s) => s.id))
  );

  // ... reste du code qui utilise RECOMMENDED_SUPPLIERS et OTHER_SUPPLIERS
};

export default SupplierSelectionModal;
```

---

## 🟢 APRÈS : Version avec API dynamique

```typescript
// components/flow/SupplierSelectionModal.tsx
'use client';

import { useState, useMemo } from "react";
import { useRecommendedSuppliers } from "@/hooks"; // ✅ IMPORT DU HOOK
// ... autres imports

// ✅ PLUS DE DONNÉES STATIQUES !

interface SupplierSelectionModalProps {
  userAnswers?: Record<number, string[]>;
  onBackToQuestionnaire?: () => void;
}

const SupplierSelectionModal = ({ userAnswers }: SupplierSelectionModalProps) => {
  // ✅ RÉCUPÉRATION DYNAMIQUE DES DONNÉES
  const {
    recommended: RECOMMENDED_SUPPLIERS,
    others: OTHER_SUPPLIERS,
    loading,
    error,
    refetch
  } = useRecommendedSuppliers(userAnswers || {});

  // ✅ GESTION DE L'ÉTAT DE CHARGEMENT
  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent" />
          <p className="mt-4 text-muted-foreground">Chargement des fournisseurs...</p>
        </div>
      </div>
    );
  }

  // ✅ GESTION DES ERREURS
  if (error) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-background p-6">
        <div className="max-w-md w-full bg-destructive/10 border border-destructive rounded-lg p-6">
          <h2 className="text-lg font-semibold text-destructive mb-2">
            Erreur de chargement
          </h2>
          <p className="text-sm text-muted-foreground mb-4">{error}</p>
          <button
            onClick={refetch}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
          >
            Réessayer
          </button>
        </div>
      </div>
    );
  }

  // ✅ LE RESTE DU CODE RESTE IDENTIQUE
  const ALL_SUPPLIERS = [...RECOMMENDED_SUPPLIERS, ...OTHER_SUPPLIERS];

  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    new Set(RECOMMENDED_SUPPLIERS.map((s) => s.id))
  );

  // ... reste du code inchangé
};

export default SupplierSelectionModal;
```

---

## 📝 Résumé des changements

### 1. Imports
```diff
+ import { useRecommendedSuppliers } from "@/hooks";
```

### 2. Suppression des constantes statiques
```diff
- const RECOMMENDED_SUPPLIERS: Supplier[] = [/* ... */];
- const OTHER_SUPPLIERS: Supplier[] = [/* ... */];
- const ALL_SUPPLIERS = [...RECOMMENDED_SUPPLIERS, ...OTHER_SUPPLIERS];
```

### 3. Ajout du hook
```diff
const SupplierSelectionModal = ({ userAnswers }: SupplierSelectionModalProps) => {
+  const {
+    recommended: RECOMMENDED_SUPPLIERS,
+    others: OTHER_SUPPLIERS,
+    loading,
+    error,
+    refetch
+  } = useRecommendedSuppliers(userAnswers || {});
```

### 4. Gestion du chargement
```typescript
if (loading) {
  return <LoadingState />;
}
```

### 5. Gestion des erreurs
```typescript
if (error) {
  return <ErrorState error={error} onRetry={refetch} />;
}
```

### 6. Reconstruction de ALL_SUPPLIERS
```typescript
const ALL_SUPPLIERS = [...RECOMMENDED_SUPPLIERS, ...OTHER_SUPPLIERS];
```

---

## 🎨 Composants réutilisables (bonus)

Pour rendre le code plus propre, créez des composants pour les états :

### LoadingState.tsx
```typescript
export function LoadingState() {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent" />
        <p className="mt-4 text-muted-foreground">Chargement...</p>
      </div>
    </div>
  );
}
```

### ErrorState.tsx
```typescript
interface ErrorStateProps {
  error: string;
  onRetry?: () => void;
}

export function ErrorState({ error, onRetry }: ErrorStateProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background p-6">
      <div className="max-w-md w-full bg-destructive/10 border border-destructive rounded-lg p-6">
        <h2 className="text-lg font-semibold text-destructive mb-2">
          Erreur de chargement
        </h2>
        <p className="text-sm text-muted-foreground mb-4">{error}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
          >
            Réessayer
          </button>
        )}
      </div>
    </div>
  );
}
```

### Utilisation simplifiée
```typescript
import { LoadingState, ErrorState } from '@/components/shared';

const SupplierSelectionModal = ({ userAnswers }: SupplierSelectionModalProps) => {
  const { recommended, others, loading, error, refetch } = useRecommendedSuppliers(userAnswers || {});

  if (loading) return <LoadingState />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;

  // ... reste du code
};
```

---

## 🧪 Test de la migration

### Test 1 : API disponible
1. Configurer `.env.local` avec une vraie URL d'API
2. Lancer l'app : `npm run dev`
3. Naviguer vers `/selection`
4. ✅ Vérifier que les fournisseurs sont chargés depuis l'API
5. ✅ Vérifier l'affichage du spinner pendant le chargement

### Test 2 : API indisponible
1. Configurer `.env.local` avec une URL invalide : `NEXT_PUBLIC_API_BASE_URL=http://invalid-url`
2. Lancer l'app
3. Naviguer vers `/selection`
4. ✅ Vérifier que les données locales (fallback) sont utilisées
5. ✅ Pas d'erreur critique, l'app continue de fonctionner

### Test 3 : Gestion des erreurs
1. Configurer une URL d'API qui retourne 500
2. Naviguer vers `/selection`
3. ✅ Vérifier l'affichage du message d'erreur
4. ✅ Vérifier que le bouton "Réessayer" fonctionne

---

## 📊 Comparaison performances

| Métrique | Avant (statique) | Après (API) |
|----------|------------------|-------------|
| Taille bundle | +12 KB | +2 KB |
| Temps de chargement initial | 0 ms | 200-500 ms |
| Flexibilité | Aucune | Totale |
| Données à jour | Non | Oui |

**Note :** Les données statiques restent en fallback, donc le bundle inclut toujours les données.

---

## 🚀 Prochaines optimisations

Une fois la migration terminée, envisagez :

1. **Cache avec SWR**
```typescript
import useSWR from 'swr';

const { data, error } = useSWR(
  ['/api/suppliers/recommended', userAnswers],
  ([url, answers]) => fetchRecommendedSuppliers(answers)
);
```

2. **Prefetching**
```typescript
// Précharger les données pendant le questionnaire
useEffect(() => {
  if (currentStep === lastStep - 1) {
    // Précharger les fournisseurs avant la fin
    prefetchRecommendedSuppliers(userAnswers);
  }
}, [currentStep]);
```

3. **Optimistic UI**
```typescript
// Afficher les données immédiatement, corriger si erreur
const [optimisticData, setOptimisticData] = useState(fallbackData);
```

---

## ✅ Checklist finale

Avant de déployer :

- [ ] Hook importé et utilisé correctement
- [ ] État de chargement implémenté
- [ ] Gestion d'erreur implémentée
- [ ] Fallback sur données locales testé
- [ ] Tests avec API réelle effectués
- [ ] Tests avec API indisponible effectués
- [ ] Performance acceptable (< 1s)
- [ ] Pas d'erreur TypeScript
- [ ] Pas d'erreur console
- [ ] UI responsive maintenue

---

**Temps estimé de migration :** 20-30 minutes par composant majeur
