import { NextRequest, NextResponse } from 'next/server';

const BASE_URL = process.env.HELLOPRO_FRONTEND_URL || 'https://dev-www.hellopro.fr';

/**
 * Proxy pour ajax_get_data.php
 * - ?t=1           → Liste des pays
 * - ?t=2&cp=XXXXX  → Villes par code postal
 */
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const t = searchParams.get('t');
    const cp = searchParams.get('cp');

    if (!t) {
      return NextResponse.json(
        { error: 'Paramètre t requis' },
        { status: 400 }
      );
    }

    const url = new URL(`${BASE_URL}/hellopro_fr/ajax/ajax_get_data.php`);
    url.searchParams.append('t', t);
    if (cp) {
      url.searchParams.append('cp', cp);
    }

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `API error: ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();

    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('Geo proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
