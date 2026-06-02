import { generateConseilToken } from './conseil-token';
import { createDecipheriv, createHash } from 'crypto';

const TEST_SECRET = 'test-secret-for-unit-tests';

function base64UrlDecode(str: string): Buffer {
  let base64 = str.replace(/-/g, '+').replace(/_/g, '/');
  const padding = base64.length % 4;
  if (padding) base64 += '='.repeat(4 - padding);
  return Buffer.from(base64, 'base64');
}

function decryptToken(token: string, secret: string): Record<string, string> {
  const data = base64UrlDecode(token);
  const iv = data.subarray(0, 16);
  const encrypted = data.subarray(16);
  const key = createHash('sha256').update(secret).digest();
  const decipher = createDecipheriv('aes-256-cbc', key, iv);
  const decrypted = Buffer.concat([decipher.update(encrypted), decipher.final()]);
  return JSON.parse(decrypted.toString('utf-8'));
}

describe('generateConseilToken', () => {
  beforeEach(() => {
    process.env.CONSEILS_TOKEN_SECRET = TEST_SECRET;
  });

  afterEach(() => {
    delete process.env.CONSEILS_TOKEN_SECRET;
  });

  it('génère un token non vide', () => {
    const token = generateConseilToken();
    expect(token).toBeTruthy();
    expect(typeof token).toBe('string');
  });

  it('le payload déchiffré contient temp-key et expires-at', () => {
    const token = generateConseilToken();
    const payload = decryptToken(token, TEST_SECRET);
    expect(payload['temp-key']).toBeDefined();
    expect(payload['expires-at']).toBe('unlimited');
  });

  it('temp-key commence par "no_token-"', () => {
    const token = generateConseilToken();
    const payload = decryptToken(token, TEST_SECRET);
    expect(payload['temp-key']).toMatch(/^no_token-\d+$/);
  });

  it('génère un token différent à chaque appel (IV aléatoire)', () => {
    const t1 = generateConseilToken();
    const t2 = generateConseilToken();
    expect(t1).not.toBe(t2);
  });

  it('lève une erreur si CONSEILS_TOKEN_SECRET n\'est pas défini', () => {
    delete process.env.CONSEILS_TOKEN_SECRET;
    expect(() => generateConseilToken()).toThrow('CONSEILS_TOKEN_SECRET');
  });

  it('le token est encodé en Base64 URL-safe (pas de +, /, =)', () => {
    const token = generateConseilToken();
    expect(token).not.toMatch(/[+/=]/);
  });
});
