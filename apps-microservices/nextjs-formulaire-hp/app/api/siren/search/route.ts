import { NextRequest, NextResponse } from 'next/server';

const BASE_URL = 'https://www.hellopro.fr';

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const soc = searchParams.get('soc');
    const p = searchParams.get('p') || 'demande_information_v2';

    // Validation
    if (!soc) {
      return NextResponse.json(
        { error: 'Paramètre soc requis' },
        { status: 400 }
      );
    }

    if (soc.trim().length < 2) {
      return NextResponse.json(
        { error: 'Veuillez saisir au moins 2 caractères' },
        { status: 400 }
      );
    }

    // Construction URL pour API INSEE v2 (retourne du JSON)
    const url = new URL(`${BASE_URL}/api_insee/_ag_web_service_insee_v2.php`);
    url.searchParams.append('soc', soc.trim());
    url.searchParams.append('p', p);

    console.log('Calling Legacy SIREN API v2:', url.toString());

    // Appel vers l'API Legacy v2
    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `API error: ${response.status}` },
        { status: response.status }
      );
    }

    const jsonData = await response.json();

    console.log('SIREN API v2 response:', jsonData);

    // Retourne le JSON (structure: { status, nb, max, result: [...] })
    return NextResponse.json(jsonData, { status: 200 });
  } catch (error) {
    console.error('SIREN search proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
