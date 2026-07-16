'use client';

import SelectionTableViewB from '@/components/flow/selection-views/SelectionTableViewB';
import { RECOMMENDED_SUPPLIERS_DATA } from '@/data/suppliers';

// =============================================================================
// FOND DE L'ÉTAPE TRANSPARENCE — tableau final de produits flouté
// =============================================================================
// Réutilise le MÊME composant que le tableau final de /selection
// (SelectionTableViewB) : toute évolution du tableau se répercute
// automatiquement sur ce fond.
//
// Données statiques pour l'instant (mocks pont élévateur de data/suppliers.ts).
// Pour passer aux vraies données plus tard : remplacer les deux constantes
// ci-dessous par matchingResults.recommended / matchingResults.others du store.
// =============================================================================

// Références stables au niveau module (pas de re-render inutile).
// 3 produits seulement, comme la maquette.
const BACKGROUND_SUPPLIERS = RECOMMENDED_SUPPLIERS_DATA.slice(0, 3);
const STATIC_SELECTED_IDS = new Set(BACKGROUND_SUPPLIERS.map((s) => s.id));
const noop = () => {};

export default function TransparenceTableBackground() {
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
          selectedSuppliers={BACKGROUND_SUPPLIERS}
          otherSuppliers={[]}
          selectedIds={STATIC_SELECTED_IDS}
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
