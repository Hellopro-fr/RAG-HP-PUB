"use client";

import { useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import NeedsQuestionnaire from '@/components/flow/NeedsQuestionnaire';
import { useFlowStore } from '@/lib/stores/flow-store';
import { useFlowNavigation } from '@/hooks/useFlowNavigation';

interface QuestionnaireClientProps {
  initialCategoryId?: string;
  initialToken?: string;
}

export default function QuestionnaireClient({
  initialCategoryId,
  initialToken
}: QuestionnaireClientProps) {
  const searchParams = useSearchParams();
  const { setCategoryId } = useFlowStore();
  const { goToProfile } = useFlowNavigation();

  // Récupérer et stocker le categoryId
  // Priorité : props du Server Component > searchParams client
  useEffect(() => {
    let categoryId = initialCategoryId;

    // Fallback: searchParams côté client (pour navigation interne)
    if (!categoryId) {
      categoryId = searchParams.get('categoryId') || searchParams.get('id_categorie') || undefined;
    }

    if (categoryId) {
      const id = parseInt(categoryId, 10);
      if (!isNaN(id) && id > 0) {
        setCategoryId(id);
      }
      
      /* const currentFullUrl = `${pathname}?${searchParams.toString()}`;
      setEntryUrl(currentFullUrl); */
    }
  }, [initialCategoryId, searchParams, setCategoryId]);

  const handleComplete = (answers: Record<number, string[]>) => {
    // Navigate to profile step with GET params preserved
    goToProfile();
  };

  return (
    <NeedsQuestionnaire
      onComplete={handleComplete}
      rubriqueId={initialCategoryId}
    />
  );
}
