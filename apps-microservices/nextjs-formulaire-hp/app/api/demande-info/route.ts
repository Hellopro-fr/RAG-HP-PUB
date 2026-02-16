// ========================================
// API ROUTE - PROXY DEMANDE D'INFORMATION
// Gère l'envoi avec ou sans pièces jointes
// ========================================

import { NextRequest, NextResponse } from 'next/server';

/**
 * URL du endpoint PHP pour l'insertion des demandes
 */
const DEMANDE_INFO_ENDPOINT = process.env.DEMANDE_INFO_URL
  || 'https://www.hellopro.fr/hellopro_fr/include/demande_information/demande_info_insertion.php';

/**
 * Convertit un objet complexe (avec objets et tableaux) en URLSearchParams
 */
function objectToFormData(obj: any, params = new URLSearchParams(), prefix = ''): URLSearchParams {
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      const value = obj[key];
      const fullKey = prefix ? `${prefix}[${key}]` : key;

      if (value === null || value === undefined || value === '') {
        continue;
      }

      if (typeof value === 'object' && !(value instanceof Date)) {
        // Si c'est un objet ou un tableau, on descend d'un niveau
        objectToFormData(value, params, fullKey);
      } else {
        // Si c'est une valeur primitive, on l'ajoute
        params.append(fullKey, String(value));
      }
    }
  }
  return params;
}

/**
 * Ajoute récursivement un objet dans un FormData (pour multipart)
 */
function appendObjectToFormData(formData: FormData, obj: any, prefix = ''): void {
  for (const key in obj) {
    if (Object.prototype.hasOwnProperty.call(obj, key)) {
      const value = obj[key];
      const fullKey = prefix ? `${prefix}[${key}]` : key;

      if (value === null || value === undefined || value === '') {
        continue;
      }

      if (typeof value === 'object' && !(value instanceof Date) && !(value instanceof Blob)) {
        // Si c'est un objet ou un tableau, on descend d'un niveau
        appendObjectToFormData(formData, value, fullKey);
      } else {
        // Si c'est une valeur primitive, on l'ajoute
        formData.append(fullKey, String(value));
      }
    }
  }
}

/**
 * POST /api/demande-info
 * Proxy vers le fichier PHP de création de demande
 * Gère les requêtes JSON (sans fichiers) et multipart/form-data (avec fichiers)
 */
export async function POST(request: NextRequest) {
  try {
    const contentType = request.headers.get('content-type') || '';

    let payload: any;
    let files: File[] = [];

    // Déterminer le type de requête
    if (contentType.includes('multipart/form-data')) {
      // Requête avec fichiers (FormData)
      const formData = await request.formData();

      // Extraire le payload JSON
      const payloadString = formData.get('payload');
      if (payloadString && typeof payloadString === 'string') {
        payload = JSON.parse(payloadString);
      } else {
        throw new Error('Payload manquant dans la requête multipart');
      }

      // Extraire les fichiers (clé 'filepond')
      const fileEntries = formData.getAll('filepond');
      files = fileEntries.filter((entry): entry is File => entry instanceof File);

      console.log(`[demande-info] Requête multipart avec ${files.length} fichier(s)`);
    } else {
      // Requête JSON classique (sans fichiers)
      payload = await request.json();
      console.log('[demande-info] Requête JSON (sans fichiers)');
    }

    console.log('[demande-info] Endpoint:', DEMANDE_INFO_ENDPOINT);

    let response: Response;

    if (files.length > 0) {
      // Avec fichiers : envoyer en multipart/form-data au PHP
      const phpFormData = new FormData();

      // Ajouter les fichiers avec la clé 'filepond' (format attendu par PHP)
      files.forEach((file) => {
        phpFormData.append('filepond', file, file.name);
      });

      // Ajouter les données du payload
      appendObjectToFormData(phpFormData, payload);

      response = await fetch(DEMANDE_INFO_ENDPOINT, {
        method: 'POST',
        headers: {
          'User-Agent': request.headers.get('user-agent') || 'NextJS-UX-Matching',
          'X-Forwarded-For': request.headers.get('x-forwarded-for') || request.ip || '',
          // Ne pas définir Content-Type - le runtime le définit avec le boundary
        },
        body: phpFormData,
      });
    } else {
      // Sans fichiers : envoyer en x-www-form-urlencoded (comportement actuel)
      const urlParams = objectToFormData(payload);

      response = await fetch(DEMANDE_INFO_ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'User-Agent': request.headers.get('user-agent') || 'NextJS-UX-Matching',
          'X-Forwarded-For': request.headers.get('x-forwarded-for') || request.ip || '',
        },
        body: urlParams.toString(),
      });
    }

    // Récupérer la réponse du PHP
    const responseText = await response.text();
    console.log('[demande-info] Réponse PHP:', responseText.substring(0, 200));

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
