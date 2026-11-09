'use client';

// /projects/[id]/members ("Membres et accès"): visibility, teams and people with access.
// Priority: accepted individual role > highest team role > public read; admins own everything.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';

import { Badge, Button, Card, Input, cn } from '@/components/ui';
import {
  type ErrorBody,
  type PersonAccess,
  type ProjectMembers,
  ApiError,
  api,
  errorMessage,
  keys,
  unwrap,
} from '@/lib/api/client';
import { fr, visibilityText } from '@/lib/i18n/fr';

const selectClass =
  'h-8 rounded-md border border-slate-300 bg-white px-2 text-sm focus-visible:outline-2 focus-visible:outline-slate-400';

async function okOrThrow(r: { error?: unknown; response: Response }): Promise<void> {
  if (!r.response.ok) throw new ApiError(r.response.status, r.error as ErrorBody | undefined);
}

const roleLabel = (r: string | null | undefined) => (r ? (fr.role[r] ?? r) : fr.members.noAccess);

/** "Individuel : Lecteur (prioritaire) · via Data : Éditeur (remplacé)". */
export function personSources(p: PersonAccess): string {
  const individualWins = !!p.individual_role && !p.invitation_pending;
  const parts: string[] = [];
  if (p.individual_role) {
    parts.push(
      p.invitation_pending
        ? `${fr.members.individual(roleLabel(p.individual_role), false)} · ${fr.members.pending}`
        : fr.members.individual(roleLabel(p.individual_role), p.via_teams.length > 0),
    );
  }
  for (const t of p.via_teams) {
    parts.push(fr.members.viaTeam(t.name, roleLabel(t.role), individualWins));
  }
  const source = p.source ? fr.members.source[p.source] : undefined;
  if (source) parts.push(source);
  return parts.join(' · ');
}

