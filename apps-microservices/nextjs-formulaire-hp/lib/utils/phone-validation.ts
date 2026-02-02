/**
 * Configuration des pays pour la validation téléphonique
 * Repris du template_tel_top du legacy
 */

export interface PhoneCountryConfig {
  id: number;
  name: string;
  dialCode: string;
  placeholder: string;
  mask: string;
  regex: RegExp;
  minLength: number;
  maxLength: number;
}

export const PHONE_COUNTRIES: Record<string, PhoneCountryConfig> = {
  '+33': {
    id: 1,
    name: 'France',
    dialCode: '+33',
    placeholder: '6 12 34 56 78',
    mask: '# 00 00 00 00',
    regex: /^\d\s\d{2}\s\d{2}\s\d{2}\s\d{2}$/,
    minLength: 9,
    maxLength: 9,
  },
  '+32': {
    id: 4,
    name: 'Belgique',
    dialCode: '+32',
    placeholder: '212 12 34 56',
    mask: '000 00 00 00',
    regex: /^\d{3}\s\d{2}\s\d{2}\s\d{2}$/,
    minLength: 9,
    maxLength: 9,
  },
  '+212': {
    id: 353,
    name: 'Maroc',
    dialCode: '+212',
    placeholder: '6 50 12 34 56',
    mask: '0 00 00 00 00',
    regex: /^\d{1}\s\d{2}\s\d{2}\s\d{2}\s\d{2}$/,
    minLength: 9,
    maxLength: 9,
  },
  '+213': {
    id: 224,
    name: 'Algérie',
    dialCode: '+213',
    placeholder: '0551 23 45 67',
    mask: '0000 00 00 00',
    regex: /^\d{4}\s\d{2}\s\d{2}\s\d{2}$/,
    minLength: 10,
    maxLength: 10,
  },
  '+216': {
    id: 439,
    name: 'Tunisie',
    dialCode: '+216',
    placeholder: '20 123 456',
    mask: '00 000 000',
    regex: /^\d{2}\s\d{3}\s\d{3}$/,
    minLength: 8,
    maxLength: 8,
  },
  '+41': {
    id: 28,
    name: 'Suisse',
    dialCode: '+41',
    placeholder: '78 123 45 67',
    mask: '00 000 00 00',
    regex: /^\d{2}\s\d{3}\s\d{2}\s\d{2}$/,
    minLength: 9,
    maxLength: 9,
  },
  '+1': {
    id: 12,
    name: 'Canada',
    dialCode: '+1',
    placeholder: '506 234 5678',
    mask: '000 000 0000',
    regex: /^\d{3}\s\d{3}\s\d{4}$/,
    minLength: 10,
    maxLength: 10,
  },
  '+225': {
    id: 275,
    name: "Côte d'Ivoire",
    dialCode: '+225',
    placeholder: '01 23 45 67 89',
    mask: '00 00 00 00 00',
    regex: /^\d{2}\s\d{2}\s\d{2}\s\d{2}\s\d{2}$/,
    minLength: 10,
    maxLength: 10,
  },
  '+262': {
    id: 399,
    name: 'Réunion',
    dialCode: '+262',
    placeholder: '692 12 34 56',
    mask: '000 00 00 00',
    regex: /^\d{3}\s\d{2}\s\d{2}\s\d{2}$/,
    minLength: 9,
    maxLength: 9,
  },
  '+237': {
    id: 260,
    name: 'Cameroun',
    dialCode: '+237',
    placeholder: '6 71 23 45 67',
    mask: '0 00 00 00 00',
    regex: /^\d\s\d{2}\s\d{2}\s\d{2}\s\d{2}$/,
    minLength: 9,
    maxLength: 9,
  },
};

/**
 * Liste des pays top (les plus utilisés)
 */
export const TOP_COUNTRIES = ['+33', '+32', '+41', '+212', '+213', '+216'];

/**
 * Vérifier si un pays est dans la liste des pays top
 */
export function isTopCountry(dialCode: string): boolean {
  return TOP_COUNTRIES.includes(dialCode);
}

/**
 * Récupérer la configuration d'un pays par son indicatif
 */
export function getCountryConfig(dialCode: string): PhoneCountryConfig | null {
  return PHONE_COUNTRIES[dialCode] || null;
}

/**
 * Formater un numéro de téléphone selon le masque du pays
 */
export function formatPhoneNumber(phone: string, dialCode: string): string {
  const config = getCountryConfig(dialCode);
  if (!config) return phone;

  // Enlever tous les caractères non numériques
  const cleaned = phone.replace(/\D/g, '');

  // Appliquer le masque
  let formatted = '';
  let digitIndex = 0;

  for (let i = 0; i < config.mask.length && digitIndex < cleaned.length; i++) {
    if (config.mask[i] === '0' || config.mask[i] === '#') {
      formatted += cleaned[digitIndex];
      digitIndex++;
    } else {
      formatted += config.mask[i];
    }
  }

  return formatted;
}

/**
 * Valider un numéro de téléphone selon le pays
 */
export function validatePhoneNumber(phone: string, dialCode: string): {
  isValid: boolean;
  error?: string;
} {
  const config = getCountryConfig(dialCode);

  if (!config) {
    // Validation générique pour pays non supportés
    const cleaned = phone.replace(/\D/g, '');
    const isValid = cleaned.length >= 7 && cleaned.length <= 14;

    return {
      isValid,
      error: isValid ? undefined : 'Numéro de téléphone invalide (7-14 chiffres)',
    };
  }

  // Validation avec regex spécifique au pays
  if (!config.regex.test(phone)) {
    return {
      isValid: false,
      error: `Format invalide. Exemple: ${config.placeholder}`,
    };
  }

  // Validation longueur
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length < config.minLength || cleaned.length > config.maxLength) {
    return {
      isValid: false,
      error: `Le numéro doit contenir ${config.minLength} chiffres`,
    };
  }

  return { isValid: true };
}

/**
 * Forcer un champ à n'accepter que des chiffres et espaces
 */
export function sanitizePhoneInput(value: string): string {
  // Garder uniquement les chiffres et espaces
  return value.replace(/[^\d\s]/g, '');
}

/**
 * Obtenir le numéro complet avec indicatif
 */
export function getFullPhoneNumber(phone: string, dialCode: string): string {
  const cleaned = phone.replace(/\D/g, '');
  return `${dialCode}${cleaned}`;
}

/**
 * Parser un numéro complet pour extraire indicatif et numéro
 */
export function parsePhoneNumber(fullPhone: string): {
  dialCode: string;
  phone: string;
} | null {
  // Chercher le plus long indicatif correspondant
  const sortedDialCodes = Object.keys(PHONE_COUNTRIES).sort((a, b) => b.length - a.length);

  for (const dialCode of sortedDialCodes) {
    if (fullPhone.startsWith(dialCode)) {
      return {
        dialCode,
        phone: fullPhone.substring(dialCode.length),
      };
    }
  }

  return null;
}
