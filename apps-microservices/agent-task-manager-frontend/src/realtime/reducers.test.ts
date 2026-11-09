import { describe, expect, it } from 'vitest';

import type { Board, StoredEvent } from '@/lib/api/client';

import { applyEvent } from './reducers';

const P = '00000000-0000-7000-8000-0000000000aa';
const A = '00000000-0000-7000-8000-000000000001';
const B = '00000000-0000-7000-8000-000000000002';
const AGENT = '00000000-0000-7000-8000-0000000000ff';
const T = '2026-11-05T10:00:00Z';

function board(seq = 0): Board {
  return {
    seq,
    project: { id: P, name: 'p', workflow: {}, event_seq: seq, created_at: T, visibility: 'private' },
    tasks: [],
    links: [],
  };
}

let nextSeq = 0;
function ev(type: string, payload: Record<string, unknown>, task_id: string | null = null): StoredEvent {
  nextSeq += 1;
  return { project_id: P, seq: nextSeq, task_id, type, actor_id: AGENT, payload, trace_id: null, created_at: T };
}

function run(events: StoredEvent[], start = board()) {
  return events.reduce((b, e) => {
    const r = applyEvent(b, e, { [AGENT]: 'agent-1' });
    expect(r.refetch).toBe(false);
    return r.board;
  }, start);
}

const created = (id: string) =>
  ev('task.created', { task_id: id, project_id: P, title: id, spec_id: 's', spec_version: 1, priority: 0, state: 'ready', created_by: AGENT }, id);

describe('applyEvent', () => {
  it('adds created tasks and advances the seq', () => {
    nextSeq = 0;
    const b = run([created(A)]);
    expect(b.tasks).toHaveLength(1);
    expect(b.seq).toBe(1);
    expect(b.project.event_seq).toBe(1);
  });

  it('moves a claimed task to working with its holder and lease', () => {
    nextSeq = 0;
    const b = run([
      created(A),
      ev('task.state_changed', { task_id: A, from: 'ready', to: 'working', preferred_actor_id: null, preferred_until: null }, A),
      ev('lease.claimed', { task_id: A, actor_id: AGENT, kind: 'work', token_hash: 'h', expires_at: '2026-11-05T10:10:00Z', attempt: { attempt_id: 'x', n: 1 } }, A),
    ]);
    const t = b.tasks[0]!;
    expect(t.state).toBe('working');
    expect(t.version).toBe(2);
    expect(t.attempt_count).toBe(1);
    expect(t.lease?.actor_name).toBe('agent-1');
    expect(t.lease?.expires_at).toBe('2026-11-05T10:10:00Z');
  });

  it('ignores duplicates and asks for a refetch on a gap', () => {
    nextSeq = 0;
    const b = run([created(A)]);
    const dup = { ...created(B), seq: 1 };
    expect(applyEvent(b, dup)).toEqual({ board: b, refetch: false });
    const gap = { ...created(B), seq: 5 };
    expect(applyEvent(b, gap).refetch).toBe(true);
  });

  it('derives the blocked badge from blocks links and blocker state', () => {
    nextSeq = 0;
    let b = run([created(A), created(B), ev('task.link_added', { from_id: A, to_id: B, kind: 'blocks' }, B)]);
    expect(b.tasks.find((t) => t.id === B)?.blocked).toBe(true);
    b = run(
      [ev('task.state_changed', { task_id: A, from: 'working', to: 'done', preferred_actor_id: null, preferred_until: null }, A)],
      b,
    );
    expect(b.tasks.find((t) => t.id === B)?.blocked).toBe(false);
  });

  it('counts open questions and removes released leases', () => {
    nextSeq = 0;
    const b = run([
      created(A),
      ev('lease.claimed', { task_id: A, actor_id: AGENT, kind: 'work', token_hash: 'h', expires_at: T, attempt: null }, A),
      ev('question.asked', { question_id: 'q', task_id: A, asked_by: AGENT, body: '?', blocking: true }, A),
      ev('lease.released', { task_id: A, actor_id: AGENT, kind: 'work' }, A),
    ]);
    const t = b.tasks[0]!;
    expect(t.open_questions).toBe(1);
    expect(t.blocking_questions).toBe(1);
    expect(t.lease).toBeNull();
  });

  it('requests a refetch for events about unknown tasks', () => {
    nextSeq = 0;
    const r = applyEvent(board(), ev('task.updated', { task_id: A, title: 'x', priority: null }, A));
    expect(r.refetch).toBe(true);
  });
});
