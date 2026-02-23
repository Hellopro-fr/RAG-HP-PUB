// ========================================
// RATE LIMITING - Protection contre les abus
// In-memory, sans dépendance externe
// ========================================

// IPs whitelistées (exclues du rate limiting)
const WHITELISTED_IPS = new Set([
  '129.222.108.162',
  '102.17.192.102',
]);

interface RateLimitRecord {
  count: number;
  resetTime: number;
}

// Store en mémoire (reset au redémarrage du serveur)
const rateLimitStore = new Map<string, RateLimitRecord>();

// Nettoyage périodique des entrées expirées (toutes les 5 minutes)
if (typeof setInterval !== 'undefined') {
  setInterval(() => {
    const now = Date.now();
    for (const [key, record] of rateLimitStore.entries()) {
      if (now > record.resetTime) {
        rateLimitStore.delete(key);
      }
    }
  }, 5 * 60 * 1000);
}

export interface RateLimitResult {
  success: boolean;
  limit: number;
  remaining: number;
  resetIn?: number; // ms avant reset
}

/**
 * Vérifie et applique le rate limiting pour une IP donnée
 *
 * @param identifier - IP ou identifiant unique (ex: email hash)
 * @param limit - Nombre max de requêtes autorisées
 * @param windowMs - Fenêtre de temps en millisecondes (défaut: 60000 = 1 minute)
 * @returns Résultat avec success, remaining, etc.
 *
 * @example
 * const { success, remaining } = rateLimit(ip, 10, 60000); // 10 req/min
 * if (!success) return Response 429
 */
export function rateLimit(
  identifier: string,
  limit: number = 10,
  windowMs: number = 60000
): RateLimitResult {
  // Bypass pour IPs whitelistées
  if (WHITELISTED_IPS.has(identifier)) {
    return { success: true, limit, remaining: limit };
  }

  const now = Date.now();
  const record = rateLimitStore.get(identifier);

  // Si l'enregistrement existe mais est expiré, le supprimer
  if (record && now > record.resetTime) {
    rateLimitStore.delete(identifier);
  }

  const current = rateLimitStore.get(identifier);

  if (!current) {
    // Première requête pour cet identifiant
    rateLimitStore.set(identifier, {
      count: 1,
      resetTime: now + windowMs,
    });
    return {
      success: true,
      limit,
      remaining: limit - 1,
    };
  }

  if (current.count >= limit) {
    // Limite atteinte
    return {
      success: false,
      limit,
      remaining: 0,
      resetIn: current.resetTime - now,
    };
  }

  // Incrémenter le compteur
  current.count++;
  return {
    success: true,
    limit,
    remaining: limit - current.count,
  };
}

/**
 * Configurations prédéfinies pour différents endpoints
 */
export const RATE_LIMITS = {
  // Vérification email - sensible à l'énumération
  BUYER_CHECK: { limit: 10, windowMs: 60 * 1000 },      // 10/min

  // Soumission de demande - évite le spam
  DEMANDE_INFO: { limit: 5, windowMs: 60 * 1000 },      // 5/min

  // Recherche SIREN/SIRET - usage normal élevé (autocomplétion)
  SIREN_SEARCH: { limit: 30, windowMs: 60 * 1000 },     // 30/min

  // Données géographiques - usage très élevé (autocomplétion)
  GEO: { limit: 60, windowMs: 60 * 1000 },              // 60/min

  // Matching fournisseurs
  MATCHING: { limit: 10, windowMs: 60 * 1000 },         // 10/min

  // Questionnaire - usage modéré
  QUESTIONNAIRE: { limit: 30, windowMs: 60 * 1000 },    // 30/min

  // Données de référence (caractéristiques, catégories)
  REFERENCE_DATA: { limit: 30, windowMs: 60 * 1000 },   // 30/min

  // Images/Assets - usage élevé
  ASSETS: { limit: 100, windowMs: 60 * 1000 },          // 100/min

  // Tracking - usage très élevé
  TRACKING: { limit: 100, windowMs: 60 * 1000 },        // 100/min

  // Token génération - sensible
  TOKEN: { limit: 10, windowMs: 60 * 1000 },            // 10/min

  // Produits
  PRODUITS: { limit: 20, windowMs: 60 * 1000 },         // 20/min
} as const;

/**
 * Helper pour extraire l'IP d'une requête Next.js
 */
export function getClientIP(request: Request): string {
  // Headers de proxy (Cloudflare, Vercel, nginx, etc.)
  const forwardedFor = request.headers.get('x-forwarded-for');
  if (forwardedFor) {
    // Prendre la première IP (celle du client original)
    return forwardedFor.split(',')[0].trim();
  }

  const realIP = request.headers.get('x-real-ip');
  if (realIP) {
    return realIP;
  }

  // Fallback
  return 'anonymous';
}

/**
 * Helper pour créer une réponse 429 Too Many Requests
 */
export function rateLimitResponse(resetIn: number = 60000) {
  const retryAfter = Math.ceil(resetIn / 1000);

  return new Response(
    JSON.stringify({
      error: 'Trop de requêtes. Veuillez réessayer.',
      retryAfter,
    }),
    {
      status: 429,
      headers: {
        'Content-Type': 'application/json',
        'Retry-After': retryAfter.toString(),
        'X-RateLimit-Reset': retryAfter.toString(),
      },
    }
  );
}
