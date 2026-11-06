// The ONLY place where live events change cached data. Pure: (board, event) -> new board.
// The server decides everything; the client mirrors committed events in seq order.

import type { Board, StoredEvent, TaskView } from '@/lib/api/client';

export type ApplyResult = {
  board: Board;
  /** The event cannot be applied safely (gap, unknown task): refetch the board. */
  refetch: boolean;
};

type Payload = Record<string, unknown>;

const str = (p: Payload, k: string) => (typeof p[k] === 'string' ? (p[k] as string) : null);
const num = (p: Payload, k: string) => (typeof p[k] === 'number' ? (p[k] as number) : null);

/** Derived badge (§4): a task is blocked while a `blocks` predecessor is not done. */
export function withBlocked(board: Board): Board {
  const state = new Map(board.tasks.map((t) => [t.id, t.state]));
  const blockedIds = new Set(
    board.links
      .filter((l) => l.kind === 'blocks' && state.get(l.from_id) !== 'done')
      .map((l) => l.to_id),
  );
  return {
    ...board,
    tasks: board.tasks.map((t) =>
      t.blocked === blockedIds.has(t.id) ? t : { ...t, blocked: blockedIds.has(t.id) },
    ),
  };
}

export function applyEvent(
  board: Board,
  ev: StoredEvent,
  actorNames: Record<string, string> = {},
): ApplyResult {
  if (ev.seq <= board.seq) return { board, refetch: false }; // duplicate: already applied
  if (ev.seq !== board.seq + 1) return { board, refetch: true }; // gap: resync from the server
  const p = (ev.payload ?? {}) as Payload;
  const taskId = ev.task_id ?? null;
  let tasks = board.tasks;
  let links = board.links;
  let refetch = false;

  const patch = (id: string | null, f: (t: TaskView) => TaskView) => {
    if (!id) return;
    if (!tasks.some((t) => t.id === id)) {
      refetch = true;
      return;
    }
    tasks = tasks.map((t) => (t.id === id ? f(t) : t));
  };
  const bump = (t: TaskView): TaskView => ({ ...t, version: t.version + 1, updated_at: ev.created_at });

  switch (ev.type) {
    case 'task.created':
      tasks = [
        ...tasks,
        {
          id: str(p, 'task_id') ?? '',
          project_id: str(p, 'project_id') ?? board.project.id,
          parent_id: str(p, 'parent_id'),
          title: str(p, 'title') ?? '',
          state: str(p, 'state') ?? 'draft',
          priority: num(p, 'priority') ?? 0,
          version: 1,
          spec_id: str(p, 'spec_id') ?? '',
          spec_version: num(p, 'spec_version') ?? 1,
          spec_outdated: false,
          preferred_actor_id: null,
          preferred_until: null,
          attempt_count: 0,
          rejection_count: 0,
          blocked: false,
          open_questions: 0,
          blocking_questions: 0,
          lease: null,
          created_at: ev.created_at,
          updated_at: ev.created_at,
        },
      ];
      break;
    case 'task.updated':
      patch(taskId, (t) =>
        bump({ ...t, title: str(p, 'title') ?? t.title, priority: num(p, 'priority') ?? t.priority }),
      );
      break;
    case 'task.state_changed':
      patch(taskId, (t) =>
        bump({
          ...t,
          state: str(p, 'to') ?? t.state,
          preferred_actor_id: str(p, 'preferred_actor_id'),
          preferred_until: str(p, 'preferred_until'),
        }),
      );
      break;
    case 'task.spec_outdated':
      patch(taskId, (t) => bump({ ...t, spec_outdated: true }));
      break;
    case 'task.repinned':
      patch(taskId, (t) =>
        bump({ ...t, spec_outdated: false, spec_version: num(p, 'spec_version') ?? t.spec_version }),
      );
      break;
    case 'task.link_added':
      links = [
        ...links,
        { from_id: str(p, 'from_id') ?? '', to_id: str(p, 'to_id') ?? '', kind: str(p, 'kind') ?? '' },
      ];
      break;
    case 'lease.claimed': {
      const actor = str(p, 'actor_id') ?? '';
      const attempt = (p.attempt ?? null) as Payload | null;
      patch(taskId, (t) => ({
        ...t,
        attempt_count: attempt ? (num(attempt, 'n') ?? t.attempt_count) : t.attempt_count,
        lease: {
          actor_id: actor,
          actor_name: actorNames[actor] ?? '',
          kind: str(p, 'kind') ?? 'work',
          expires_at: str(p, 'expires_at') ?? ev.created_at,
          paused: false,
          last_heartbeat_at: ev.created_at,
        },
      }));
      break;
    }
    case 'lease.released':
    case 'lease.expired':
      patch(taskId, (t) => ({ ...t, lease: null }));
      break;
    case 'test.requested':
      patch(taskId, (t) => (t.lease ? { ...t, lease: { ...t.lease, paused: true } } : t));
      break;
    case 'test.completed':
      if (p.passed !== true || p.protected_path_violation === true) {
        patch(taskId, (t) =>
          t.lease
            ? {
                ...t,
                lease: {
                  ...t.lease,
                  paused: false,
                  expires_at: str(p, 'resume_expires_at') ?? t.lease.expires_at,
                },
              }
            : t,
        );
      }
      break;
    case 'review.submitted':
      if (p.verdict === 'changes_requested') {
        patch(taskId, (t) => ({ ...t, rejection_count: t.rejection_count + 1 }));
      }
      break;
    case 'question.asked':
      patch(taskId, (t) => ({
        ...t,
        open_questions: t.open_questions + 1,
        blocking_questions: t.blocking_questions + (p.blocking === true ? 1 : 0),
      }));
      break;
    case 'question.answered':
      // The payload does not say whether it was blocking: apply what is known, then resync.
      patch(taskId, (t) => ({ ...t, open_questions: Math.max(0, t.open_questions - 1) }));
      refetch = true;
      break;
    default:
      // activity.reported, attempt.ended, spec.*: no board change, the seq still advances.
      break;
  }

  const next = withBlocked({
    ...board,
    seq: ev.seq,
    project: { ...board.project, event_seq: ev.seq },
    tasks,
    links,
  });
  return { board: next, refetch };
}
