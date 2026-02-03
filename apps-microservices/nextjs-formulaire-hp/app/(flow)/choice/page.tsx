import { Suspense } from 'react';
import type { Metadata } from 'next';
import ChoiceClient from './choice-client';

export const metadata: Metadata = {
  title: 'Choix - Que souhaitez-vous faire ?',
  description: 'Choisissez entre parcourir les résultats ou nous faire part d\'un besoin spécifique.',
};

export default function ChoicePage() {
  return (
    <Suspense fallback={null}>
      <ChoiceClient />
    </Suspense>
  );
}
