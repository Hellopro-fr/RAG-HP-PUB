import { Suspense } from 'react';
import type { Metadata } from 'next';
import ContactSimpleClient from './contact-simple-client';

export const metadata: Metadata = {
  title: 'Contact - Vos coordonnées',
  description: 'Laissez-nous vos coordonnées pour que nous puissions vous recontacter.',
};

export default function ContactSimplePage() {
  return (
    <Suspense fallback={null}>
      <ContactSimpleClient />
    </Suspense>
  );
}
