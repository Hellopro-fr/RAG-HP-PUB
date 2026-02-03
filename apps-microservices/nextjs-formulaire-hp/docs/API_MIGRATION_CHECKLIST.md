# Checklist de Migration vers API Dynamique

## 📌 Vue d'ensemble

Ce document liste tous les fichiers et composants à modifier pour passer des données statiques aux données dynamiques via API.

---

## ✅ Infrastructure (TERMINÉ)

- [x] Services API créés (`lib/api/services/`)
  - [x] `questions.service.ts`
  - [x] `suppliers.service.ts`
  - [x] `companies.service.ts`
  - [x] `location.service.ts`
  - [x] `leads.service.ts`

- [x] Client HTTP configuré (`lib/api/client.ts`)
  - [x] Méthodes GET, POST, PUT, DELETE
  - [x] Gestion timeout
  - [x] Gestion erreurs

- [x] Endpoints définis (`lib/api/endpoints.ts`)
  - [x] Questions
  - [x] Suppliers
  - [x] Companies
  - [x] Location
  - [x] Leads
  - [x] Criteria

- [x] Hooks React créés (`hooks/`)
  - [x] `use-questions.ts`
  - [x] `use-suppliers.ts`
  - [x] `index.ts` (barrel export)

- [x] Documentation
  - [x] `docs/API_INTEGRATION.md`
  - [x] `docs/API_MIGRATION_CHECKLIST.md`

---

## 🔄 Composants à migrer

### 1. Questions / Questionnaire

#### `components/flow/NeedsQuestionnaire.tsx`

**État actuel :**
```typescript
import { QUESTIONS_DATA } from '@/data/questions';
const questions = QUESTIONS_DATA;
```

**À modifier :**
```typescript
import { useQuestions } from '@/hooks';

function NeedsQuestionnaire() {
  const { questions, loading, error } = useQuestions();

  if (loading) return <LoadingState />;
  if (error) return <ErrorState error={error} />;

  // Reste du code inchangé
}
```

**Fichiers concernés :**
- `components/flow/NeedsQuestionnaire.tsx`
- `components/flow/QuestionScreen.tsx`

**Estimation :** 15 min

---

### 2. Sélection Fournisseurs

#### `components/flow/SupplierSelectionModal.tsx`

**État actuel :**
```typescript
const RECOMMENDED_SUPPLIERS = [/* données statiques */];
const OTHER_SUPPLIERS = [/* données statiques */];
```

**À modifier :**
```typescript
import { useRecommendedSuppliers } from '@/hooks';
import { useFlowStore } from '@/lib/stores/flow-store';

function SupplierSelectionModal() {
  const { userAnswers } = useFlowStore();
  const { recommended, others, loading, error } = useRecommendedSuppliers(userAnswers);

  if (loading) return <MatchingLoader />;
  if (error) return <ErrorState error={error} />;

  // Utiliser recommended et others au lieu des constantes
}
```

**Modifications requises :**
1. Supprimer les constantes `RECOMMENDED_SUPPLIERS` et `OTHER_SUPPLIERS`
2. Remplacer par `useRecommendedSuppliers(userAnswers)`
3. Ajouter état de chargement
4. Gérer les erreurs

**Fichiers concernés :**
- `components/flow/SupplierSelectionModal.tsx`

**Estimation :** 20 min

---

### 3. Détails Produit

#### `components/flow/ProductDetailModal.tsx`

**État actuel :**
```typescript
// Reçoit directement l'objet product en props
```

**À modifier (optionnel) :**
```typescript
import { useSupplier } from '@/hooks';

function ProductDetailModal({ productId }: { productId: string }) {
  const { supplier, loading, error } = useSupplier(productId);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState error={error} />;
  if (!supplier) return null;

  // Utiliser supplier au lieu de product
}
```

**Note :** Seulement si vous voulez charger les détails à la demande. Sinon, les données sont déjà dans la liste.

**Estimation :** 10 min (optionnel)

---

### 4. Recherche de Fournisseurs

**État actuel :**
```typescript
// Filtrage local dans SupplierSelectionModal
const filtered = suppliers.filter(s =>
  s.productName.toLowerCase().includes(query)
);
```

**À modifier :**
```typescript
import { useSupplierSearch } from '@/hooks';

function SupplierSelectionModal() {
  const { suppliers, loading, error, search } = useSupplierSearch();

  const handleSearch = (query: string) => {
    search(query);
  };

  // Utiliser suppliers du hook au lieu du filtrage local
}
```

**Fichiers concernés :**
- `components/flow/SupplierSelectionModal.tsx` (section recherche)

**Estimation :** 15 min

---

### 5. Formulaire Contact (POST)

#### `components/flow/ContactForm.tsx`

**État actuel :**
```typescript
// Pas d'envoi réel, juste navigation
const handleSubmit = async (data: ContactFormData) => {
  // Simulation
  await new Promise(resolve => setTimeout(resolve, 1000));
  router.push('/confirmation');
};
```

