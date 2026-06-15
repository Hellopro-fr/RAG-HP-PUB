import { NextResponse } from 'next/server';

/**
 * Route Handler BFF — objet `user` du dataLayer GTM pour le visiteur courant.
 *
 * Pourquoi un BFF ? L'endpoint user vit dans l'API conseils (api/hp/view/gtm_user.php),
 * protégé par le MÊME Bearer token que page_conseil.php — un secret qui ne doit JAMAIS
 * atteindre le navigateur. Mais les données sont par-visiteur (cookies .hellopro.fr).
 *
 * Ce handler résout les deux : le navigateur appelle /api/gtm-user en same-origin
 * (cookies du visiteur envoyés automatiquement sous conseils.hellopro.fr) ; côté serveur,
 * on relaie ces cookies vers l'API avec le Bearer token (gardé côté serveur). Per-visiteur
 * → jamais de cache (force-dynamic + no-store).
 */

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const HP_BASE = process.env.HELLOPRO_API_URL ?? 'https://api.hellopro.fr';
const HP_USER_URL = `${HP_BASE}/api/hp/view/gtm_user.php`;
const API_TOKEN = process.env.CONSEILS_API_TOKEN ?? '';

const NO_STORE = { 'Cache-Control': 'private, no-store, max-age=0' } as const;

export async function GET(request: Request): Promise<NextResponse> {
  // Sans token (dev/local) : pas d'appel API → user dégradé "unlogged" conservé côté client.
  if (!API_TOKEN) {
    return NextResponse.json({ user: null }, { headers: NO_STORE });
  }

  // Relaie l'identité du visiteur (cookies .hellopro.fr) vers l'API.
  const cookie = request.headers.get('cookie') ?? '';

  try {
    const res = await fetch(HP_USER_URL, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        Accept: 'application/json',
        ...(cookie ? { Cookie: cookie } : {}),
      },
      cache: 'no-store',
    });

    if (!res.ok) {
      return NextResponse.json({ user: null }, { status: 200, headers: NO_STORE });
    }

    const text = await res.text();
    // L'API PHP peut préfixer du texte de debug avant le JSON (cf. fetchConseilPage).
    const jsonMatch = text.match(/\{[\s\S]*\}$/);
    if (!jsonMatch) {
      return NextResponse.json({ user: null }, { status: 200, headers: NO_STORE });
    }

    const data = JSON.parse(jsonMatch[0]) as { user?: Record<string, unknown> };
    return NextResponse.json({ user: data.user ?? null }, { headers: NO_STORE });
  } catch {
    // API/réseau indisponible : on renvoie un user nul, le client garde le dégradé.
    return NextResponse.json({ user: null }, { status: 200, headers: NO_STORE });
  }
}