export function MembersPage({ projectId, initial }: { projectId: string; initial: ProjectMembers }) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: keys.members(projectId),
    queryFn: () =>
      unwrap(api.GET('/api/projects/{id}/members', { params: { path: { id: projectId } } })),
    initialData: initial,
  });
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<'team' | 'user'>('team');
  const [teamPick, setTeamPick] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('editor');
  const refresh = () => {
    setError(null);
    void qc.invalidateQueries({ queryKey: keys.members(projectId) });
    void qc.invalidateQueries({ queryKey: keys.projects });
  };
  const onError = (e: unknown) => setError(errorMessage(e, fr.errors.generic, fr.errors.forbidden));
  const path = { params: { path: { id: projectId } } };
  const setVisibility = useMutation({
    mutationFn: (visibility: string) =>
      api.PUT('/api/projects/{id}/visibility', { ...path, body: { visibility } }).then(okOrThrow),
    onSuccess: refresh,
    onError,
  });
  const add = useMutation({
    mutationFn: (body: { kind: string; id: string; role: string }) =>
      api.POST('/api/projects/{id}/members', { ...path, body }).then(okOrThrow),
    onSuccess: () => {
      setEmail('');
      refresh();
    },
    onError,
  });
  const setRoleOf = useMutation({
    mutationFn: (v: { kind: string; subject: string; role: string }) =>
      api
        .PUT('/api/projects/{id}/members/{kind}/{subject}', {
          params: { path: { id: projectId, kind: v.kind, subject: v.subject } },
          body: { role: v.role },
        })
        .then(okOrThrow),
    onSuccess: refresh,
    onError,
  });
  const remove = useMutation({
    mutationFn: (v: { kind: string; subject: string }) =>
      api
        .DELETE('/api/projects/{id}/members/{kind}/{subject}', {
          params: { path: { id: projectId, kind: v.kind, subject: v.subject } },
        })
        .then(okOrThrow),
    onSuccess: refresh,
    onError,
  });

  const manage = data.can_manage;
  const team = teamPick || data.available_teams[0]?.id || '';
  const roles = kind === 'team' ? ['editor', 'viewer'] : ['owner', 'editor', 'viewer'];
  const pickedRole = roles.includes(role) ? role : 'editor';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link href={`/projects/${projectId}`} className="text-sm text-slate-600 hover:underline">
          ← {fr.members.back}
        </Link>
        <h1 className="text-xl font-semibold">{fr.members.title}</h1>
        <Badge tone={data.visibility === 'public' ? 'info' : 'neutral'}>
          {visibilityText(data.visibility)[0]}
        </Badge>
        <span className="ml-auto text-sm text-slate-500">{roleLabel(data.my_role)}</span>
      </div>
      {error && (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="space-y-4">
          <Card className="space-y-3 p-4">
            <h2 className="text-sm font-semibold">{fr.members.visibility}</h2>
            <div className="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label={fr.members.visibility}>
              {(['private', 'public'] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  role="radio"
                  aria-checked={data.visibility === v}
                  disabled={!manage || setVisibility.isPending}
                  onClick={() => setVisibility.mutate(v)}
                  className={cn(
                    'rounded-md border p-3 text-left text-sm disabled:cursor-default',
                    data.visibility === v ? 'border-slate-900 bg-slate-50' : 'border-slate-200',
                  )}
                >
                  <span className="block font-medium">{fr.projects.visibility[v][0]}</span>
                  <span className="block text-xs text-slate-500">{fr.projects.visibility[v][1]}</span>
                </button>
              ))}
            </div>
            {!manage && <p className="text-xs text-slate-500">{fr.members.readOnly}</p>}
          </Card>

          {manage && (
            <Card className="space-y-3 p-4">
              <h2 className="text-sm font-semibold">{fr.members.give}</h2>
              <div role="tablist" className="inline-flex rounded-md border border-slate-300 p-0.5 text-sm">
                {(['team', 'user'] as const).map((k) => (
                  <button
                    key={k}
                    role="tab"
                    type="button"
                    aria-selected={kind === k}
                    onClick={() => setKind(k)}
                    className={cn(
                      'rounded px-3 py-1',
                      kind === k ? 'bg-slate-900 text-white' : 'text-slate-600 hover:text-slate-900',
                    )}
                  >
                    {k === 'team' ? fr.members.kindTeam : fr.members.kindPerson}
                  </button>
                ))}
              </div>
              <form
                className="flex flex-wrap items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  const id = kind === 'team' ? team : email.trim();
                  if (id) add.mutate({ kind, id, role: pickedRole });
                }}
              >
                {kind === 'team' ? (
                  data.available_teams.length ? (
                    <select
                      className={selectClass}
                      aria-label={fr.members.team}
                      value={team}
                      onChange={(e) => setTeamPick(e.target.value)}
                    >
                      {data.available_teams.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name} ({fr.access.members(t.member_count)})
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-sm text-slate-500">{fr.members.noTeamLeft}</span>
                  )
                ) : (
                  <Input
                    className="max-w-xs"
                    type="email"
                    aria-label={fr.members.email}
                    placeholder="prenom.nom@hellopro.fr"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                )}
                <select
                  className={selectClass}
                  aria-label={fr.members.role}
                  value={pickedRole}
                  onChange={(e) => setRole(e.target.value)}
                >
                  {roles.map((r) => (
                    <option key={r} value={r}>
                      {fr.role[r]}
                    </option>
                  ))}
                </select>
                <Button type="submit" size="sm" disabled={add.isPending || (kind === 'team' && !team)}>
                  {kind === 'team' ? fr.members.grantTeam : fr.members.invite}
                </Button>
              </form>
              <p className="text-xs text-slate-500">
                {kind === 'team' ? fr.members.teamHint : fr.members.personHint}
              </p>
            </Card>
          )}

          <Card className="space-y-2 p-4">
            <dl className="space-y-1 text-xs">
              {fr.members.rules.map(([term, value]) => (
                <div key={term}>
                  <dt className="inline font-medium">{term} : </dt>
                  <dd className="inline text-slate-600">{value}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="p-4">
            <h2 className="mb-2 text-sm font-semibold">{fr.members.teams(data.teams.length)}</h2>
            {data.teams.length === 0 && <p className="text-sm text-slate-500">{fr.members.noTeams}</p>}
            <ul className="divide-y divide-slate-100">
              {data.teams.map((t) => (
                <li key={t.id} className="flex items-center gap-2 py-2 text-sm">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{t.name}</span>
                    <span className="block text-xs text-slate-500">{fr.access.members(t.member_count)}</span>
                  </span>
                  {manage ? (
                    <select
                      className={selectClass}
                      aria-label={`${fr.members.role} : ${t.name}`}
                      value={t.role}
                      onChange={(e) =>
                        setRoleOf.mutate({ kind: 'team', subject: t.id, role: e.target.value })
                      }
                    >
                      <option value="editor">{fr.role.editor}</option>
                      <option value="viewer">{fr.role.viewer}</option>
                    </select>
                  ) : (
                    <Badge>{roleLabel(t.role)}</Badge>
                  )}
                  {manage && (
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={fr.members.removeTeam(t.name)}
                      title={fr.members.removeTeam(t.name)}
                      onClick={() => remove.mutate({ kind: 'team', subject: t.id })}
                    >
                      ✕
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </Card>

          <Card className="p-4">
            <h2 className="mb-2 text-sm font-semibold">{fr.members.people(data.people.length)}</h2>
            <ul className="divide-y divide-slate-100" data-testid="people">
              {data.people.map((p) => (
                <li key={p.subject} className="flex items-start gap-2 py-2 text-sm">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">
                      {p.name}
                      {!p.user_id && (
                        <span className="ml-1 text-xs font-normal text-slate-500">
                          · {fr.members.notSignedIn}
                        </span>
                      )}
                    </span>
                    <span className="block text-xs text-slate-500">{personSources(p)}</span>
                    {p.agents.length > 0 && (
                      <span className="block text-xs text-slate-500">{fr.members.agents(p.agents)}</span>
                    )}
                  </span>
                  <Badge
                    tone={
                      p.effective_role === 'owner'
                        ? 'ok'
                        : p.effective_role === 'editor'
                          ? 'info'
                          : 'neutral'
                    }
                  >
                    {roleLabel(p.effective_role)}
                  </Badge>
                  {manage && p.individual_role && (
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={fr.members.remove(p.name)}
                      title={fr.members.remove(p.name)}
                      onClick={() => remove.mutate({ kind: 'user', subject: p.subject })}
                    >
                      ✕
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
