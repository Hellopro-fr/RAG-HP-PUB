import { NextRequest, NextResponse } from 'next/server';
import { rateLimit, getClientIP, rateLimitResponse, RATE_LIMITS } from '@/lib/utils/rate-limit';

const BASE_URL = 'https://www.hellopro.fr';

export async function POST(request: NextRequest) {
  // Rate limiting - 10 requêtes/minute par IP
  const ip = getClientIP(request);
  const { success, resetIn } = rateLimit(ip, RATE_LIMITS.BUYER_CHECK.limit, RATE_LIMITS.BUYER_CHECK.windowMs);

  if (!success) {
    return rateLimitResponse(resetIn);
  }

  try {
    const body = await request.formData();

    const email = body.get('email');
    const id_rubrique = body.get('id_rubrique');
    const url_page = body.get('url_page');

    // Validation
    if (!email || typeof email !== 'string') {
      return NextResponse.json(
        { error: 'Email requis' },
        { status: 400 }
      );
    }

    // Construction FormData pour Legacy API
    const formData = new FormData();
    formData.append('email', email.trim());
    if (id_rubrique) formData.append('id_rubrique', id_rubrique.toString());
    if (url_page) formData.append('url_page', url_page.toString());

    // Appel vers l'API Legacy
    const response = await fetch(
      `${BASE_URL}/annuaire_hp/ajax/demande_information/verif_doublon_di.php`,
      {
        method: 'POST',
        body: formData,
      }
    );

    if (!response.ok) {
      return NextResponse.json(
        { error: `API error: ${response.status}` },
        { status: response.status }
      );
    }

    const result = await response.text();

    // Retourne le résultat brut
    return new NextResponse(result, {
      status: 200,
      headers: {
        'Content-Type': 'text/plain',
      },
    });
  } catch (error) {
    console.error('Buyer check proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
