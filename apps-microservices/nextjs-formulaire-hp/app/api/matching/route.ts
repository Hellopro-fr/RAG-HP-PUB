import { NextRequest, NextResponse } from 'next/server';

// const BASE_URL = process.env.HELLOPRO_API_URL || 'https://www.hellopro.fr';

const BASE_URL         = 'https://api.hellopro.eu';
const URL_API_MATCHING = `${BASE_URL}/graph-service/produits/matching`;

export async function POST(request: NextRequest) {
  try {
    const body                    = await request.formData();
    const id_categorie            = body.get('id_categorie');
    const top_k                   = body.get('top_k');
    const champs_sortie           = body.get('champs_sortie');
    const metadonnee_utilisateurs = body.get('metadonnee_utilisateurs');
    const liste_caracteristique   = body.get('liste_caracteristique');
    const matching_test_params    = body.get('matching_test_params');

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
    if (matching_test_params) {
      const testParams = JSON.parse(matching_test_params.toString());
      // Ajouter chaque paramètre individuellement au payload
      for (const [key, value] of Object.entries(testParams)) {
        if (value !== undefined && value !== null) {
          payload[key] = value;
        }
      }
      console.log('[API Matching] Test params added to payload:', testParams);
    }

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
