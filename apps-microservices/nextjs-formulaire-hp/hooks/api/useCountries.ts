'use client';

import { useQuery } from '@tanstack/react-query';
import { basePath } from '@/lib/utils';

const getApiBasePath = () => basePath || '';

// Type de réponse de l'API PHP
interface CountryApiItem {
  id_pays: string;
  indicatif: string;
  nom_pays: string;
  active_?: string;
  pays_drapeau?: string;
}

interface CountryApiResponse {
  success: boolean;
  data: CountryApiItem[];
}

// Convertit un code ISO 2 lettres en emoji drapeau
// "fr" → 🇫🇷, "be" → 🇧🇪
function isoToFlag(isoCode: string): string {
  if (!isoCode || isoCode.length !== 2) return '';
  return isoCode
    .toUpperCase()
    .split('')
    .map(char => String.fromCodePoint(0x1F1E6 + char.charCodeAt(0) - 65))
    .join('');
}

// Fonction pour décoder les entités HTML
function decodeHtmlEntities(text: string): string {
  const textarea = typeof document !== 'undefined' ? document.createElement('textarea') : null;
  if (textarea) {
    textarea.innerHTML = text;
    return textarea.value;
  }
  // Fallback pour SSR
  return text
    .replace(/&eacute;/g, 'é')
    .replace(/&egrave;/g, 'è')
    .replace(/&agrave;/g, 'à')
    .replace(/&ocirc;/g, 'ô')
    .replace(/&icirc;/g, 'î')
    .replace(/&ucirc;/g, 'û')
    .replace(/&ccedil;/g, 'ç')
    .replace(/&amp;/g, '&');
}

// Type utilisé dans l'application
export interface Country {
  id: number;        // id_pays
  code: string;      // indicatif avec "+"
  country: string;   // nom_pays
  flag: string;      // emoji drapeau
}

// Mapping des indicatifs vers les emojis drapeaux
const FLAG_BY_CODE: Record<string, string> = {
  "+93": "🇦🇫", "+355": "🇦🇱", "+213": "🇩🇿", "+376": "🇦🇩", "+244": "🇦🇴",
  "+54": "🇦🇷", "+374": "🇦🇲", "+61": "🇦🇺", "+43": "🇦🇹", "+994": "🇦🇿",
  "+973": "🇧🇭", "+880": "🇧🇩", "+32": "🇧🇪", "+229": "🇧🇯", "+975": "🇧🇹",
  "+591": "🇧🇴", "+387": "🇧🇦", "+267": "🇧🇼", "+55": "🇧🇷", "+359": "🇧🇬",
  "+226": "🇧🇫", "+257": "🇧🇮", "+855": "🇰🇭", "+237": "🇨🇲", "+1": "🇺🇸",
  "+238": "🇨🇻", "+236": "🇨🇫", "+56": "🇨🇱", "+86": "🇨🇳", "+357": "🇨🇾",
  "+57": "🇨🇴", "+269": "🇰🇲", "+242": "🇨🇬", "+243": "🇨🇩", "+82": "🇰🇷",
  "+225": "🇨🇮", "+385": "🇭🇷", "+53": "🇨🇺", "+45": "🇩🇰", "+253": "🇩🇯",
  "+20": "🇪🇬", "+971": "🇦🇪", "+593": "🇪🇨", "+34": "🇪🇸", "+372": "🇪🇪",
  "+251": "🇪🇹", "+358": "🇫🇮", "+33": "🇫🇷", "+241": "🇬🇦", "+220": "🇬🇲",
  "+995": "🇬🇪", "+233": "🇬🇭", "+30": "🇬🇷", "+502": "🇬🇹", "+224": "🇬🇳",
  "+509": "🇭🇹", "+504": "🇭🇳", "+852": "🇭🇰", "+36": "🇭🇺", "+91": "🇮🇳",
  "+62": "🇮🇩", "+98": "🇮🇷", "+964": "🇮🇶", "+353": "🇮🇪", "+354": "🇮🇸",
  "+972": "🇮🇱", "+39": "🇮🇹", "+81": "🇯🇵", "+962": "🇯🇴", "+7": "🇷🇺",
  "+254": "🇰🇪", "+965": "🇰🇼", "+996": "🇰🇬", "+856": "🇱🇦", "+371": "🇱🇻",
  "+961": "🇱🇧", "+218": "🇱🇾", "+423": "🇱🇮", "+370": "🇱🇹", "+352": "🇱🇺",
  "+853": "🇲🇴", "+389": "🇲🇰", "+261": "🇲🇬", "+60": "🇲🇾", "+960": "🇲🇻",
  "+223": "🇲🇱", "+356": "🇲🇹", "+212": "🇲🇦", "+230": "🇲🇺", "+222": "🇲🇷",
  "+52": "🇲🇽", "+373": "🇲🇩", "+377": "🇲🇨", "+976": "🇲🇳", "+382": "🇲🇪",
  "+258": "🇲🇿", "+95": "🇲🇲", "+264": "🇳🇦", "+977": "🇳🇵", "+505": "🇳🇮",
  "+227": "🇳🇪", "+234": "🇳🇬", "+47": "🇳🇴", "+64": "🇳🇿", "+968": "🇴🇲",
  "+256": "🇺🇬", "+998": "🇺🇿", "+92": "🇵🇰", "+970": "🇵🇸", "+507": "🇵🇦",
  "+595": "🇵🇾", "+31": "🇳🇱", "+51": "🇵🇪", "+63": "🇵🇭", "+48": "🇵🇱",
  "+351": "🇵🇹", "+974": "🇶🇦", "+40": "🇷🇴", "+44": "🇬🇧", "+250": "🇷🇼",
  "+221": "🇸🇳", "+381": "🇷🇸", "+65": "🇸🇬", "+421": "🇸🇰", "+386": "🇸🇮",
  "+252": "🇸🇴", "+249": "🇸🇩", "+94": "🇱🇰", "+46": "🇸🇪", "+41": "🇨🇭",
  "+963": "🇸🇾", "+886": "🇹🇼", "+992": "🇹🇯", "+255": "🇹🇿", "+235": "🇹🇩",
  "+420": "🇨🇿", "+66": "🇹🇭", "+228": "🇹🇬", "+216": "🇹🇳", "+993": "🇹🇲",
  "+90": "🇹🇷", "+380": "🇺🇦", "+598": "🇺🇾", "+58": "🇻🇪", "+84": "🇻🇳",
  "+967": "🇾🇪", "+260": "🇿🇲", "+263": "🇿🇼",
};

