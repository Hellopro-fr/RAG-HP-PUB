'use client';

// /projects/[id]: one column per state (§10). Cards show title, priority, holder with lease
// countdown, blocked / spec-outdated badges, attempt number, open-question marker.
// No optimistic transitions: a drop sends the command; the card moves when the event arrives.

import { useMutation, useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useEffect, useState } from 'react';

import { Badge, Card, cn } from '@/components/ui';
import { type ActorView, type Board, type TaskView, ApiError, api, keys, unwrap } from '@/lib/api/client';
import { STATE_ORDER, type TaskState, formatRemaining, fr } from '@/lib/i18n/fr';
import { type StreamStatus, useLiveBoard } from '@/realtime/stream';

const TERMINAL: TaskState[] = ['done', 'failed', 'cancelled'];

export function LeaseCountdown({ expiresAt, paused }: { expiresAt: string; paused: boolean }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  if (paused) return <span className="text-slate-500">{fr.board.leasePaused}</span>;
  const left = new Date(expiresAt).getTime() - now;
  return (
    <span className={cn(left < 60_000 ? 'text-red-600' : 'text-slate-500')} data-testid="lease-countdown">
      {left > 0 ? fr.board.leaseLeft(formatRemaining(left)) : fr.board.leaseExpired}
    </span>
  );
}

function TaskCard({ task, pending }: { task: TaskView; pending: boolean }) {
  return (
    <Card
      draggable={!TERMINAL.includes(task.state as TaskState)}
      onDragStart={(e) => e.dataTransfer.setData('text/task-id', task.id)}
      data-testid="task-card"
      data-task-id={task.id}
      data-state={task.state}
      className={cn('cursor-grab space-y-1.5 p-3 text-sm', pending && 'opacity-60')}
    >
      <div className="flex items-start justify-between gap-2">
        <Link href={`/tasks/${task.id}`} className="font-medium hover:underline">
          {task.title}
        </Link>
        <Badge>{fr.board.priority(task.priority)}</Badge>
      </div>
      <div className="flex flex-wrap gap-1">
        {task.blocked && <Badge tone="warn">{fr.board.blocked}</Badge>}
        {task.spec_outdated && <Badge tone="danger">{fr.board.specOutdated}</Badge>}
        {task.attempt_count > 0 && <Badge tone="neutral">{fr.board.attempt(task.attempt_count)}</Badge>}
        {task.open_questions > 0 && (
          <Badge tone={task.blocking_questions > 0 ? 'danger' : 'info'}>
            ? {fr.board.questions(task.open_questions)}
          </Badge>
        )}
        {task.preferred_actor_id && task.state === 'ready' && <Badge tone="info">{fr.board.reservedFor}</Badge>}
      </div>
      {task.lease && (
        <div className="flex items-center justify-between text-xs" data-testid="task-holder">
          <span className="font-medium text-slate-700">{task.lease.actor_name}</span>
          <LeaseCountdown expiresAt={task.lease.expires_at} paused={task.lease.paused} />
        </div>
      )}
      {pending && <p className="text-xs text-slate-500">{fr.board.pending}</p>}
    </Card>
  );
}

function StatusDot({ status }: { status: StreamStatus }) {
  const live = status === 'live';
  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-600" data-testid="stream-status" data-status={status}>
      <span className={cn('h-2 w-2 rounded-full', live ? 'bg-emerald-500' : 'bg-amber-500')} />
      {live ? fr.board.live : fr.board.reconnecting}
    </span>
  );
}

export function BoardView({ projectId, initial }: { projectId: string; initial: Board }) {
  const board = useQuery({
    queryKey: keys.board(projectId),
    queryFn: () => unwrap(api.GET('/api/projects/{id}/board', { params: { path: { id: projectId } } })),
    initialData: initial,
    staleTime: Infinity,
  });
  useQuery({
    queryKey: keys.actors,
    queryFn: () => unwrap<ActorView[]>(api.GET('/api/actors')),
  });
  const status = useLiveBoard(projectId, initial.seq);
  const [notice, setNotice] = useState<string | null>(null);
  const cancel = useMutation({
    mutationFn: (taskId: string) =>
      unwrap(api.POST('/api/tasks/{id}/cancel', { params: { path: { id: taskId } }, body: {} })),
    onError: (e) => setNotice(e instanceof ApiError ? e.message : fr.errors.generic),
  });

  const onDrop = (state: TaskState, taskId: string) => {
    setNotice(null);
    if (state !== 'cancelled') {
      setNotice(fr.board.dropNotAllowed);
      return;
    }
    if (window.confirm(fr.board.confirmCancel)) cancel.mutate(taskId);
  };

  const tasks = board.data.tasks;
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{board.data.project.name}</h1>
        <StatusDot status={status} />
      </div>
      {notice && (
        <p role="status" className="rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {notice}
        </p>
      )}
      <div className="flex gap-3 overflow-x-auto pb-4">
        {STATE_ORDER.map((state) => {
          const column = tasks.filter((t) => t.state === state);
          return (
            <section
              key={state}
              data-testid={`column-${state}`}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => onDrop(state, e.dataTransfer.getData('text/task-id'))}
              className="w-64 shrink-0 space-y-2 rounded-lg bg-slate-100 p-2"
            >
              <h2 className="flex justify-between px-1 text-xs font-semibold uppercase tracking-wide text-slate-600">
                {fr.state[state]} <span>{column.length}</span>
              </h2>
              {column.map((t) => (
                <TaskCard key={t.id} task={t} pending={cancel.isPending && cancel.variables === t.id} />
              ))}
            </section>
          );
        })}
      </div>
    </div>
  );
}
