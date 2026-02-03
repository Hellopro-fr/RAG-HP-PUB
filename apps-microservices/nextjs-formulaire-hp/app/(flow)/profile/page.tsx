import { Suspense } from 'react';
import type { Metadata } from 'next';
import ProfileServer from './profile-server';

export const metadata: Metadata = {
  title: 'Profil - Vos informations',
  description: 'Renseignez vos informations professionnelles pour recevoir des devis personnalisés.',
};

export default function ProfilePage() {
  return (
    <Suspense fallback={null}>
      <ProfileServer />
    </Suspense>
  );
}
