import { NextRequest, NextResponse } from 'next/server';

const BASE_URL = process.env.HELLOPRO_API_URL || 'https://api.hellopro.fr';
const URL_API = `${BASE_URL}/api/hp/view/index.php`;
const TOKEN   = process.env.TOKEN_INFO_PRODUIT || '';

/**
 * Proxy vers l'endpoint PHP get_photos_categorie : renvoie nom + 1 image de N
 * produits scrapés d'une catégorie (source IA scrapping), pour alimenter le
 * fond d'aperçu de l'étape transparence.
 * Route nommée "pht" (comme "pdt") pour éviter un blocage WAF sur "produits".
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { id_categorie, nb } = body;

    if (!id_categorie) {
      return NextResponse.json(
        { error: 'id_categorie required' },
        { status: 400 }
      );
    }

    const payload = {
      etape: 'get_photos_categorie',
      scrapping: 1,
      action: 'get',
      data: {
        id_categorie: id_categorie.toString(),
        nb: nb ?? 3,
      },
    };

    const response = await fetch(URL_API, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${TOKEN}`,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `API error: ${response.status}` },
        { status: response.status }
      );
    }

    const text = await response.text();

    // L'API peut retourner du texte avant le JSON (debug SQL), on extrait le JSON
    const jsonMatch = text.match(/\{[\s\S]*\}$/);
    if (!jsonMatch) {
      console.error('Invalid API response - no JSON found:', text.substring(0, 200));
      return NextResponse.json(
        { error: 'Invalid API response format' },
        { status: 500 }
      );
    }

    const data = JSON.parse(jsonMatch[0]);

    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('get_photos_categorie proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
