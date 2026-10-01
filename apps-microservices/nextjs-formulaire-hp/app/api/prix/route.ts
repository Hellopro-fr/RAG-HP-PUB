import { NextRequest, NextResponse } from 'next/server';

const URL_API_PRIX = 'https://api.hellopro.eu/prix_traitement-service/prix/questionnaire-v2';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    if (!body.id_categorie) {
      return NextResponse.json(
        { error: 'id_categorie required' },
        { status: 400 }
      );
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90000); // 1min30s

    try {
      const response = await fetch(URL_API_PRIX, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (!response.ok) {
        return NextResponse.json(
          { error: `API error: ${response.status}` },
          { status: response.status }
        );
      }

      const data = await response.json();

      // Strip matching.results (~400 KB de debug backend) avant retour au navigateur
      if (data?.matching?.results) {
        const { results, ...matchingMeta } = data.matching;
        data.matching = {
          ...matchingMeta,
          results_count_retenues: Array.isArray(results) ? results.length : 0,
        };
      }

      return NextResponse.json(data, { status: 200 });
    } catch (fetchError: any) {
      clearTimeout(timeout);
      if (fetchError.name === 'AbortError') {
        return NextResponse.json(
          { error: 'Prix API timeout (90s)' },
          { status: 504 }
        );
      }
      throw fetchError;
    }
  } catch (error) {
    console.error('Prix proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
