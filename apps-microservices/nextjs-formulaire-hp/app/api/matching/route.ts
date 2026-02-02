import { NextRequest, NextResponse } from 'next/server';

// const BASE_URL = process.env.HELLOPRO_API_URL || 'https://www.hellopro.fr';

const BASE_URL         = 'https://api.hellopro.eu';
const URL_API_MATCHING = `${BASE_URL}/graphdebug-service/produits/matching`;

export async function POST(request: NextRequest) {
  try {
    const body = await request.formData();
    const id_categorie = body.get('id_categorie');
    const top_k = body.get('top_k');
    const metadonnee_utilisateurs = body.get('metadonnee_utilisateurs');
    const liste_caracteristique = body.get('liste_caracteristique');

    if (!id_categorie) {
      return NextResponse.json(
        { error: 'id_categorie required' },
        { status: 400 }
      );
    }

    const url = new URL(URL_API_MATCHING);
    console.log('Calling API_MATCHING API:', url.toString());    
    
    // Reconstruction du payload avec les bons types
    const payload = {
      id_categorie: Number(id_categorie), // Conversion en nombre si nécessaire
      top_k: Number(top_k) || 12,        // Conversion en nombre
      // On parse les chaînes JSON pour les transformer en vrais objets/tableaux JS
      metadonnee_utilisateurs: metadonnee_utilisateurs 
        ? JSON.parse(metadonnee_utilisateurs.toString()) 
        : {},
      liste_caracteristique: liste_caracteristique 
        ? JSON.parse(liste_caracteristique.toString()) 
        : []
    };

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

    console.log("API_MATCHING", data);

    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error('API_MATCHING proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
