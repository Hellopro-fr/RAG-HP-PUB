// ========================================
// API ROUTE - PROXY DEMANDE D'INFORMATION
// ========================================

import { NextRequest, NextResponse } from 'next/server';

/**
 * URL du endpoint PHP pour l'insertion des demandes
 */
const DEMANDE_INFO_ENDPOINT = process.env.DEMANDE_INFO_URL
  || 'https://dev-www.hellopro.fr/include/demande_information/demande_info_insertion.php';

/**
 * Convertit un objet en URLSearchParams pour FormData
 */
function objectToFormData(obj: Record<string, unknown>): URLSearchParams {
  const params = new URLSearchParams();

  Object.entries(obj).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.append(key, String(value));
    }
  });

  return params;
}

/**
 * POST /api/demande-info
 * Proxy vers le fichier PHP de création de demande
 */
export async function POST(request: NextRequest) {
  try {
    const payload = await request.json();

    // Convertir en FormData pour le PHP
    const formData = objectToFormData(payload);

    // Envoyer au PHP
    const response = await fetch(DEMANDE_INFO_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': request.headers.get('user-agent') || 'NextJS-UX-Matching',
        'X-Forwarded-For': request.headers.get('x-forwarded-for') || request.ip || '',
      },
      body: formData.toString(),
    });

    // Récupérer la réponse du PHP
    const responseText = await response.text();

    // Le PHP retourne généralement une URL de redirection
    if (responseText.startsWith('http')) {
      return NextResponse.json({
        success: true,
        redirect_url: responseText.trim(),
      });
    }

    // Si c'est du JSON
    try {
      const jsonResponse = JSON.parse(responseText);
      return NextResponse.json({
        success: true,
        ...jsonResponse,
      });
    } catch {
      // Retourner le texte brut si ce n'est pas du JSON
      return NextResponse.json({
        success: true,
        response: responseText.trim(),
      });
    }
  } catch (error) {
    console.error('Erreur API demande-info:', error);

    return NextResponse.json(
      {
        success: false,
        error: error instanceof Error ? error.message : 'Erreur serveur',
      },
      { status: 500 }
    );
  }
}

/**
 * OPTIONS pour CORS
 */
export async function OPTIONS() {
  return new NextResponse(null, {
    status: 200,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    },
  });
}
