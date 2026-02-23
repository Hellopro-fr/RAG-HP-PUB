import { NextRequest, NextResponse } from 'next/server';
import { rateLimit, getClientIP, rateLimitResponse, RATE_LIMITS } from '@/lib/utils/rate-limit';

const BASE_URL = process.env.HELLOPRO_API_URL || 'https://api.hellopro.fr';
const TOKEN = process.env.TOKEN_INFO_PRODUIT || '';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  // Rate limiting - 30 requêtes/minute
  const ip = getClientIP(request);
  const { success, resetIn } = rateLimit(ip, RATE_LIMITS.REFERENCE_DATA.limit, RATE_LIMITS.REFERENCE_DATA.windowMs);
  if (!success) return rateLimitResponse(resetIn);

  try {
    const { id } = await params;

    if (!id) {
      return NextResponse.json(
        { error: 'id_categorie required' },
        { status: 400 }
      );
    }

    const url = `${BASE_URL}/hp/info-categorie/${id}`;

    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${TOKEN}`,
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
    console.error('Info categorie proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
