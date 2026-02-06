'use client';

import { useCountries } from '@/hooks/api';

/**
 * Composant invisible qui précharge la liste des pays
 * À inclure dans le layout du flow pour que les données
 * soient prêtes quand l'utilisateur arrive au formulaire de contact
 */
export function CountriesPrefetcher() {
  // Appeler le hook suffit à déclencher le fetch et la mise en cache
  useCountries();

  // Ce composant ne rend rien
  return null;
}
