// Browser API client. Same origin in production (the ingress routes /api/* to the Rust server);
// rewritten to the backend by `next dev`. Types come ONLY from the generated schema.d.ts.
import createClient from 'openapi-fetch';

import type { components, paths } from './schema';

export type Schemas = components['schemas'];
export type Board = Schemas['Board'];
export type TaskView = Schemas['TaskView'];
export type StoredEvent = Schemas['StoredEvent'];
export type TaskContext = Schemas['TaskContext'];
export type QuestionView = Schemas['QuestionView'];
export type ActorView = Schemas['ActorView'];
export type ProjectView = Schemas['ProjectView'];
export type CommandResult = Schemas['CommandResult'];
export type ErrorBody = Schemas['ErrorBody'];
export type MeView = Schemas['MeView'];
export type AccessOverview = Schemas['AccessOverview'];
export type UserAccess = Schemas['UserAccess'];
export type TeamAccess = Schemas['TeamAccess'];
export type SourceView = Schemas['SourceView'];
export type InvitationView = Schemas['InvitationView'];
export type ProjectMembers = Schemas['ProjectMembers'];
export type PersonAccess = Schemas['PersonAccess'];
export type UserView = Schemas['UserView'];

export const api = createClient<paths>({ baseUrl: '', credentials: 'include' });

/** Origin of the SSE stream: '' (same origin) in production, the backend URL in `next dev`. */
export const streamOrigin = process.env.NEXT_PUBLIC_STREAM_ORIGIN ?? '';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ErrorBody | undefined,
  ) {
    super(body?.message ?? `HTTP ${status}`);
  }

  get code(): string {
    return this.body?.code ?? 'http_error';
  }
}

/** Throw on error, return the typed body on success. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok || data === undefined) {
    throw new ApiError(response.status, error as ErrorBody | undefined);
  }
  return data;
}

/** User-facing message: refusals get a French explanation, other API errors their message. */
export function errorMessage(e: unknown, fallback: string, forbidden: string): string {
  if (e instanceof ApiError) return e.status === 403 ? forbidden : e.message;
  return fallback;
}

export const keys = {
  board: (projectId: string) => ['board', projectId] as const,
  task: (taskId: string) => ['task', taskId] as const,
  timeline: (taskId: string) => ['timeline', taskId] as const,
  questions: (status: string) => ['questions', status] as const,
  actors: ['actors'] as const,
  projects: ['projects'] as const,
  access: ['access'] as const,
  invitations: ['invitations'] as const,
  members: (projectId: string) => ['members', projectId] as const,
  users: ['users'] as const,
  accessUser: (id: string) => ['access', 'user', id] as const,
  accessTeam: (id: string) => ['access', 'team', id] as const,
};
