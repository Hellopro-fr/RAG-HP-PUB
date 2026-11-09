'use client';

// /access ("Accès", admins only): levels and permissions per user and per team.
// Priority: individual setting > teams (one team allowing is enough) > refused. Admins: everything.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useState } from 'react';

import { Badge, Card, cn } from '@/components/ui';
import {
  type AccessOverview,
  type ErrorBody,
  type SourceView,
  ApiError,
  api,
  errorMessage,
  keys,
  unwrap,
} from '@/lib/api/client';
import { fr } from '@/lib/i18n/fr';

type Kind = 'user' | 'team';

const selectClass =
  'h-8 rounded-md border border-slate-300 bg-white px-2 text-sm focus-visible:outline-2 focus-visible:outline-slate-400 disabled:bg-slate-50 disabled:text-slate-400';

function permLabel(key: string): [string, string] {
  return fr.access.perms[key] ?? [key, ''];
}

export function sourceText(s: SourceView): string {
  const names = s.teams.join(', ');
  switch (s.kind) {
    case 'admin_level':
      return fr.access.source.admin_level;
    case 'admin_only':
      return fr.access.source.admin_only;
    case 'individual': {
      const teams =
        s.teams_outcome === 'allowed' ? 'autorisé' : s.teams_outcome === 'denied' ? 'refusé' : '';
      return fr.access.source.individual(teams);
    }
    case 'teams':
      return s.teams_outcome === 'allowed'
        ? fr.access.source.teamsAllowed(names)
        : fr.access.source.teamsDenied(names);
    default:
      return fr.access.source.default;
  }
}

/** PUT endpoints answer 204 (no body): turn an error status into an exception for useMutation. */
async function okOrThrow(r: { error?: unknown; response: Response }): Promise<void> {
  if (!r.response.ok) throw new ApiError(r.response.status, r.error as ErrorBody | undefined);
}

export function AccessPage({ initial, meId }: { initial: AccessOverview; meId: string }) {
  const { data } = useQuery({
    queryKey: keys.access,
    queryFn: () => unwrap(api.GET('/api/access')),
    initialData: initial,
  });
  const [kind, setKind] = useState<Kind>('user');
  const [selected, setSelected] = useState<string | null>(null);

  const pick = (k: Kind) => {
    setKind(k);
    setSelected(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{fr.access.title}</h1>
        <div role="tablist" className="inline-flex rounded-md border border-slate-300 p-0.5 text-sm">
          {(['user', 'team'] as const).map((k) => (
            <button
              key={k}
              role="tab"
              type="button"
              aria-selected={kind === k}
              className={cn(
                'rounded px-3 py-1',
                kind === k ? 'bg-slate-900 text-white' : 'text-slate-600 hover:text-slate-900',
              )}
              onClick={() => pick(k)}
            >
              {k === 'user' ? fr.access.users : fr.access.teams}
            </button>
          ))}
        </div>
      </div>
      <p className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900">
        {fr.access.priority}
      </p>
      {!data.directory_enabled && (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {fr.access.noDirectory}
        </p>
      )}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <Card className="divide-y divide-slate-100 overflow-hidden" data-testid="access-subjects">
          {kind === 'user'
            ? data.users.map((u) => (
                <SubjectRow
                  key={u.id}
                  active={selected === u.id}
                  onClick={() => setSelected(u.id)}
                  title={u.name}
                  meta={u.teams.length ? u.teams.map((t) => t.name).join(', ') : fr.access.noTeam}
                  badge={
                    <Badge tone={u.level === 'admin' ? 'info' : 'neutral'}>{fr.level[u.level]}</Badge>
                  }
                />
              ))
            : data.teams.map((t) => (
                <SubjectRow
                  key={t.id}
                  active={selected === t.id}
                  onClick={() => setSelected(t.id)}
                  title={t.name}
                  meta={t.description || fr.access.members(t.member_count)}
                  badge={<Badge>{fr.access.members(t.member_count)}</Badge>}
                />
              ))}
          {kind === 'team' && data.teams.length === 0 && (
            <p className="p-4 text-sm text-slate-500">{fr.access.noTeam}</p>
          )}
        </Card>
        <Card className="p-4">
          {!selected && <p className="py-10 text-center text-sm text-slate-500">{fr.access.select}</p>}
          {selected && kind === 'user' && <UserPanel id={selected} meId={meId} />}
          {selected && kind === 'team' && <TeamPanel id={selected} />}
        </Card>
      </div>
    </div>
  );
}

function SubjectRow(props: {
  active: boolean;
  onClick: () => void;
  title: string;
  meta: string;
  badge: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={props.onClick}
      aria-pressed={props.active}
      className={cn(
        'flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-slate-50',
        props.active && 'bg-slate-100',
      )}
    >
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{props.title}</span>
        <span className="block truncate text-xs text-slate-500">{props.meta}</span>
      </span>
      {props.badge}
    </button>
  );
}

function useAccessMutation() {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const done = {
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: keys.access });
    },
    onError: (e: unknown) => setError(errorMessage(e, fr.errors.generic, fr.errors.forbidden)),
  };
  return { error, done };
}