**À modifier :**
```typescript
import { post } from '@/lib/api/client';
import { ENDPOINTS } from '@/lib/api/endpoints';

const handleSubmit = async (data: ContactFormData) => {
  setSubmitting(true);

  const response = await post(ENDPOINTS.leads.submit(), {
    ...data,
    suppliers: selectedSuppliers,
    userAnswers,
  });

  if (response.error) {
    toast.error('Erreur lors de l\'envoi');
    setSubmitting(false);
    return;
  }

  router.push('/confirmation');
};
```

**Fichiers concernés :**
- `components/flow/ContactForm.tsx`
- `components/flow/ContactFormSimple.tsx`

**Estimation :** 20 min

---

## 📋 Résumé des modifications

| Composant | Type de changement | Priorité | Temps estimé |
|-----------|-------------------|----------|--------------|
| NeedsQuestionnaire | GET questions | Haute | 15 min |
| QuestionScreen | GET questions | Haute | 10 min |
| SupplierSelectionModal | GET suppliers recommandés | Haute | 20 min |
| SupplierSearch | GET suppliers search | Moyenne | 15 min |
| ContactForm | POST lead | Haute | 20 min |
| ContactFormSimple | POST lead | Moyenne | 15 min |
| ProductDetailModal | GET supplier by ID | Basse | 10 min |

**Temps total estimé :** ~2 heures

---

## 🎯 Plan d'action recommandé

### Phase 1 : Récupération des données (GET)
1. ✅ Migrer `NeedsQuestionnaire` et `QuestionScreen`
2. ✅ Migrer `SupplierSelectionModal`
3. ✅ Tester le flow complet questionnaire → sélection

### Phase 2 : Envoi des données (POST)
4. ✅ Migrer `ContactForm` et `ContactFormSimple`
5. ✅ Gérer les états de succès/erreur
6. ✅ Tester l'envoi de leads

### Phase 3 : Fonctionnalités avancées
7. ✅ Migrer la recherche de fournisseurs
8. ✅ Ajouter cache avec SWR ou React Query (optionnel)
9. ✅ Optimiser les performances

---

## 🔧 Configuration requise

### Variables d'environnement

Créer `.env.local` :

```env
# URL de l'API backend
NEXT_PUBLIC_API_BASE_URL=https://api.hellopro.fr/v1

# Ou pour le développement local
# NEXT_PUBLIC_API_BASE_URL=http://localhost:3001/api
```

### Backup des données locales

Les données statiques dans `data/` resteront comme **fallback** :
- `data/questions.ts` → Utilisé si API échoue
- `data/suppliers.ts` → Utilisé si API échoue

**Ne pas supprimer ces fichiers** pour garantir que l'app fonctionne offline.

---

## 🧪 Tests recommandés

Après chaque migration :

1. **Test avec API disponible**
   - Vérifier que les données sont chargées depuis l'API
   - Vérifier les états de chargement

2. **Test avec API indisponible**
   - Désactiver l'API (mauvaise URL)
   - Vérifier le fallback sur données locales
   - Vérifier les messages d'erreur

3. **Test de performance**
   - Vérifier les temps de chargement
   - Optimiser si nécessaire avec cache

---

## 📝 Notes de migration

### Patterns à suivre

#### 1. État de chargement
```typescript
if (loading) {
  return <div className="flex items-center justify-center p-8">
    <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
  </div>;
}
```

#### 2. Gestion d'erreur
```typescript
if (error) {
  return <div className="p-4 bg-destructive/10 border border-destructive rounded-lg">
    <p className="text-destructive">Une erreur est survenue : {error}</p>
    <button onClick={refetch} className="mt-2 text-sm underline">
      Réessayer
    </button>
  </div>;
}
```

#### 3. Données vides
```typescript
if (!data || data.length === 0) {
  return <div className="text-center p-8 text-muted-foreground">
    Aucun résultat trouvé
  </div>;
}
```

---

## ✨ Améliorations futures (optionnelles)

1. **Caching avancé avec SWR**
   ```bash
   npm install swr
   ```

2. **Optimistic updates**
   - Mettre à jour l'UI immédiatement
   - Rollback si erreur

3. **Infinite scroll** pour la liste de fournisseurs
   - Charger par pagination
   - Améliorer les performances

4. **Prefetching**
   - Précharger les questions suivantes
   - Précharger les détails produits

---

## 🚀 Commandes utiles

```bash
# Lancer le serveur de développement
npm run dev

# Build pour production
npm run build

# Tester la version de production
npm run start

# Linter
npm run lint
```

---

## 📞 Support

Si vous rencontrez des problèmes :

1. Vérifier la console navigateur pour les erreurs
2. Vérifier les appels réseau dans l'onglet Network
3. Consulter `docs/API_INTEGRATION.md` pour plus de détails
4. Vérifier les types TypeScript

---

**Dernière mise à jour :** 2026-01-18