// Pays par défaut (France)
const DEFAULT_COUNTRY: Country = {
  id: 1,
  code: "+33",
  country: "France",
  flag: "🇫🇷",
};

// Fallback statique si l'API échoue
const FALLBACK_COUNTRIES: Country[] = [
  { id: 1, code: "+33", country: "France", flag: "🇫🇷" },
  { id: 2, code: "+32", country: "Belgique", flag: "🇧🇪" },
  { id: 3, code: "+41", country: "Suisse", flag: "🇨🇭" },
  { id: 4, code: "+352", country: "Luxembourg", flag: "🇱🇺" },
  { id: 5, code: "+44", country: "Royaume-Uni", flag: "🇬🇧" },
  { id: 6, code: "+49", country: "Allemagne", flag: "🇩🇪" },
  { id: 7, code: "+34", country: "Espagne", flag: "🇪🇸" },
  { id: 8, code: "+39", country: "Italie", flag: "🇮🇹" },
];

async function fetchCountries(): Promise<Country[]> {
  const apiBase = getApiBasePath();
  const response = await fetch(`${apiBase}/api/geo?t=3`);

  if (!response.ok) {
    throw new Error('Failed to fetch countries');
  }

  const json: CountryApiResponse = await response.json();

  if (!json.success || !json.data) {
    throw new Error('Invalid API response');
  }

  // Transformer la réponse API en format Country
  return json.data.map((item) => {
    const indicatif = item.indicatif.startsWith('+') ? item.indicatif : `+${item.indicatif}`;
    // Priorité : pays_drapeau (ISO) → FLAG_BY_CODE → drapeau par défaut
    const flag = (item.pays_drapeau && isoToFlag(item.pays_drapeau))
      || FLAG_BY_CODE[indicatif]
      || "🏳️";
    return {
      id: parseInt(item.id_pays, 10),
      code: indicatif,
      country: decodeHtmlEntities(item.nom_pays),
      flag,
    };
  });
}

export function useCountries() {
  return useQuery({
    queryKey: ['countries'],
    queryFn: fetchCountries,
    staleTime: 1000 * 60 * 60, // 1 heure
    gcTime: 1000 * 60 * 60 * 24, // 24 heures
    placeholderData: FALLBACK_COUNTRIES,
  });
}

export function getDefaultCountry(): Country {
  return DEFAULT_COUNTRY;
}

export function findCountryByCode(countries: Country[], code: string): Country | undefined {
  return countries.find((c) => c.code === code);
}

export function findCountryById(countries: Country[], id: number): Country | undefined {
  return countries.find((c) => c.id === id);
}
