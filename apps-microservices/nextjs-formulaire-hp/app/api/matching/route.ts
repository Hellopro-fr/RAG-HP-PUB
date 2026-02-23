import { NextRequest, NextResponse } from 'next/server';
import { rateLimit, getClientIP, rateLimitResponse, RATE_LIMITS } from '@/lib/utils/rate-limit';

// const BASE_URL = process.env.HELLOPRO_API_URL || 'https://www.hellopro.fr';

const BASE_URL         = 'https://api.hellopro.eu';
const URL_API_MATCHING = `${BASE_URL}/graph-service/produits/matching`;

export async function POST(request: NextRequest) {
  // Rate limiting - 10 requêtes/minute
  const ip = getClientIP(request);
  const { success, resetIn } = rateLimit(ip, RATE_LIMITS.MATCHING.limit, RATE_LIMITS.MATCHING.windowMs);
  if (!success) return rateLimitResponse(resetIn);

  try {
    const body                    = await request.formData();
    const id_categorie            = body.get('id_categorie');
    const top_k                   = body.get('top_k');
    const champs_sortie           = body.get('champs_sortie');
    const metadonnee_utilisateurs = body.get('metadonnee_utilisateurs');
    const liste_caracteristique   = body.get('liste_caracteristique');
    const scoring    = body.get('scoring');

    if (!id_categorie) {
      return NextResponse.json(
        { error: 'id_categorie required' },
        { status: 400 }
      );
    }

    // Reconstruction du payload avec les bons types
    const payload: Record<string, any> = {
      id_categorie: Number(id_categorie), // Conversion en nombre si nécessaire
      top_k: Number(top_k) || 12,        // Conversion en nombre
      champs_sortie : champs_sortie
        ? JSON.parse(champs_sortie.toString())
        : {},
      // On parse les chaînes JSON pour les transformer en vrais objets/tableaux JS
      metadonnee_utilisateurs: metadonnee_utilisateurs
        ? JSON.parse(metadonnee_utilisateurs.toString())
        : {},
      liste_caracteristique: liste_caracteristique
        ? JSON.parse(liste_caracteristique.toString())
        : []
    };

    // Ajouter les paramètres de test du matching (si présents)
    // Ces paramètres sont passés via l'URL pour les tests uniquement
    // Ils doivent être encapsulés dans un objet "scoring"
    console.log('[API Matching] Scoring field received:', scoring);
    if (scoring) {
      const testParams = JSON.parse(scoring.toString());
      // Encapsuler dans l'objet scoring
      payload.scoring = testParams;
      console.log('[API Matching] Scoring params added to payload:', testParams);
    } else {
      console.log('[API Matching] No scoring params received');
    }

    console.log('[API Matching] Final payload to GraphRAG:', JSON.stringify(payload, null, 2));

    const response = await fetch(URL_API_MATCHING, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json'
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
    console.error('API_MATCHING proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
