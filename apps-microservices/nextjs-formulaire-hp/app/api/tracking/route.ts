import { NextRequest, NextResponse } from 'next/server';


const BASE_URL = process.env.HELLOPRO_API_URL || 'https://api.hellopro.fr';
const URL_API = `${BASE_URL}/api/hp/view/index.php`;
const TOKEN   = process.env.TOKEN_INFO_PRODUIT || '';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // Récupérer le Referrer réel depuis les headers de la requête (équivalent PHP $_SERVER['HTTP_REFERER'])
    const serverReferrer = request.headers.get('referer') || '';

    // Injection automatique dans session_meta pour garantir la donnée en base
    if (body.data && body.data.session_meta) {
      // Si le client n'a pas pu l'envoyer (document.referrer vide), on utilise celui du serveur
      if (!body.data.session_meta.referrer || body.data.session_meta.referrer === '') {
        body.data.session_meta.referrer = serverReferrer || '';
      }
    }

    // Forward to the tracking API
    const response = await fetch(URL_API, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${TOKEN}`
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      console.error('Tracking API error:', response.status);
      return NextResponse.json({ error: 'Tracking failed' }, { status: response.status });
    }

    const data = await response.json().catch(() => ({}));
    return NextResponse.json({ success: true, data });

  } catch (error) {
    console.error('Tracking proxy error:', error);
    return NextResponse.json({ error: 'Internal error' }, { status: 500 });
  }
}