function UserPanel({ id, meId }: { id: string; meId: string }) {
  const { data } = useQuery({
    queryKey: keys.accessUser(id),
    queryFn: () => unwrap(api.GET('/api/access/users/{id}', { params: { path: { id } } })),
  });
  const { error, done } = useAccessMutation();
  const setting = useMutation({
    mutationFn: (v: { permission: string; effect: string | null }) =>
      api
        .PUT('/api/access/users/{id}/permissions/{permission}', {
          params: { path: { id, permission: v.permission } },
          body: { effect: v.effect },
        })
        .then(okOrThrow),
    ...done,
  });
  const level = useMutation({
    mutationFn: (l: string) =>
      api
        .PUT('/api/access/users/{id}/level', { params: { path: { id } }, body: { level: l } })
        .then(okOrThrow),
    ...done,
  });
  if (!data) return <p className="text-sm text-slate-500">…</p>;
  const isAdmin = data.user.level === 'admin';
  const self = id === meId;
  return (
    <div className="space-y-4" data-testid="user-panel">
      <div>
        <h2 className="text-base font-semibold">{data.user.name}</h2>
        <p className="text-xs text-slate-500">
          {data.user.login ?? '—'}
          {data.user.teams.length > 0 && ` · ${data.user.teams.map((t) => t.name).join(', ')}`}
        </p>
      </div>
      <label className="flex flex-wrap items-center gap-3 text-sm">
        <span className="font-medium">{fr.access.level}</span>
        <select
          className={selectClass}
          value={data.user.level}
          disabled={self || level.isPending}
          onChange={(e) => level.mutate(e.target.value)}
        >
          <option value="admin">{fr.level.admin}</option>
          <option value="classic">{fr.level.classic}</option>
        </select>
        <span className="text-xs text-slate-500">
          {self ? fr.access.levelSelf : isAdmin ? fr.access.levelHint : ''}
        </span>
      </label>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-slate-500">
          <tr>
            <th className="py-1">{fr.access.permission}</th>
            <th className="py-1">{fr.access.setting}</th>
            <th className="py-1">{fr.access.effective}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {data.permissions.map((p) => {
            const [label, help] = permLabel(p.permission);
            const locked = p.permission === 'access.manage';
            return (
              <tr key={p.permission} data-testid={`perm-${p.permission}`}>
                <td className="py-2 pr-2">
                  <span className="block">{label}</span>
                  {help && <span className="block text-xs text-slate-500">{help}</span>}
                </td>
                <td className="py-2 pr-2">
                  {locked ? (
                    <span className="text-xs text-slate-500">{fr.access.adminOnly}</span>
                  ) : (
                    <select
                      className={selectClass}
                      aria-label={`${fr.access.setting} : ${label}`}
                      value={p.setting ?? ''}
                      disabled={isAdmin || setting.isPending}
                      onChange={(e) =>
                        setting.mutate({ permission: p.permission, effect: e.target.value || null })
                      }
                    >
                      <option value="">{fr.access.inherit}</option>
                      <option value="allow">{fr.access.allow}</option>
                      <option value="deny">{fr.access.deny}</option>
                    </select>
                  )}
                </td>
                <td className="py-2">
                  <Badge tone={p.allowed ? 'ok' : 'neutral'}>
                    {p.allowed ? fr.access.allow : fr.access.deny}
                  </Badge>
                  <span className="block text-xs text-slate-500">{sourceText(p.source)}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TeamPanel({ id }: { id: string }) {
  const { data } = useQuery({
    queryKey: keys.accessTeam(id),
    queryFn: () => unwrap(api.GET('/api/access/teams/{id}', { params: { path: { id } } })),
  });
  const { error, done } = useAccessMutation();
  const setting = useMutation({
    mutationFn: (v: { permission: string; effect: string | null }) =>
      api
        .PUT('/api/access/teams/{id}/permissions/{permission}', {
          params: { path: { id, permission: v.permission } },
          body: { effect: v.effect },
        })
        .then(okOrThrow),
    ...done,
  });
  if (!data) return <p className="text-sm text-slate-500">…</p>;
  return (
    <div className="space-y-4" data-testid="team-panel">
      <div>
        <h2 className="text-base font-semibold">{data.team.name}</h2>
        <p className="text-xs text-slate-500">
          {data.team.description || fr.access.members(data.team.member_count)}
        </p>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-slate-500">
          <tr>
            <th className="py-1">{fr.access.permission}</th>
            <th className="py-1">{fr.access.setting}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {data.permissions.map((p) => {
            const [label, help] = permLabel(p.permission);
            return (
              <tr key={p.permission} data-testid={`perm-${p.permission}`}>
                <td className="py-2 pr-2">
                  <span className="block">{label}</span>
                  {help && <span className="block text-xs text-slate-500">{help}</span>}
                  {p.exceptions > 0 && (
                    <span className="block text-xs text-amber-700">
                      {fr.access.exceptions(p.exceptions)}
                    </span>
                  )}
                </td>
                <td className="py-2">
                  <select
                    className={selectClass}
                    aria-label={`${fr.access.setting} : ${label}`}
                    value={p.setting ?? ''}
                    disabled={setting.isPending}
                    onChange={(e) =>
                      setting.mutate({ permission: p.permission, effect: e.target.value || null })
                    }
                  >
                    <option value="">{fr.access.unset}</option>
                    <option value="allow">{fr.access.allow}</option>
                    <option value="deny">{fr.access.deny}</option>
                  </select>
                </td>
              </tr>
            );
          })}
          <tr>
            <td className="py-2 pr-2">{permLabel('access.manage')[0]}</td>
            <td className="py-2 text-xs text-slate-500">{fr.access.adminOnly}</td>
          </tr>
        </tbody>
      </table>
      <div>
        <h3 className="mb-1 text-sm font-medium">{fr.access.members(data.members.length)}</h3>
        <ul className="divide-y divide-slate-100 text-sm">
          {data.members.map((m) => (
            <li key={m.email} className="flex justify-between gap-2 py-1.5">
              <span className="truncate">{m.name}</span>
              <span className="truncate text-xs text-slate-500">
                {m.user_id ? m.email : `${m.email} · ${fr.access.notSignedIn}`}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
