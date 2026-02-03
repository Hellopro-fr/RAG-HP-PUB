"use client";

import { useFlowNavigation } from '@/hooks/useFlowNavigation';
import SearchResultChoice from '@/components/flow/SearchResultChoice';

export default function ChoiceClient() {
  const { goToSelection, goToSomethingToAdd } = useFlowNavigation();

  return (
    <SearchResultChoice
      onChooseSelection={goToSelection}
      onChooseSomethingToAdd={goToSomethingToAdd}
    />
  );
}
