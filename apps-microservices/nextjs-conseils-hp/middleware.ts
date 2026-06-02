import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Next.js App Router ne route pas les URLs avec extension .html vers les segments
 * dynamiques — il les traite comme des fichiers statiques inexistants et renvoie 404.
 * Ce middleware réécrit /slug-123.html → /slug-123 avant le routing.
 * Le segment [slugWithId] reçoit alors "slug-123" (sans .html).
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.endsWith('.html')) {
    const url = request.nextUrl.clone();
    url.pathname = pathname.slice(0, -5); // retire '.html'
    return NextResponse.rewrite(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!_next/|api/|favicon\\.ico).+\\.html)'],
};
