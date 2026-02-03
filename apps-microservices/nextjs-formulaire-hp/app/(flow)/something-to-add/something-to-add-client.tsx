"use client";

import { useFlowNavigation } from '@/hooks/useFlowNavigation';
import SomethingToAddForm from '@/components/flow/SomethingToAddForm';

export default function SomethingToAddClient() {
  const { goToContactSimple, goToChoice } = useFlowNavigation();

  return (
    <SomethingToAddForm
      onNext={goToContactSimple}
      onBack={goToChoice}
    />
  );
}
