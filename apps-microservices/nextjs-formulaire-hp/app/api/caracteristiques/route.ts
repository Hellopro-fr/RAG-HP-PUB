import { NextRequest, NextResponse } from 'next/server';

const BASE_URL = process.env.HELLOPRO_API_URL || 'https://dev-api.hellopro.fr';
const URL_API = `${BASE_URL}/v2/index.php`;
const TOKEN = process.env.NEXT_TOKEN_API_QUESTION || '';

export async function POST(request: NextRequest) {
  try {
    const body = await request.formData();
    const categoryId = body.get('id_categorie');

    if (!categoryId) {
      return NextResponse.json(
        { error: 'id_categorie required' },
        { status: 400 }
      );
    }

    const payload = {
      etape: "caracteristique",
      field: "final",
      action: "get",
      data: {
        id_categorie: categoryId.toString()
      }
    };

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

    const data = await response.json();

    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('Caracteristiques proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
