// Next.js 16 proxy (formerly middleware): pages need a session cookie. The cookie itself is
// validated by the Rust server on every API call; this only avoids rendering a page that would
// immediately fail.
import { type NextRequest, NextResponse } from 'next/server';

export function proxy(request: NextRequest) {
  if (request.cookies.has('atb_session')) return NextResponse.next();
  const url = request.nextUrl.clone();
  url.pathname = '/login';
  url.search = `?next=${encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search)}`;
  return NextResponse.redirect(url);
}

export const config = {
  // Everything except the login page, the API (served by the Rust server) and static assets.
  matcher: ['/((?!login|api|mcp|_next|favicon.ico).*)'],
};
