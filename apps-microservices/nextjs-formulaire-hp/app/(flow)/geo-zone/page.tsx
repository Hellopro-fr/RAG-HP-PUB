import { Suspense } from 'react';
import type { Metadata } from 'next';
import GeoZoneServer from './geo-zone-server';

export const metadata: Metadata = {
  title: 'Localisation - Où êtes-vous situé ?',
  description: 'Renseignez votre localisation pour trouver les fournisseurs près de chez vous.',
};

// Force dynamic rendering pour éviter les erreurs de fetch pendant le build statique
export const dynamic = 'force-dynamic';

export default function GeoZonePage() {
  return (
    <Suspense fallback={null}>
      <GeoZoneServer />
    </Suspense>
  );
}
