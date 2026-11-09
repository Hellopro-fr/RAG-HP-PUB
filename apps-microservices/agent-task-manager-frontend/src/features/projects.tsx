'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';

import { Button, Card, Input } from '@/components/ui';
import { type ProjectView, api, errorMessage, keys, unwrap } from '@/lib/api/client';
import { formatDate, fr } from '@/lib/i18n/fr';

export function ProjectList({ initial, canCreate }: { initial: ProjectView[]; canCreate: boolean }) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: keys.projects,
    queryFn: () => unwrap(api.GET('/api/projects')),
    initialData: initial,
  });
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: (n: string) => unwrap(api.POST('/api/projects', { body: { name: n } })),
    onSuccess: () => {
      setName('');
      void qc.invalidateQueries({ queryKey: keys.projects });
    },
    onError: (e) => setError(errorMessage(e, fr.errors.generic, fr.errors.forbidden)),
  });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{fr.projects.title}</h1>
      {canCreate && (
      <form
        className="flex max-w-md gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) create.mutate(name.trim());
        }}
      >
        <Input aria-label={fr.projects.name} placeholder={fr.projects.name} value={name} onChange={(e) => setName(e.target.value)} />
        <Button type="submit" disabled={create.isPending}>
          {fr.projects.create}
        </Button>
      </form>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {data.length === 0 && <p className="text-slate-500">{fr.projects.empty}</p>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {data.map((p) => (
          <Card key={p.id} className="space-y-1 p-4">
            <Link href={`/projects/${p.id}`} className="font-medium hover:underline" data-testid="project-link">
              {p.name}
            </Link>
            <p className="text-xs text-slate-500">{formatDate(p.created_at)}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}
