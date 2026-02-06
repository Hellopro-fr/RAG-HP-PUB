'use client';

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useFlowStore } from '@/lib/stores/flow-store';
import { basePath } from '@/lib/utils';
import type { CharacteristicsMap } from '@/types/characteristics';

const getApiBasePath = () => basePath || '';

/**
 * Fetch les caractéristiques depuis l'API et les stocke dans Zustand
 * Appelé une seule fois par catégorie, les données sont ensuite réutilisées partout
 */
async function fetchCharacteristics(categoryId: number): Promise<CharacteristicsMap> {
  const apiBase = getApiBasePath();
  const formData = new FormData();
  formData.append('id_categorie', categoryId.toString());

  const response = await fetch(`${apiBase}/api/caracteristiques`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch characteristics: ${response.status}`);
  }

  const data = await response.json();

  // Transformer le tableau en Map indexée par ID pour accès O(1)
  // L'API peut retourner 'id' ou 'id_caracteristique' pour l'ID de la caractéristique
  // et 'id' ou 'id_valeur' pour l'ID des valeurs
  const characteristicsArray = data.response || [];
  const characteristicsMap: CharacteristicsMap = {};

  for (const char of characteristicsArray) {
    // Récupérer l'ID depuis 'id' ou 'id_caracteristique'
    const charId = Number((char as any).id_caracteristique || char.id);

    if (isNaN(charId)) {
      console.warn('Invalid characteristic ID:', char);
      continue;
    }

    characteristicsMap[charId] = {
      id: charId,
      nom: char.nom,
      unite: char.unite,
      type: char.type,
      valeurs: (char.valeurs || []).map((v: any) => ({
        // Récupérer l'ID depuis 'id' ou 'id_valeur'
        id: Number(v.id_valeur || v.id),
        valeur: v.valeur,
      })),
    };
  }

  return characteristicsMap;
}

/**
 * Hook pour charger et accéder aux caractéristiques
 *
 * @param categoryId - ID de la catégorie (optionnel, utilise celui du store par défaut)
 * @returns { isLoading, isError, characteristicsMap }
 *
 * @example
 * const { isLoading, characteristicsMap } = useCharacteristics();
 * const label = characteristicsMap[176]?.nom; // "Type de pont"
 */
export function useCharacteristics(categoryIdOverride?: number) {
  const { categoryId: storeId, characteristicsMap, setCharacteristicsMap } = useFlowStore();
  const categoryId = categoryIdOverride ?? storeId;

  const hasData = Object.keys(characteristicsMap).length > 0;

  const { data, isLoading, isError } = useQuery({
    queryKey: ['characteristics', categoryId],
    queryFn: () => fetchCharacteristics(categoryId!),
    enabled: !!categoryId && !hasData, // Skip si déjà dans le store
    staleTime: Infinity, // Ne jamais refetch automatiquement
    gcTime: Infinity, // Garder en cache indéfiniment
  });

  // Stocker dans Zustand quand les données arrivent
  useEffect(() => {
    if (data && !hasData) {
      setCharacteristicsMap(data);
    }
  }, [data, hasData, setCharacteristicsMap]);

  return {
    isLoading: isLoading && !hasData,
    isError,
    characteristicsMap: hasData ? characteristicsMap : (data || {}),
  };
}
