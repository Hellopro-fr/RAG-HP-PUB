import { NextRequest, NextResponse } from 'next/server';

// URL interne du CDN d'images (accessible uniquement depuis le réseau Docker)
const IMAGE_CDN_URL = process.env.IMAGE_CDN_INTERNAL_URL || 'http://image-cdn-service:8580';

/**
 * Décode un chemin d'image depuis Base64 URL-safe
 */
function decodeImagePath(encodedPath: string): string {
  try {
    // Reconvertit depuis Base64 URL-safe
    let base64 = encodedPath.replace(/-/g, '+').replace(/_/g, '/');
    // Ajoute le padding si nécessaire
    while (base64.length % 4) {
      base64 += '=';
    }
    // Decode en Node.js (pas de atob disponible)
    return Buffer.from(base64, 'base64').toString('utf-8');
  } catch {
    return '';
  }
}

/**
 * Valide que le chemin est une image valide
 */
function isValidImagePath(path: string): boolean {
  // Doit contenir un nom de fichier avec extension image
  const validExtensions = /\.(jpg|jpeg|png|gif|webp)$/i;
  if (!validExtensions.test(path)) {
    return false;
  }
  // Ne doit pas contenir de tentatives de path traversal
  if (path.includes('..') || path.includes('//')) {
    return false;
  }
  return true;
}

/**
 * Proxy pour les images produit
 * Route: /api/images/[path]
 *
 * Le [path] est un chemin Base64 URL-safe encodé qui est décodé puis
 * utilisé pour fetch l'image depuis le CDN interne.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string }> }
) {
  try {
    const { path: encodedPath } = await params;

    if (!encodedPath) {
      return NextResponse.json({ error: 'Path required' }, { status: 400 });
    }

    // Décode le chemin
    const imagePath = decodeImagePath(encodedPath);

    if (!imagePath) {
      return NextResponse.json({ error: 'Invalid path encoding' }, { status: 400 });
    }

    // Valide le chemin
    if (!isValidImagePath(imagePath)) {
      return NextResponse.json({ error: 'Invalid image path' }, { status: 400 });
    }

    // Construit l'URL interne du CDN
    const cdnUrl = `${IMAGE_CDN_URL}/images/${imagePath}`;

    // Fetch l'image depuis le CDN interne
    const response = await fetch(cdnUrl, {
      method: 'GET',
      headers: {
        'Accept': 'image/*',
      },
    });

    if (!response.ok) {
      if (response.status === 404) {
        return NextResponse.json({ error: 'Image not found' }, { status: 404 });
      }
      return NextResponse.json(
        { error: `CDN error: ${response.status}` },
        { status: response.status }
      );
    }

    // Récupère le content-type de l'image
    const contentType = response.headers.get('content-type') || 'image/jpeg';

    // Récupère le body comme ArrayBuffer
    const imageBuffer = await response.arrayBuffer();

    // Retourne l'image avec les headers de cache appropriés
    return new NextResponse(imageBuffer, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'public, max-age=2592000, immutable', // 30 jours
        'X-Content-Type-Options': 'nosniff',
      },
    });
  } catch (error) {
    console.error('Image proxy error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
