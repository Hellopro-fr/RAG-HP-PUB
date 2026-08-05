'use client';

import type { CSSProperties } from 'react';
import 'react-international-phone/style.css';
import { PhoneInput, defaultCountries } from 'react-international-phone';

/**
 * Neutralise les bordures et fonds INTERNES que la lib pose via ses propres
 * variables CSS (sur le sélecteur, l'input et la pastille d'indicatif « +33 »).
 * Résultat : une seule bordure, celle du conteneur — plus de « couture ».
 */
const PHONE_CSS_VARS = {
  '--react-international-phone-border-color': 'transparent',
  '--react-international-phone-background-color': 'transparent',
  '--react-international-phone-font-size': '0.875rem',
} as CSSProperties;

/**
 * Champ téléphone international (indicatif pays + numéro), basé sur
 * `react-international-phone`. Isolé dans ce wrapper pour :
 *  - contenir l'import CSS de la lib et sa configuration au même endroit ;
 *  - permettre aux tests de le mocker sans charger la lib ni son CSS.
 *
 * `onChange` remonte : le numéro complet (E.164, ex. `+33612345678`), le NOM du
 * pays sélectionné (→ `coordonnees.adresse`, le serveur en déduit le pays), et
 * son indicatif (→ pour distinguer « numéro national saisi » de « juste l'indicatif »).
 */

// La lib fournit les noms de pays en anglais : on francise les plus probables
// (le reste garde l'anglais — rare pour ces leads).
const FRENCH_NAMES: Record<string, string> = {
  be: 'Belgique',
  ma: 'Maroc',
  dz: 'Algérie',
  tn: 'Tunisie',
  ch: 'Suisse',
  lu: 'Luxembourg',
  ca: 'Canada',
  sn: 'Sénégal',
  ci: "Côte d'Ivoire",
  cm: 'Cameroun',
  es: 'Espagne',
  it: 'Italie',
  de: 'Allemagne',
  gb: 'Royaume-Uni',
  us: 'États-Unis',
};

const countries = defaultCountries.map((country) => {
  const iso2 = country[1];
  const fr = FRENCH_NAMES[iso2];
  return fr ? [fr, ...country.slice(1)] : country;
}) as typeof defaultCountries;

export function PhoneField({
  value,
  onChange,
  ariaLabel,
}: {
  value: string;
  onChange: (phone: string, countryName: string, dialCode: string) => void;
  ariaLabel: string;
}) {
  return (
    <PhoneInput
      defaultCountry="fr"
      value={value}
      onChange={(phone, meta) => onChange(phone, meta.country.name, meta.country.dialCode)}
      countries={countries}
      preferredCountries={['fr', 'be', 'ma', 'dz', 'ch', 'lu']}
      // Indicatif ISOLÉ dans le sélecteur : pas dans l'input, donc non modifiable
      // à la main (il ne change qu'en changeant de pays). La valeur remontée par
      // `onChange` reste le numéro complet E.164 (indicatif inclus).
      disableDialCodeAndPrefix
      showDisabledDialCodeAndPrefix
      style={PHONE_CSS_VARS}
      placeholder={ariaLabel}
      inputProps={{ 'aria-label': ariaLabel }}
      // UNE seule boîte : la bordure/arrondi/fond sont sur le conteneur ; le
      // sélecteur pays et l'input sont transparents et sans bordure interne (pas
      // de « couture »). Le focus orange s'applique à tout l'ensemble.
      className="!flex !w-full !items-center !rounded-xl !border !border-border !bg-surface focus-within:!border-cta focus-within:!ring-2 focus-within:!ring-cta/20"
      inputClassName="!h-12 !w-full !border-0 !bg-transparent !text-sm !text-foreground !outline-none focus:!ring-0"
      countrySelectorStyleProps={{
        buttonClassName: '!h-12 !rounded-l-xl !border-0 !bg-transparent !pl-3 !pr-1',
        // Le dropdown hérite du fond transparent du conteneur (var CSS) : on lui
        // redonne un fond solide (`!important` bat la variable héritée).
        dropdownStyleProps: {
          className: '!bg-card !border !border-border !shadow-elegant',
          listItemClassName: '!bg-card hover:!bg-muted',
        },
      }}
    />
  );
}
