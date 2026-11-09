'use client';

// /users ("Utilisateurs"): people of the board and people invited to a project, with their
// level, status, teams, projects and agents. Admins disable access and revoke sessions; levels
// and permissions are changed on the Accès page.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';

import { Badge, Button, Card, cn } from '@/components/ui';
import {
  type ErrorBody,
  type UserView,
  ApiError,
  api,
  errorMessage,
  keys,
  unwrap,
} from '@/lib/api/client';
import { formatDate, formatRemaining, fr } from '@/lib/i18n/fr';

type Filter = 'all' | 'admin' | 'pending' | 'disabled';

export function matchesUserFilter(u: Pick<UserView, 'level' | 'status'>, f: Filter): boolean {
  if (f === 'admin') return u.level === 'admin';
  if (f === 'pending') return u.status === 'pending';
  if (f === 'disabled') return u.status === 'disabled';
  return true;
}

async function okOrThrow(r: { error?: unknown; response: Response }): Promise<void> {
  if (!r.response.ok) throw new ApiError(r.response.status, r.error as ErrorBody | undefined);
}

const statusTone = (s: string) => (s === 'active' ? 'ok' : s === 'disabled' ? 'danger' : 'warn');

function seen(iso: string | null | undefined): string {
  if (!iso) return fr.users.never;
  return fr.users.seen(`il y a ${formatRemaining(Date.now() - new Date(iso).getTime())}`);
}

const keyOf = (u: UserView) => u.id ?? u.login;

