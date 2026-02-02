import { createCipheriv, createDecipheriv, createHash, randomBytes } from 'crypto';

// =============================================================================
// CONFIGURATION
// =============================================================================

const TOKEN_SECRET = process.env.CATEGORY_TOKEN_SECRET || '';

// =============================================================================
// TYPES
// =============================================================================

interface TokenPayload {
  c: number;    // id_categorie
  d: string;    // date (YYYY-MM-DD)
  t: number;    // timestamp (pour unicité supplémentaire)
}

interface TokenValidationResult {
  valid: boolean;
  categoryId?: number;
  error?: 'invalid_format' | 'invalid_token' | 'expired' | 'invalid_payload';
}

// =============================================================================
// HELPERS
// =============================================================================

/**
 * Dérive une clé AES-256 (32 bytes) depuis le secret via SHA-256
 */
function deriveKey(secret: string): Buffer {
  return createHash('sha256').update(secret).digest();
}

/**
 * Encode en Base64 URL-safe (sans padding)
 */
function base64UrlEncode(data: Buffer): string {
  return data
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

/**
 * Décode depuis Base64 URL-safe
 */
function base64UrlDecode(str: string): Buffer {
  // Restaurer les caractères Base64 standard
  let base64 = str.replace(/-/g, '+').replace(/_/g, '/');

  // Ajouter le padding si nécessaire
  const padding = base64.length % 4;
  if (padding) {
    base64 += '='.repeat(4 - padding);
  }

  return Buffer.from(base64, 'base64');
}

/**
 * Obtient la date du jour au format YYYY-MM-DD
 */
function getTodayDate(): string {
  return new Date().toISOString().split('T')[0];
}

/**
 * Vérifie si une date est valide (aujourd'hui ou hier)
 */
function isDateValid(dateStr: string): boolean {
  const tokenDate = new Date(dateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  const maxDate = new Date(today);
  maxDate.setDate(maxDate.getDate() + 1); // Fin de journée

  return tokenDate >= yesterday && tokenDate < maxDate;
}

// =============================================================================
// PUBLIC API
// =============================================================================

/**
 * Génère un token sécurisé chiffré pour une catégorie
 * Utilise AES-256-CBC avec IV aléatoire
 * Le token est différent à chaque génération grâce à l'IV aléatoire
 *
 * @param categoryId - L'ID de la catégorie à encoder
 * @returns Le token URL-safe (complètement différent à chaque appel)
 *
 * @example
 * const token = generateCategoryToken(123);
 * // → "xYz...différent à chaque appel"
 */
export function generateCategoryToken(categoryId: number): string {
  const payload: TokenPayload = {
    c: categoryId,
    d: getTodayDate(),
    t: Date.now(),
  };

  if (!TOKEN_SECRET) {
    throw new Error('CATEGORY_TOKEN_SECRET is not configured');
  }

  const payloadStr = JSON.stringify(payload);
  const key = deriveKey(TOKEN_SECRET);

  // IV aléatoire de 16 bytes
  const iv = randomBytes(16);

  // Chiffrer avec AES-256-CBC
  const cipher = createCipheriv('aes-256-cbc', key, iv);
  const encrypted = Buffer.concat([
    cipher.update(payloadStr, 'utf-8'),
    cipher.final()
  ]);

  // Concaténer IV + données chiffrées et encoder en Base64 URL-safe
  const combined = Buffer.concat([iv, encrypted]);
  return base64UrlEncode(combined);
}

/**
 * Valide un token et extrait l'ID de catégorie
 *
 * @param token - Le token à valider
 * @returns Résultat de validation avec categoryId si valide
 *
 * @example
 * const result = validateCategoryToken("xYz...");
 * if (result.valid) {
 *   console.log(result.categoryId); // 123
 * }
 */
export function validateCategoryToken(token: string): TokenValidationResult {
  try {
    // Décoder le token
    const data = base64UrlDecode(token);

    // Vérifier la longueur minimale (16 bytes IV + au moins 16 bytes de données)
    if (data.length < 32) {
      return { valid: false, error: 'invalid_format' };
    }

    // Extraire IV et données chiffrées
    const iv = data.subarray(0, 16);
    const encrypted = data.subarray(16);

    // Déchiffrer
    if (!TOKEN_SECRET) {
      return { valid: false, error: 'invalid_token' as const };
    }
    const key = deriveKey(TOKEN_SECRET);
    const decipher = createDecipheriv('aes-256-cbc', key, iv);
    const decrypted = Buffer.concat([
      decipher.update(encrypted),
      decipher.final()
    ]);

    // Parser le payload JSON
    const payload: TokenPayload = JSON.parse(decrypted.toString('utf-8'));

    // Vérifier la validité de la date (aujourd'hui ou hier)
    if (!payload.d || !isDateValid(payload.d)) {
      return { valid: false, error: 'expired' };
    }

    // Vérifier que categoryId est un nombre valide
    if (typeof payload.c !== 'number' || payload.c <= 0) {
      return { valid: false, error: 'invalid_payload' };
    }

    return {
      valid: true,
      categoryId: payload.c,
    };
  } catch {
    return { valid: false, error: 'invalid_token' };
  }
}

/**
 * Extrait l'ID de catégorie d'un token sans validation complète
 * Utile pour le logging/debug uniquement
 */
export function extractCategoryIdUnsafe(token: string): number | null {
  try {
    const result = validateCategoryToken(token);
    return result.valid ? result.categoryId ?? null : null;
  } catch {
    return null;
  }
}
