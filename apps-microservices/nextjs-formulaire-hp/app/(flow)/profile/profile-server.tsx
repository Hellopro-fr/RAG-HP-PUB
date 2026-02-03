import { fetchCountries, type Country } from '@/lib/api/services/countries.service';
import ProfileClient from './profile-client';

export default async function ProfileServer() {
  // Récupérer les pays côté serveur
  const response = await fetchCountries();

  let priorityCountries: Country[] = [];
  let otherCountries: Country[] = [];

  if (response.data) {
    priorityCountries = response.data.principal;
    otherCountries = response.data.complet;
  } else {
    // Fallback sur les données locales
    console.warn('Fallback sur données locales de pays');
    priorityCountries = [
      { id: 2, libelle: 'Belgique' },
      { id: 3, libelle: 'Suisse' },
      { id: 4, libelle: 'Luxembourg' },
      { id: 5, libelle: 'Canada' },
      { id: 6, libelle: 'Maroc' },
      { id: 7, libelle: 'Algérie' },
      { id: 8, libelle: 'Tunisie' },
    ];
    otherCountries = [
      { id: 9, libelle: 'Afghanistan' },
      { id: 10, libelle: 'Afrique du Sud' },
      { id: 11, libelle: 'Albanie' },
    ];
  }

  return (
    <ProfileClient
      priorityCountries={priorityCountries}
      otherCountries={otherCountries}
    />
  );
}