export function UsersPage({
  initial,
  meId,
  isAdmin,
}: {
  initial: UserView[];
  meId: string;
  isAdmin: boolean;
}) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: keys.users,
    queryFn: () => unwrap(api.GET('/api/users')),
    initialData: initial,
  });
  const [filter, setFilter] = useState<Filter>('all');
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const onError = (e: unknown) => setError(errorMessage(e, fr.errors.generic, fr.errors.forbidden));
  const status = useMutation({
    mutationFn: (v: { id: string; disabled: boolean }) =>
      api
        .PUT('/api/users/{id}/status', {
          params: { path: { id: v.id } },
          body: { disabled: v.disabled },
        })
        .then(okOrThrow),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: keys.users });
    },
    onError,
  });
  const revoke = useMutation({
    mutationFn: (id: string) =>
      api.POST('/api/users/{id}/revoke-sessions', { params: { path: { id } } }).then(okOrThrow),
    onSuccess: () => {
      setError(null);
      setInfo(fr.users.revoked);
    },
    onError,
  });

  const list = data.filter((u) => matchesUserFilter(u, filter));
  const sel = data.find((u) => keyOf(u) === selected) ?? null;
  const isMe = sel?.id === meId;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{fr.users.title}</h1>
        <Badge>{data.length}</Badge>
        <div role="tablist" className="ml-auto inline-flex rounded-md border border-slate-300 p-0.5 text-sm">
          {(['all', 'admin', 'pending', 'disabled'] as const).map((f) => (
            <button
              key={f}
              role="tab"
              type="button"
              aria-selected={filter === f}
              onClick={() => setFilter(f)}
              className={cn(
                'rounded px-3 py-1',
                filter === f ? 'bg-slate-900 text-white' : 'text-slate-600 hover:text-slate-900',
              )}
            >
              {fr.users.filters[f]}
            </button>
          ))}
        </div>
      </div>
      {error && (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      {info && <p className="text-sm text-emerald-700">{info}</p>}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <Card className="divide-y divide-slate-100 overflow-hidden" data-testid="users">
          {list.length === 0 && <p className="p-4 text-sm text-slate-500">{fr.users.empty}</p>}
          {list.map((u) => (
            <button
              key={keyOf(u)}
              type="button"
              onClick={() => {
                setSelected(keyOf(u));
                setInfo(null);
              }}
              aria-pressed={selected === keyOf(u)}
              className={cn(
                'flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-slate-50',
                selected === keyOf(u) && 'bg-slate-100',
              )}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">
                  {u.name} {u.id === meId && fr.users.you}
                </span>
                <span className="block truncate text-xs text-slate-500">
                  {u.login} · {fr.users.usage(u.projects.length, u.agents.length)}
                </span>
              </span>
              <Badge tone={u.level === 'admin' ? 'info' : 'neutral'}>{fr.level[u.level]}</Badge>
              <Badge tone={statusTone(u.status)}>{fr.users.status[u.status]}</Badge>
            </button>
          ))}
        </Card>

        <Card className="p-4">
          {!sel && <p className="py-10 text-center text-sm text-slate-500">{fr.users.select}</p>}
          {sel && (
            <div className="space-y-4" data-testid="user-panel">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold">
                  {sel.name} {isMe && fr.users.you}
                </h2>
                <Badge tone={statusTone(sel.status)}>{fr.users.status[sel.status]}</Badge>
              </div>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-slate-500">{fr.users.email}</dt>
                <dd>{sel.login}</dd>
                <dt className="text-slate-500">{fr.users.source}</dt>
                <dd>{fr.users.sourceValue}</dd>
                <dt className="text-slate-500">{fr.users.teams}</dt>
                <dd>{sel.teams.length ? sel.teams.join(', ') : fr.users.none}</dd>
                <dt className="text-slate-500">{fr.users.first}</dt>
                <dd>{formatDate(sel.first_seen_at)}</dd>
                <dt className="text-slate-500">{fr.users.last}</dt>
                <dd>{seen(sel.last_seen_at)}</dd>
                <dt className="text-slate-500">{fr.users.level}</dt>
                <dd className="flex items-center gap-2">
                  {fr.level[sel.level]}
                  {isAdmin && sel.id && (
                    <Link href="/access" className="text-xs text-slate-600 underline">
                      {fr.users.manageAccess}
                    </Link>
                  )}
                </dd>
              </dl>

              <div>
                <h3 className="mb-1 text-sm font-medium">{fr.users.projects(sel.projects.length)}</h3>
                {sel.projects.length === 0 && (
                  <p className="text-sm text-slate-500">{fr.users.noProject}</p>
                )}
                <ul className="divide-y divide-slate-100 text-sm">
                  {sel.projects.map((p) => (
                    <li key={p.id} className="flex justify-between gap-2 py-1.5">
                      <Link href={`/projects/${p.id}`} className="truncate hover:underline">
                        {p.name}
                      </Link>
                      <span className="text-xs text-slate-500">
                        {fr.role[p.role] ?? p.role} {p.pending && fr.users.invitation}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <h3 className="mb-1 text-sm font-medium">{fr.users.agents(sel.agents.length)}</h3>
                {sel.agents.length === 0 ? (
                  <p className="text-sm text-slate-500">{fr.users.noAgent}</p>
                ) : (
                  <p className="text-sm">{sel.agents.join(', ')}</p>
                )}
              </div>

              {isAdmin && sel.id && (
                <div className="space-y-2 border-t border-slate-100 pt-3">
                  {isMe ? (
                    <p className="text-xs text-slate-500">{fr.users.isMe}</p>
                  ) : (
                    <>
                      <p className="text-xs text-slate-500">
                        {sel.level === 'admin'
                          ? fr.users.adminHint
                          : sel.status === 'disabled'
                            ? fr.users.disabledHint
                            : fr.users.disableHint}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant={sel.status === 'disabled' ? 'default' : 'destructive'}
                          disabled={
                            status.isPending || (sel.level === 'admin' && sel.status !== 'disabled')
                          }
                          onClick={() => {
                            const disable = sel.status !== 'disabled';
                            if (disable && !confirm(fr.users.confirmDisable(sel.name))) return;
                            status.mutate({ id: sel.id!, disabled: disable });
                          }}
                        >
                          {sel.status === 'disabled' ? fr.users.enable : fr.users.disable}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={revoke.isPending}
                          onClick={() => revoke.mutate(sel.id!)}
                        >
                          {fr.users.revoke}
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
