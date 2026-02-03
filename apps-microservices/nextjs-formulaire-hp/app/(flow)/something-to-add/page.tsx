import { Suspense } from 'react';
import type { Metadata } from 'next';
import SomethingToAddClient from './something-to-add-client';

export const metadata: Metadata = {
  title: 'Précisions - Quelque chose à ajouter ?',
  description: 'Ajoutez des précisions sur votre besoin pour que nous puissions mieux vous aider.',
};

export default function SomethingToAddPage() {
  return (
    <Suspense fallback={null}>
      <SomethingToAddClient />
    </Suspense>
  );
}
