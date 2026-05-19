import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import type { CategoryTokenUrlData as TokenUrlData } from '@/types/category-token';

// =============================================================================
// CONFIGURATION
// =============================================================================

// Mapping des routes tokenisées vers les routes réelles
const ROUTE_MAPPING: Record<string, string> = {
  '/questionnaire': '/',                    // /questionnaire/TOKEN → / (page d'accueil avec questionnaire)
  '/selection': '/selection',               // /selection/TOKEN → /selection
  '/formulaire': '/contact-simple',         // /formulaire/TOKEN → /contact-simple
  '/something-to-add': '/something-to-add', // /something-to-add/TOKEN → /something-to-add (ne plus rediriger vers /selection)
};

// Routes qui nécessitent un token de catégorie valide
const PROTECTED_ROUTES = Object.keys(ROUTE_MAPPING);

// URL de redirection pour les tokens invalides (page catégorie externe)
// TODO: Remplacer par l'URL de la page catégorie réelle
const INVALID_TOKEN_REDIRECT = process.env.INVALID_TOKEN_REDIRECT_URL || 'https://www.hellopro.fr/404.html';

// =============================================================================
// TOKEN VALIDATION - AES-256-CBC (inline pour éviter les imports dans Edge Runtime)
// =============================================================================

/**
 * Décode un string Base64 URL-safe en Uint8Array
 */
function base64UrlDecodeToBytes(str: string): Uint8Array {
  // Convertir Base64 URL-safe en Base64 standard
  let base64 = str.replace(/-/g, '+').replace(/_/g, '/');
  const padding = base64.length % 4;
  if (padding) {
    base64 += '='.repeat(4 - padding);
  }

  // Décoder Base64 en string binaire puis en bytes
  const binaryStr = atob(base64);
  const bytes = new Uint8Array(binaryStr.length);
  for (let i = 0; i < binaryStr.length; i++) {
    bytes[i] = binaryStr.charCodeAt(i);
  }
  return bytes;
}

/**
 * Vérifie si la date est valide (48 heures max)
 */
