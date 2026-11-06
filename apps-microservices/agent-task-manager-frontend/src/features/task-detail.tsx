'use client';

// /tasks/[id]: spec version with its acceptance criteria, timeline from events (thoughts
// collapsed; questions and results prominent), attempts with commit / handoff / trace, and an
// answer form for open questions (§10).

import { useMutation, useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';

import { Badge, Button, Card } from '@/components/ui';
import { type StoredEvent, type TaskContext, ApiError, api, keys, unwrap } from '@/lib/api/client';
import { type TaskState, formatDate, fr } from '@/lib/i18n/fr';
import { useLiveTask } from '@/realtime/stream';

import { LeaseCountdown } from './board';
import { AnswerForm } from './questions';

type Ac = { id: string; text: string; verify?: { kind?: string } };

function describe(ev: StoredEvent): string {
  const p = (ev.payload ?? {}) as Record<string, unknown>;
  switch (ev.type) {
    case 'task.state_changed':
      return `${fr.state[p.from as TaskState] ?? p.from} → ${fr.state[p.to as TaskState] ?? p.to}`;
    case 'activity.reported':
      return `[${String(p.kind)}] ${String(p.body ?? '')}`;
    case 'question.asked':
      return `${p.blocking ? '⛔ ' : ''}${String(p.body ?? '')}`;
    case 'question.answered':
      return String(p.answer ?? '');
    case 'lease.expired':
    case 'attempt.ended':
      return String(p.handoff_note ?? p.outcome ?? '');
    default:
      return '';
  }
}

function Timeline({ taskId }: { taskId: string }) {
  const [showThoughts, setShowThoughts] = useState(false);
  const { data = [] } = useQuery({
    queryKey: keys.timeline(taskId),
    queryFn: () => unwrap(api.GET('/api/tasks/{id}/timeline', { params: { path: { id: taskId } } })),
  });
  const visible = data.filter(
    (e) => showThoughts || !(e.type === 'activity.reported' && (e.payload as { kind?: string }).kind === 'thought'),
  );
  return (
    <Card className="space-y-2 p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">{fr.task.timeline}</h2>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={showThoughts} onChange={(e) => setShowThoughts(e.target.checked)} />
          {fr.task.showThoughts}
        </label>
      </div>
      <ol className="space-y-1.5 text-sm" data-testid="timeline">
        {visible.map((e) => {
          const prominent = e.type.startsWith('question.') || e.type.startsWith('test.') || e.type.startsWith('review.');
          return (
            <li key={e.seq} className={prominent ? 'rounded bg-amber-50 px-2 py-1' : 'px-2'}>
              <span className="mr-2 text-xs text-slate-400">#{e.seq} {formatDate(e.created_at)}</span>
              <span className="font-medium">{fr.event[e.type] ?? e.type}</span>{' '}
              <span className="whitespace-pre-wrap text-slate-700">{describe(e)}</span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

export function TaskDetail({ initial }: { initial: TaskContext }) {
  const taskId = initial.task.id;
  const { data: ctx } = useQuery({
    queryKey: keys.task(taskId),
    queryFn: () => unwrap(api.GET('/api/tasks/{id}', { params: { path: { id: taskId } } })),
    initialData: initial,
  });
  useLiveTask(ctx.task.project_id, taskId);
  const [error, setError] = useState<string | null>(null);
  const cancel = useMutation({
    mutationFn: () => unwrap(api.POST('/api/tasks/{id}/cancel', { params: { path: { id: taskId } }, body: {} })),
    onError: (e) => setError(e instanceof ApiError ? e.message : fr.errors.generic),
  });
  const t = ctx.task;
  const acs = (Array.isArray(ctx.spec?.acceptance_criteria) ? ctx.spec?.acceptance_criteria : []) as Ac[];
  const terminal = ['done', 'failed', 'cancelled'].includes(t.state);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link className="text-sm text-slate-500 hover:underline" href={`/projects/${t.project_id}`}>
          ← {fr.nav.projects}
        </Link>
        <h1 className="text-xl font-semibold">{t.title}</h1>
        <Badge tone="info" data-testid="task-state">
          {fr.state[t.state as TaskState] ?? t.state}
        </Badge>
        {t.blocked && <Badge tone="warn">{fr.board.blocked}</Badge>}
        {t.spec_outdated && <Badge tone="danger">{fr.board.specOutdated}</Badge>}
        {!terminal && (
          <Button
            variant="destructive"
            size="sm"
            disabled={cancel.isPending}
            onClick={() => window.confirm(fr.board.confirmCancel) && cancel.mutate()}
          >
            {fr.task.cancel}
          </Button>
        )}
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {t.lease && (
        <p className="text-sm">
          {fr.task.holder} : <strong>{t.lease.actor_name}</strong> ·{' '}
          <LeaseCountdown expiresAt={t.lease.expires_at} paused={t.lease.paused} />
        </p>
      )}
      {ctx.blockers.length > 0 && (
        <p className="text-sm">
          {fr.task.blockers} :{' '}
          {ctx.blockers.map((b) => (
            <Link key={b.id} href={`/tasks/${b.id}`} className="mr-2 underline">
              {b.title} ({fr.state[b.state as TaskState] ?? b.state})
            </Link>
          ))}
        </p>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="space-y-3 p-4">
          <h2 className="font-semibold">
            {fr.task.spec} v{t.spec_version}
          </h2>
          <p className="whitespace-pre-wrap text-sm text-slate-700">{ctx.spec?.body_md}</p>
          <h3 className="text-sm font-semibold">{fr.task.criteria}</h3>
          <ul className="space-y-1 text-sm" data-testid="criteria">
            {acs.map((ac) => (
              <li key={ac.id}>
                <Badge>{ac.id}</Badge> {ac.text}{' '}
                <span className="text-xs text-slate-500">({ac.verify?.kind}, {fr.task.notVerified})</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="space-y-3 p-4">
          <h2 className="font-semibold">{fr.task.questions}</h2>
          {ctx.questions.length === 0 && <p className="text-sm text-slate-500">{fr.task.none}</p>}
          {ctx.questions.map((q) => (
            <div key={q.id} className="space-y-1 border-b border-slate-100 pb-2 text-sm">
              <p>
                {q.blocking && <Badge tone="danger">{fr.questions.blocking}</Badge>} {q.body}{' '}
                <span className="text-slate-500">({fr.questions.askedBy(q.asked_by_name)})</span>
              </p>
              {q.status === 'open' ? <AnswerForm question={q} /> : <p className="text-emerald-700">→ {q.answer}</p>}
            </div>
          ))}
        </Card>
      </div>
      <Card className="p-4">
        <h2 className="mb-2 font-semibold">{fr.task.attempts}</h2>
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-500">
            <tr>
              <th>#</th>
              <th>{fr.agents.actor}</th>
              <th>{fr.task.commit}</th>
              <th>{fr.task.handoff}</th>
              <th>{fr.task.trace}</th>
            </tr>
          </thead>
          <tbody>
            {ctx.attempts.map((a) => (
              <tr key={a.id} className="border-t border-slate-100 align-top">
                <td>{a.n}</td>
                <td>
                  {a.actor_name} <span className="text-xs text-slate-500">{a.outcome ?? '…'}</span>
                </td>
                <td className="font-mono text-xs">{a.commit_sha ?? fr.task.none}</td>
                <td className="whitespace-pre-wrap">{a.handoff_note ?? fr.task.none}</td>
                <td className="font-mono text-xs">{a.trace_id ?? fr.task.none}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Timeline taskId={taskId} />
    </div>
  );
}
