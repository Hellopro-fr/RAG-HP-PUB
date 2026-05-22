"use client";

import { useEffect, useRef } from 'react';
import SupplierSelectionModal from '@/components/flow/SupplierSelectionModal';
import { useFlowStore } from '@/lib/stores/flow-store';
import { useFlowNavigation } from '@/hooks/useFlowNavigation';
import { Supplier } from '@/types';
import { getAssetPath } from "@/lib/utils";
import { trackSelectionPageView, setFlowType } from '@/lib/analytics';
import { initDebugMatching } from '@/lib/utils/debug-matching';
import { useDbTracking } from '@/hooks/tracking/useDbTracking';

export default function SelectionClient() {
  const { userAnswers, flowType, setFlowType: setStoreFlowType, categoryId } = useFlowStore();
  const { goToQuestionnaire } = useFlowNavigation();
  const { trackDbEvent } = useDbTracking();
  const hasTrackedView = useRef(false);

  // Initialize debug matching functions (debugInfo, clearDebugInfo)
  useEffect(() => {
    initDebugMatching();
  }, []);

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
      trackSelectionPageView(4, 12);

      // Guard sessionStorage : 1 seul fire DB par session (survit aux remounts).
      // Cle nettoyee au F5 par resetTrackingState() (prefixe hp_viewed_).
      if (typeof window !== 'undefined' && !sessionStorage.getItem('hp_viewed_db_selection_view')) {
        sessionStorage.setItem('hp_viewed_db_selection_view', 'true');
        trackDbEvent('selection', 'selection_view', {}, categoryId, 2);
      }
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
