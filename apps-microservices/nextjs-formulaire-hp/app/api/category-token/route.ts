import { NextRequest, NextResponse } from 'next/server';
import { generateCategoryToken, validateCategoryToken } from '@/lib/category-token';

/**
 * POST /api/category-token
 * Génère un token sécurisé pour une catégorie
 *
 * Body: { categoryId: number }
 * Response: { token: string, url: string }
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { categoryId } = body;

    if (!categoryId || typeof categoryId !== 'number' || categoryId <= 0) {
      return NextResponse.json(
        { error: 'categoryId est requis et doit être un nombre positif' },
        { status: 400 }
      );
    }

    const token = generateCategoryToken(categoryId);
    const baseUrl = process.env.NEXT_PUBLIC_BASE_PATH || '';

    return NextResponse.json({
      token,
      urls: {
        questionnaire: `${baseUrl}/questionnaire/${token}`,
        selection: `${baseUrl}/selection/${token}`,
        formulaire: `${baseUrl}/formulaire/${token}`,
      },
    });
  } catch (error) {
    console.error('Erreur génération token:', error);
    return NextResponse.json(
      { error: 'Erreur lors de la génération du token' },
      { status: 500 }
    );
  }
}

/**
 * GET /api/category-token?token=xxx
 * Valide un token et retourne l'ID de catégorie
 *
 * Query: token
 * Response: { valid: boolean, categoryId?: number, error?: string }
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const token = searchParams.get('token');

  if (!token) {
    return NextResponse.json(
      { error: 'token est requis' },
      { status: 400 }
    );
  }

  const result = validateCategoryToken(token);

  return NextResponse.json(result);
}
