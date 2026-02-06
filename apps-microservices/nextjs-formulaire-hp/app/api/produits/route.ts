import { NextRequest, NextResponse } from 'next/server';

const BASE_URL = process.env.HELLOPRO_API_URL || 'https://dev-api.hellopro.fr';
const URL_API = `${BASE_URL}/api/hp/view/index.php`;
const TOKEN   = process.env.TOKEN_INFO_PRODUIT || '';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { id_categorie, id_produits } = body;

    if (!id_produits || !Array.isArray(id_produits) || id_produits.length === 0) {
      return NextResponse.json(
        { error: 'id_produits required (array of product IDs)' },
        { status: 400 }
      );
    }

    const payload = {
      etape: "get_info_produit",
      scrapping: 1,
      action: "get",
      data: {
        id_categorie: id_categorie?.toString() || "",
        id_produits: id_produits.map(String),
      },
    };

    console.log('Calling get_info_produit API:', URL_API, payload);

    const response = await fetch(URL_API, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',        
        'Authorization': `Bearer ${TOKEN}`
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

    // L'API peut retourner du texte avant le JSON (SQL debug), on extrait le JSON
    const jsonMatch = text.match(/\{[\s\S]*\}$/);
    if (!jsonMatch) {
      console.error('Invalid API response - no JSON found:', text.substring(0, 200));
      return NextResponse.json(
        { error: 'Invalid API response format' },
        { status: 500 }
      );
    }

    const data = JSON.parse(jsonMatch[0]);

    console.log('get_info_produit response:', Object.keys(data.items || {}));

    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('get_info_produit proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
