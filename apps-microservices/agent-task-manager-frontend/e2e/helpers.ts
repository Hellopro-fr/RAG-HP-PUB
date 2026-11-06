// Shared setup for the e2e suite: admin login and fixtures created through the real API.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { type APIRequestContext, type Browser, type BrowserContext, expect } from '@playwright/test';

function backendEnv(): Record<string, string> {
  try {
    const here = dirname(fileURLToPath(import.meta.url));
    const raw = readFileSync(resolve(here, '../../agent-task-manager-backend/.env'), 'utf8');
    return Object.fromEntries(
      raw
        .split('\n')
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith('#') && l.includes('='))
        .map((l) => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)]),
    );
  } catch {
    return {};
  }
}

const env = backendEnv();
export const ADMIN = {
  login: process.env.E2E_ADMIN_LOGIN ?? env.ATB_BOOTSTRAP_ADMIN_LOGIN ?? 'admin',
  password: process.env.E2E_ADMIN_PASSWORD ?? env.ATB_BOOTSTRAP_ADMIN_PASSWORD ?? '',
};

export async function login(request: APIRequestContext) {
  const res = await request.post('/api/auth/login', { data: ADMIN });
  expect(res.ok(), `admin login: ${res.status()}`).toBeTruthy();
}

/** A logged-in browser context (the session cookie is shared with its pages). */
export async function adminContext(browser: Browser): Promise<BrowserContext> {
  const ctx = await browser.newContext();
  await login(ctx.request);
  return ctx;
}

async function post<T>(request: APIRequestContext, path: string, data: unknown, token?: string): Promise<T> {
  const res = await request.post(path, {
    data,
    headers: token ? { authorization: `Bearer ${token}` } : undefined,
  });
  expect(res.ok(), `${path}: ${res.status()} ${await res.text()}`).toBeTruthy();
  return (await res.json()) as T;
}

export type Fixture = { project: string; spec: string; tasks: string[]; agent: { name: string; token: string } };

/** Project without test/review gates, an approved spec, `titles.length` tasks and one agent. */
export async function fixture(request: APIRequestContext, titles: string[]): Promise<Fixture> {
  const stamp = Date.now().toString(36);
  const { id: project } = await post<{ id: string }>(request, '/api/projects', {
    name: `e2e ${stamp}`,
    workflow: {
      spec_gate: true,
      test_gate: 'none',
      review_gate: 'none',
      require_different_model: false,
      max_rejections: 3,
      lease_ttl_secs: 600,
      preferred_grace_secs: 120,
    },
  });
  const { spec_id: spec } = await post<{ spec_id: string }>(request, `/api/projects/${project}/specs`, {
    title: 'Spec e2e',
    body_md: 'Corps de la spec',
    acceptance_criteria: [{ id: 'AC-1', text: 'Le critère e2e', verify: { kind: 'human' } }],
  });
  await post(request, `/api/specs/${spec}/versions/1/approve`, {});
  const tasks: string[] = [];
  for (const title of titles) {
    const { task_id } = await post<{ task_id: string }>(request, `/api/projects/${project}/tasks`, {
      title,
      spec_id: spec,
    });
    tasks.push(task_id);
  }
  const name = `agent-${stamp}`;
  const { token } = await post<{ token: string }>(request, '/api/actors', {
    kind: 'agent',
    name,
    model: 'model-e2e',
    roles: ['implementer'],
  });
  return { project, spec, tasks, agent: { name, token } };
}

export async function agentCall<T>(request: APIRequestContext, token: string, path: string, data: unknown): Promise<T> {
  return post<T>(request, path, data, token);
}
