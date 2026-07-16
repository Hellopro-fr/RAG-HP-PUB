'use client';

import { useMemo } from 'react';
import SelectionTableViewB from '@/components/flow/selection-views/SelectionTableViewB';
import { useFlowStore } from '@/lib/stores/flow-store';
import { buildProductSpecs, makeDisplaySupplier } from '@/lib/utils/matching-normalizer';
import { consolidateEquivalences } from '@/lib/utils/equivalence-merger';
import { fixBrokenEncoding } from '@/lib/utils/fix-encoding';
import type { Supplier } from '@/types';

// =============================================================================
// FOND DE L'ÉTAPE TRANSPARENCE — tableau final de produits flouté
// =============================================================================
// Réutilise le MÊME composant que le tableau final de /selection
// (SelectionTableViewB) : toute évolution du tableau se répercute
// automatiquement sur ce fond.
//
// Données : 3 vrais produits de la catégorie (nom + photo) récupérés via
// l'endpoint get_photos_categorie (store.categoryPreviewProducts, préfetché
// dès Q1). Les lignes de caractéristiques = les critères de l'utilisateur
// (buildProductSpecs à partir des équivalences du questionnaire), affichées
// comme "matchées" — la source scrapping n'a pas de caractéristiques produit,
// et de toute façon le fond est purement décoratif (flouté + inert).
// =============================================================================

const noop = () => {};
const NB_COLONNES = 3;

export default function TransparenceTableBackground() {
  const categoryPreviewProducts = useFlowStore((s) => s.categoryPreviewProducts);
  const categoryName = useFlowStore((s) => s.categoryName);
  const dynamicEquivalences = useFlowStore((s) => s.dynamicEquivalences);
  const characteristicsMap = useFlowStore((s) => s.characteristicsMap);

  const suppliers = useMemo<Supplier[]>(() => {
    // Specs = critères de l'utilisateur (mêmes libellés que le vrai /selection).
    // matchingCharacteristics vide (pas de matching ici) → buildProductSpecs
    // renvoie les critères avec leur valeur cible ; on force l'état "matché"
    // pour un rendu de teaser cohérent (tout en vert).
    const equivalences = consolidateEquivalences(dynamicEquivalences || {});
    const specs = buildProductSpecs([], characteristicsMap || {}, equivalences)
      .slice(0, 5)
      .map((s) => ({
        ...s,
        value: s.expected || s.value,
        expected: undefined,
        matches: true,
        matchingStatus: 1 as const,
      }));

    // 3 colonnes : vraies photos+noms de la catégorie ; complète si < 3.
    const items = [...(categoryPreviewProducts || [])].slice(0, NB_COLONNES);
    while (items.length < NB_COLONNES) {
      items.push({ nom: categoryName || '', image: '' });
    }

    return items.map((p, i) =>
      makeDisplaySupplier({
        id: `preview-${i}`,
        productName: fixBrokenEncoding(p.nom) || categoryName || 'Produit',
        image: p.image,
        specs,
        supplierName: 'Fournisseur vérifié',
        isCertified: true,
      })
    );
  }, [categoryPreviewProducts, categoryName, dynamicEquivalences, characteristicsMap]);

  const selectedIds = useMemo(
    () => new Set(suppliers.map((s) => s.id)),
    [suppliers]
  );

  return (
    // pointer-events-none + inert + aria-hidden : fond purement décoratif.
    // Indispensable car le tableau contient des boutons interactifs (dont la
    // pagination mobile en position:fixed, repositionnée dans ce conteneur par
    // le filter blur) qui ne doivent être ni cliquables ni tabbables.
    <div
      aria-hidden="true"
      className="absolute inset-0 overflow-hidden pointer-events-none select-none"
      {...({ inert: '' } as Record<string, unknown>)}
    >
      <div className="absolute inset-0 blur-[2.5px] opacity-90 px-4 pt-4 sm:px-6">
        <SelectionTableViewB
          selectedSuppliers={suppliers}
          otherSuppliers={[]}
          selectedIds={selectedIds}
          onToggle={noop}
          onViewDetails={noop}
        />
      </div>
      {/* Voiles pour la lisibilité de la carte au premier plan */}
      <div className="absolute inset-0 bg-background/25" />
      <div className="absolute inset-x-0 top-0 h-[260px] bg-gradient-to-b from-background via-background/70 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-[160px] bg-gradient-to-t from-background/85 to-transparent" />
    </div>
  );
}
