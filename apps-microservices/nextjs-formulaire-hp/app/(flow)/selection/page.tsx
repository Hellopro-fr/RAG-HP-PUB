import { Suspense } from 'react';
import type { Metadata } from 'next';
import SelectionClient from './selection-client';

export const metadata: Metadata = {
  title: 'Sélection - Choisissez vos fournisseurs',
  description: 'Parcourez et sélectionnez les fournisseurs qui correspondent à vos besoins.',
};

export default function SelectionPage() {
  return (
    <Suspense fallback={null}>
      <SelectionClient />
    </Suspense>
  );
}
