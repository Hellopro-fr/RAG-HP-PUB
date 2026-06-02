import { createCipheriv, createHash, randomBytes } from 'crypto';

function deriveKey(secret: string): Buffer {
  return createHash('sha256').update(secret).digest();
}

function base64UrlEncode(data: Buffer): string {
  return data
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

/**
 * Génère un token AES-256-CBC pour l'API PHP page_conseil.php.
 *
 * Payload attendu par hp_check_access (hp_fonctions.php) :
 *   { "temp-key": "no_token-<n>", "expires-at": "unlimited" }
 *
 * Le token est différent à chaque appel grâce à l'IV aléatoire.
 * Partage le même algorithme que lib/category-token.ts du formulaire HP.
 */
export function generateConseilToken(): string {
  const secret = process.env.CONSEILS_TOKEN_SECRET ?? '';
  if (!secret) {
    throw new Error('CONSEILS_TOKEN_SECRET is not configured');
  }

  const payload = {
    'temp-key': `no_token-${Date.now()}`,
    'expires-at': 'unlimited',
  };

  const key = deriveKey(secret);
  const iv = randomBytes(16);
  const cipher = createCipheriv('aes-256-cbc', key, iv);
  const encrypted = Buffer.concat([
    cipher.update(JSON.stringify(payload), 'utf-8'),
    cipher.final(),
  ]);

  return base64UrlEncode(Buffer.concat([iv, encrypted]));
}
