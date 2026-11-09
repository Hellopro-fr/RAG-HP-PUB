// Server-side API client for Server Components: calls the Rust server directly
// (BACKEND_INTERNAL_URL) and forwards the user's httpOnly session cookie.
import createClient from 'openapi-fetch';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import type { components, paths } from './schema';

const BACKEND = process.env.BACKEND_INTERNAL_URL ?? 'http://localhost:8621';

export async function serverApi() {
  const session = (await cookies()).get('atb_session');
  return createClient<paths>({
    baseUrl: BACKEND,
    headers: session ? { cookie: `atb_session=${session.value}` } : {},
    cache: 'no-store',
  });
}

/** Unwrap a server-side call; an expired session sends the user to the login page. */
export async function load<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
  next: string,
): Promise<T> {
  const { data, response } = await call;
  if (response.status === 401) redirect(`/login?next=${encodeURIComponent(next)}`);
  if (!response.ok || data === undefined) {
    throw new Error(`backend returned HTTP ${response.status}`);
  }
  return data;
}

/** The signed-in user (level, allowed permissions), or null without a valid session. */
export async function currentUser(): Promise<components['schemas']['MeView'] | null> {
  if (!(await cookies()).get('atb_session')) return null;
  const api = await serverApi();
  const { data, response } = await api.GET('/api/auth/me');
  return response.ok && data ? data : null;
}
