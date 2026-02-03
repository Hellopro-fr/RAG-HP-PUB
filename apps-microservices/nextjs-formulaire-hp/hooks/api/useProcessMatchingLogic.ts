import { useState } from 'react';
import { useFlowStore } from '@/lib/stores/flow-store';
import { consolidateEquivalences } from '@/lib/utils/equivalence-merger';
import type { ProfileData } from '@/types';
import { fetchSuppliers } from '@/lib/api/services/suppliers.service';
import { useQuery } from '@tanstack/react-query';

import { basePath } from '@/lib/utils';

// Toujours utiliser le proxy Next.js pour éviter les problèmes CORS
const getApiBasePath = () => {
  return basePath || '';
};

function normalizeSupplier(SupplierData: any) {
  return {};
}

const type_typologie = {
  "pro_france": "1",
  "pro_foreign": "2",
  "particulier": "3",
  "creation": "4",
};

export function useProcessMatchingLogic() {
  const [showLoader, setShowLoader] = useState(false);
  const {
    categoryId,
    profileData,
    dynamicEquivalences, 
    setEquivalenceCaracteristique, 
    setMatchingResults
  } = useFlowStore();

  /**
   * Logique de consolidation des équivalences :
   * 1. Collecter toutes les équivalences avec poids_question
   * 2. Regrouper par id_caracteristique
   * 3. Poids final : critique > secondaire, puis poids_question le plus élevé
   * 4. Fusionner valeurs cibles / bloquantes
   */
  const processEquivalences = () => {
    return consolidateEquivalences(dynamicEquivalences);
  };

  /**
   * Action principale de soumission
   */
  const submitProfile = async (data: ProfileData) => {
    const consolidatedEquivalences = processEquivalences();
    setEquivalenceCaracteristique(consolidatedEquivalences);

    setShowLoader(true);

    try {

      const typologie = profileData?.type;
      const typologieValue = type_typologie[typologie as keyof typeof type_typologie] || "1";

      const metadonnee_utilisateurs = {
          "pays":  profileData?.country || '',
          "typologie": typologieValue
      } ;

      const formData = new FormData();
      formData.append('id_categorie', categoryId?.toString() || '');
      formData.append('top_k', '12');
      formData.append('metadonnee_utilisateurs', JSON.stringify(metadonnee_utilisateurs));
      formData.append('liste_caracteristique', JSON.stringify(consolidatedEquivalences));

      const apiBase = getApiBasePath();
      const apiUrl = `${apiBase}/api/matching`;
      
      const res = await fetch(apiUrl, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) throw new Error('Failed to fetch Q1');

      let apiData = await res.json();
      apiData = apiData.response;

      const dataReturn = {
        entryQuestion: normalizeSupplier(apiData),
      };

      //TODO
      //setMatchingResults

    } catch (error) {
      console.error('Matching process error:', error);
    }
  
  };

  return {
    showLoader,
    submitProfile,
  };
}
