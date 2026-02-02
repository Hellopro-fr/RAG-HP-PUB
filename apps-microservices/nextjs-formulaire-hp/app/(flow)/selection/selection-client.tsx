"use client";

import { useEffect, useRef } from 'react';
import SupplierSelectionModal from '@/components/flow/SupplierSelectionModal';
import { useFlowStore } from '@/lib/stores/flow-store';
import { useFlowNavigation } from '@/hooks/useFlowNavigation';
import { Supplier } from '@/types';
import { getAssetPath } from "@/lib/utils";
import { trackSelectionPageView, setFlowType } from '@/lib/analytics';

export default function SelectionClient() {
  const { userAnswers, flowType, setFlowType: setStoreFlowType } = useFlowStore();
  const { goToQuestionnaire } = useFlowNavigation();
  const hasTrackedView = useRef(false);

  // Track selection page view au montage et définir flowType = 'principal'
  useEffect(() => {
    if (!hasTrackedView.current) {
      hasTrackedView.current = true;

      // Si le flowType n'est pas déjà défini (premier passage sur sélection)
      // on le définit comme 'principal'
      if (!flowType) {
        setStoreFlowType('principal');
        setFlowType('principal');
      }

      // Valeurs par défaut - seront mises à jour par le composant si nécessaire
      trackSelectionPageView(4, 12); // 4 recommandés, 12 total
    }
  }, [flowType, setStoreFlowType]);

  const handleBackToQuestionnaire = () => {
    // Navigate back to questionnaire (with GET params preserved)
    goToQuestionnaire();
  };

  const { matchingResults } = useFlowStore();

  // if (!matchingResults) {
  //   return <div>Chargement ou redirection...</div>;
  // }

  //tODO changer RECOMMENDED_SUPPLIERS par result matchingResults

  return (
    <SupplierSelectionModal
      userAnswers={userAnswers}
      onBackToQuestionnaire={handleBackToQuestionnaire}
    />
  );
}
