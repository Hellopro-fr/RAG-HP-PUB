import { NextRequest, NextResponse } from 'next/server';

/**
 * Proxy vers l'autocomplétion HelloPro.
 * Évite les erreurs CORS en proxyfiant côté serveur Next.js.
 *
 * POST /api/search
 * Body JSON : { chaine: string }
 * Retourne : { html: string } — le HTML brut de l'autocomplétion
 */
export async function POST(request: NextRequest) {
  try {
    const { chaine } = await request.json() as { chaine: string };

    if (!chaine || chaine.trim().length < 2) {
      return NextResponse.json({ html: '' });
    }

    const res = await fetch(
      'https://www.hellopro.fr/hellopro_fr/ajax/auto_completion_recherche.php',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'User-Agent': 'Mozilla/5.0 (compatible; HelloPro-Conseils/1.0)',
        },
        body: `chaine=${encodeURIComponent(chaine.trim())}`,
      }
    );

    if (!res.ok) {
      return NextResponse.json({ html: '' }, { status: res.status });
    }

    const html = await res.text();
    return NextResponse.json({ html });
  } catch (err) {
    console.error('[/api/search] error:', err);
    return NextResponse.json({ html: '' }, { status: 500 });
  }
}
