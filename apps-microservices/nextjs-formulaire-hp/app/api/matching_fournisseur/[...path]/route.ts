import { NextRequest, NextResponse } from 'next/server';

const BASE_URL = 'https://api.hellopro.eu';
const URL_API_FOURNISSEUR = `${BASE_URL}/graphdebug-service/fournisseur`;

/**
 * GET /api/matching_fournisseur/[...path]
 * Proxy vers l'API fournisseur de HelloPro
 *
 * Exemple: /api/matching_fournisseur/produit/434592
 *       → https://api.hellopro.eu/graphdebug-service/fournisseur/produit/434592
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params;
    const pathString = path.join('/');
    const targetUrl = `${URL_API_FOURNISSEUR}/${pathString}`;

    console.log('[matching_fournisseur] GET:', targetUrl);

    const response = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('[matching_fournisseur] Erreur API:', response.status, errorText);
      return NextResponse.json(
        { error: `API error: ${response.status}`, details: errorText },
        { status: response.status }
      );
    }

    const data = await response.json();

    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('[matching_fournisseur] Proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error', message: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}

/**
 * POST /api/matching_fournisseur/[...path]
 * Proxy POST vers l'API fournisseur
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params;
    const pathString = path.join('/');
    const targetUrl = `${URL_API_FOURNISSEUR}/${pathString}`;
    const body = await request.json();

    console.log('[matching_fournisseur] POST:', targetUrl, body);

    const response = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('[matching_fournisseur] Erreur API POST:', response.status, errorText);
      return NextResponse.json(
        { error: `API error: ${response.status}`, details: errorText },
        { status: response.status }
      );
    }

    const data = await response.json();

    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('[matching_fournisseur] POST Proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error', message: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
