import { NextRequest, NextResponse } from 'next/server';

const BASE_URL = 'https://www.hellopro.fr';

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const soc = searchParams.get('soc');
    const cp = searchParams.get('cp');
    const p = searchParams.get('p') || 'demande_information_v2';

    // Validation
    if (!soc || !cp) {
      return NextResponse.json(
        { error: 'Paramètres soc et cp requis' },
        { status: 400 }
      );
    }

    // Validation code postal (5 chiffres)
    if (!/^[0-9]{5}$/.test(cp.trim())) {
      return NextResponse.json(
        { error: 'Le code postal doit contenir 5 chiffres' },
        { status: 400 }
      );
    }

    // Construction URL pour API INSEE
    const url = new URL(`${BASE_URL}/api_insee/_ag_web_service_insee.php`);
    url.searchParams.append('soc', soc.trim());
    url.searchParams.append('cp', cp.trim());
    url.searchParams.append('p', p);

    console.log('Calling Legacy SIRET API:', url.toString());

    // Appel vers l'API Legacy
    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: {
        Accept: 'text/html,application/json',
      },
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `API error: ${response.status}` },
        { status: response.status }
      );
    }

    const htmlContent = await response.text();

    console.log('SIRET API response length:', htmlContent.length);

    // Retourne le HTML brut (le frontend devra le parser)
    return new NextResponse(htmlContent, {
      status: 200,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
      },
    });
  } catch (error) {
    console.error('SIRET search proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
