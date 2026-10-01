import { NextResponse } from 'next/server';

/**
 * Liveness probe — répond « le conteneur Next.js est vivant et sait servir ».
 *
 * Volontairement trivial : n'appelle AUCUNE API externe (pas l'API HelloPro).
 * Un health check de liveness ne doit pas dépendre des services en amont, sinon
 * une panne de l'API ferait redémarrer le front en boucle. Cible du `healthcheck`
 * docker-compose et du LB nginx (`nextjs-conseils-hp-lb`).
 */
export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export function GET(): NextResponse {
  return NextResponse.json(
    { status: 'ok' },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
