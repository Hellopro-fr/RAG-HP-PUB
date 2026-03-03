"use client";

import { useFlowNavigation } from '@/hooks/useFlowNavigation';
import SomethingToAddForm from '@/components/flow/SomethingToAddForm';

export default function SomethingToAddClient() {
  const { goToProfile, goToChoice } = useFlowNavigation();

  return (
    <SomethingToAddForm
      onBack={goToChoice}
      onContactComplete={(isExistingBuyer) => {
        if (isExistingBuyer) {
          // Acheteur connu : le formulaire a déjà soumis le lead et navigue automatiquement
          // Pas besoin d'action supplémentaire ici
        } else {
          // Acheteur inconnu : naviguer vers Profile pour compléter les informations
          goToProfile();
        }
      }}
    />
  );
}
