import { Suspense } from 'react';
import type { Metadata } from 'next';
import ProfileServer from './profile-server';

// Force dynamic rendering - skip static generation at build time
// This avoids fetch errors when the API is not available during build
export const dynamic = 'force-dynamic';

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
