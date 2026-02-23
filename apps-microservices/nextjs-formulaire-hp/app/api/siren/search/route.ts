import { NextRequest, NextResponse } from 'next/server';
import { rateLimit, getClientIP, rateLimitResponse, RATE_LIMITS } from '@/lib/utils/rate-limit';

// Force dynamic rendering (uses searchParams)
export const dynamic = 'force-dynamic';

const BASE_URL = 'https://www.hellopro.fr';

export async function GET(request: NextRequest) {
  // Rate limiting - 30 requêtes/minute (autocomplétion)
  const ip = getClientIP(request);
  const { success, resetIn } = rateLimit(ip, RATE_LIMITS.SIREN_SEARCH.limit, RATE_LIMITS.SIREN_SEARCH.windowMs);
  if (!success) return rateLimitResponse(resetIn);

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