function isDateValid(dateStr: string): boolean {
  const tokenDate = new Date(dateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Token valide pendant 48 heures (2 jours)
  const twoDaysAgo = new Date(today);
  twoDaysAgo.setDate(twoDaysAgo.getDate() - 2);

  const maxDate = new Date(today);
  maxDate.setDate(maxDate.getDate() + 1);

  return tokenDate >= twoDaysAgo && tokenDate < maxDate;
}

/**
 * Déchiffre un token AES-256-CBC
 * Format du token: Base64URL(IV[16 bytes] + EncryptedData)
 */
async function validateTokenInMiddleware(
  token: string,
  secret: string
): Promise<{ valid: boolean; categoryId?: number; urlData?: TokenUrlData; error?: string; ddc?: string | undefined }> {
  try {
    // Validation basique du format avant déchiffrement
    if (!token || token.length < 20 || !/^[A-Za-z0-9_-]+$/.test(token)) {
      return { valid: false, error: 'invalid_format' };
    }

    // 1. Décoder le token Base64 URL-safe en bytes
    const encryptedData = base64UrlDecodeToBytes(token);

    // 2. Extraire IV (16 premiers bytes) et données chiffrées
    if (encryptedData.length < 17) {
      return { valid: false, error: 'invalid_format' };
    }
    const iv = encryptedData.slice(0, 16);
    const ciphertext = encryptedData.slice(16);

    // 3. Dériver la clé AES-256 depuis le secret (SHA-256)
    const encoder = new TextEncoder();
    const secretBytes = encoder.encode(secret);
    const keyHash = await crypto.subtle.digest('SHA-256', secretBytes);

    // 4. Importer la clé pour AES-CBC
    const key = await crypto.subtle.importKey(
      'raw',
      keyHash,
      { name: 'AES-CBC' },
      false,
      ['decrypt']
    );

    // 5. Déchiffrer
    const decryptedBuffer = await crypto.subtle.decrypt(
      { name: 'AES-CBC', iv },
      key,
      ciphertext
    );

    // 6. Convertir en string et parser le JSON
    const decoder = new TextDecoder();
    const payloadStr = decoder.decode(decryptedBuffer);
    const payload: {
      ddc_is_v: string | undefined; c: number; d: string; t?: number; data?: TokenUrlData 
    } = JSON.parse(payloadStr);

    // 7. Vérifier la date d'expiration
    if (!payload.d || !isDateValid(payload.d)) {
      return { valid: false, error: 'expired' };
    }

    // 8. Vérifier le categoryId
    if (typeof payload.c !== 'number' || payload.c <= 0) {
      return { valid: false, error: 'invalid_payload' };
    }

    // 9. Extraire les données URL optionnelles (réponse Q1 pré-remplie)
    const urlData = payload.data && payload.data.id_reponse ? payload.data : undefined;

    return { valid: true, categoryId: payload.c, urlData, ddc: payload.ddc_is_v };
  } catch (error) {
    // Erreur de déchiffrement = token invalide
    // DOMException n'est pas bien sérialisée, extraire les infos utiles
    const errorInfo = error instanceof Error
      ? { name: error.name, message: error.message }
      : { type: typeof error, value: String(error) };

    console.error('[Middleware] Token validation error:', errorInfo);
    return { valid: false, error: 'invalid_token' };
  }
}

// =============================================================================
// MIDDLEWARE
// =============================================================================

export async function middleware(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;

  // TODO: SUPPRIMER AVANT MISE EN PROD - Bypass pour tests avec ?id_categorie=123
  const devCategoryId = searchParams.get('id_categorie');
  if (devCategoryId) {
    // En mode dev, réécrire vers la route réelle correspondante
    const routePrefix = '/' + pathname.split('/').filter(Boolean)[0];
    const targetRoute = ROUTE_MAPPING[routePrefix] || '/';

    const rewriteUrl = request.nextUrl.clone();
    rewriteUrl.pathname = targetRoute;
    // Garder id_categorie pour que les pages puissent l'utiliser
    return NextResponse.rewrite(rewriteUrl);
  }

  // TODO: SUPPRIMER AVANT MISE EN PROD - Bypass complet en dev pour navigation interne
  // Laisser passer les requêtes RSC (React Server Components) et navigation interne
  const isRscRequest = searchParams.has('_rsc');
  const hasNoToken = pathname.split('/').filter(Boolean).length === 1; // ex: /selection sans token
  if (isRscRequest || hasNoToken) {
    return NextResponse.next();
  }

  // Vérifier si la route est protégée
  const isProtectedRoute = PROTECTED_ROUTES.some((route) =>
    pathname.startsWith(route)
  );

  if (!isProtectedRoute) {
    return NextResponse.next();
  }

  // Extraire le token du path (ex: /questionnaire/abc123 → abc123)
  const pathParts = pathname.split('/').filter(Boolean);

  // Si pas de token dans l'URL, rediriger vers page catégorie
  if (pathParts.length < 2) {
    return NextResponse.redirect(INVALID_TOKEN_REDIRECT);
  }

  const token = pathParts[1];
  const secret = process.env.CATEGORY_TOKEN_SECRET || '';

  // Valider le token
  const result = await validateTokenInMiddleware(token, secret);

  if (!result.valid) {
    // Token invalide/expiré → rediriger vers page catégorie
    return NextResponse.redirect(INVALID_TOKEN_REDIRECT);
  }

  console.log('[Middleware] 🔓 Données décryptées du token:', {
    categoryId: result.categoryId,
    ddc: result.ddc,
    urlData: result.urlData,
  });

  // Token valide - réécrire vers la route réelle
  const routePrefix = '/' + pathParts[0]; // ex: /questionnaire
  const targetRoute = ROUTE_MAPPING[routePrefix] || '/';

  // Créer l'URL de réécriture avec categoryId en query param
  // On clone l'URL originale et on modifie le pathname
  const rewriteUrl = request.nextUrl.clone();
  rewriteUrl.pathname = targetRoute;
  rewriteUrl.searchParams.set('categoryId', String(result.categoryId));
  rewriteUrl.searchParams.set('token', token);
  if (result.ddc) {
    rewriteUrl.searchParams.set('ddc', result.ddc);
  }

  // Ajouter les données URL si présentes (réponse Q1 pré-remplie)
  if (result.urlData) {
    // Encoder en Base64 URL-safe pour passer dans le query param
    const urlDataJson = JSON.stringify(result.urlData);
    const urlDataBase64 = btoa(urlDataJson)
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=/g, '');
    rewriteUrl.searchParams.set('urlData', urlDataBase64);
  }

  // Réécrire vers la route cible (l'URL dans le navigateur ne change pas)
  return NextResponse.rewrite(rewriteUrl);
}

// =============================================================================
// MATCHER - Appliquer uniquement sur les routes protégées
// =============================================================================

export const config = {
  matcher: [
    '/questionnaire/:token*',
    '/selection/:token*',
    '/formulaire/:token*',
    '/something-to-add/:token*',
  ],
};
