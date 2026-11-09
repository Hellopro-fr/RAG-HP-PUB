'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';

import { Badge, Button, Card, Input, cn } from '@/components/ui';
import {
  type ErrorBody,
  type InvitationView,
  type ProjectView,
  ApiError,
  api,
  errorMessage,
  keys,
  unwrap,
} from '@/lib/api/client';
import { formatDate, fr, visibilityText } from '@/lib/i18n/fr';

type Filter = 'all' | 'member' | 'public';

export function matchesFilter(p: Pick<ProjectView, 'visibility' | 'my_role'>, f: Filter): boolean {
  if (f === 'public') return p.visibility === 'public';
  if (f === 'member') return p.my_role === 'owner' || p.my_role === 'editor';
  return true;
}

async function okOrThrow(r: { error?: unknown; response: Response }): Promise<void> {
  if (!r.response.ok) throw new ApiError(r.response.status, r.error as ErrorBody | undefined);
}

export function ProjectList({
  initial,
  canCreate,
  invitations,
}: {
  initial: ProjectView[];
  canCreate: boolean;
  invitations: InvitationView[];
}) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: keys.projects,
    queryFn: () => unwrap(api.GET('/api/projects')),
    initialData: initial,
  });
  const invites = useQuery({
    queryKey: keys.invitations,
    queryFn: () => unwrap(api.GET('/api/invitations')),
    initialData: invitations,
  });
  const [name, setName] = useState('');
  const [visibility, setVisibility] = useState<'private' | 'public'>('private');
  const [filter, setFilter] = useState<Filter>('all');
  const [error, setError] = useState<string | null>(null);
  const onError = (e: unknown) => setError(errorMessage(e, fr.errors.generic, fr.errors.forbidden));
  const create = useMutation({
    mutationFn: (n: string) =>
      unwrap(api.POST('/api/projects', { body: { name: n, visibility } })),
    onSuccess: () => {
      setName('');
      setError(null);
      void qc.invalidateQueries({ queryKey: keys.projects });
    },
    onError,
  });
  const answer = useMutation({
    mutationFn: (v: { projectId: string; accept: boolean }) =>
      (v.accept
        ? api.POST('/api/invitations/{project_id}/accept', {
            params: { path: { project_id: v.projectId } },
          })
        : api.POST('/api/invitations/{project_id}/decline', {
            params: { path: { project_id: v.projectId } },
          })
      ).then(okOrThrow),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.invitations });
      void qc.invalidateQueries({ queryKey: keys.projects });
    },
    onError,
  });
  const shown = data.filter((p) => matchesFilter(p, filter));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{fr.projects.title}</h1>
        <Badge>{data.length}</Badge>
        <div role="tablist" className="ml-auto inline-flex rounded-md border border-slate-300 p-0.5 text-sm">
          {(['all', 'member', 'public'] as const).map((f) => (
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
              {fr.projects.filters[f]}
            </button>
          ))}
        </div>
      </div>

      {invites.data.map((inv) => (
        <div
          key={inv.project_id}
          className="flex flex-wrap items-center gap-3 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900"
          data-testid="invitation"
        >
          <span className="flex-1">
            {fr.projects.invitation(inv.project_name, fr.role[inv.role] ?? inv.role, inv.invited_by)}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={answer.isPending}
            onClick={() => answer.mutate({ projectId: inv.project_id, accept: false })}
          >
            {fr.projects.decline}
          </Button>
          <Button
            size="sm"
            disabled={answer.isPending}
            onClick={() => answer.mutate({ projectId: inv.project_id, accept: true })}
          >
            {fr.projects.accept}
          </Button>
        </div>
      ))}

      {canCreate && (
        <form
          className="flex max-w-2xl flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) create.mutate(name.trim());
          }}
        >
          <Input
            className="max-w-xs"
            aria-label={fr.projects.name}
            placeholder={fr.projects.name}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <select
            aria-label={fr.members.visibility}
            className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
            value={visibility}
            onChange={(e) => setVisibility(e.target.value as 'private' | 'public')}
          >
            <option value="private">{fr.projects.visibility.private[0]}</option>
            <option value="public">{fr.projects.visibility.public[0]}</option>
          </select>
          <Button type="submit" disabled={create.isPending}>
            {fr.projects.create}
          </Button>
          <span className="w-full text-xs text-slate-500">{fr.projects.visibility[visibility][1]}</span>
        </form>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {data.length === 0 && <p className="text-slate-500">{fr.projects.empty}</p>}
      {data.length > 0 && shown.length === 0 && (
        <p className="text-slate-500">{fr.projects.emptyFilter}</p>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((p) => (
          <Card key={p.id} className="space-y-2 p-4">
            <div className="flex items-start justify-between gap-2">
              <Link href={`/projects/${p.id}`} className="font-medium hover:underline" data-testid="project-link">
                {p.name}
              </Link>
              <Badge tone={p.visibility === 'public' ? 'info' : 'neutral'}>
                {visibilityText(p.visibility)[0]}
              </Badge>
            </div>
            <p className="flex items-center justify-between text-xs text-slate-500">
              <span>{formatDate(p.created_at)}</span>
              {p.my_role && <span>{fr.role[p.my_role] ?? p.my_role}</span>}
            </p>
            <Link href={`/projects/${p.id}/members`} className="text-xs text-slate-600 hover:underline">
              {fr.projects.members}
            </Link>
          </Card>
        ))}
      </div>
    </div>
  );
}
