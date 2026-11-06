'use client';

// Live streams (§6, §10): one EventSource per open project, plus the cross-project inbox stream.
// The browser resumes with Last-Event-ID automatically after a disconnect (the server sets `id:`).

import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { type ActorView, type Board, type StoredEvent, keys, streamOrigin } from '@/lib/api/client';

import { applyEvent } from './reducers';

export const EVENT_TYPES = [
  'task.created',
  'task.updated',
  'task.state_changed',
  'task.link_added',
  'task.spec_outdated',
  'task.repinned',
  'spec.version_proposed',
  'spec.version_approved',
  'lease.claimed',
  'lease.released',
  'lease.expired',
  'activity.reported',
  'question.asked',
  'question.answered',
  'test.requested',
  'test.completed',
  'review.submitted',
  'attempt.ended',
] as const;

export type StreamStatus = 'connecting' | 'live' | 'reconnecting';

/** Open the project stream; `onEvent` receives every parsed event, in seq order. */
export function useProjectEvents(
  projectId: string,
  after: number | null,
  onEvent: (ev: StoredEvent) => void,
  onError: () => void,
): StreamStatus {
  const [status, setStatus] = useState<StreamStatus>('connecting');
  const handlers = useRef({ onEvent, onError });
  useEffect(() => {
    handlers.current = { onEvent, onError };
  }, [onEvent, onError]);

  useEffect(() => {
    const qs = after === null ? '' : `?after=${after}`;
    const es = new EventSource(`${streamOrigin}/api/projects/${projectId}/stream${qs}`, {
      withCredentials: true,
    });
    const listener = (msg: MessageEvent<string>) => {
      try {
        handlers.current.onEvent(JSON.parse(msg.data) as StoredEvent);
      } catch {
        handlers.current.onError();
      }
    };
    for (const t of EVENT_TYPES) es.addEventListener(t, listener as EventListener);
    es.onopen = () => setStatus('live');
    es.onerror = () => setStatus('reconnecting');
    return () => es.close();
    // `after` is only the starting point; reconnects use Last-Event-ID.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);
  return status;
}

/** Board: apply each event to the cached board; refetch on any gap or parse error (§10). */
export function useLiveBoard(projectId: string, startSeq: number): StreamStatus {
  const qc = useQueryClient();
  return useProjectEvents(
    projectId,
    startSeq,
    (ev) => {
      const key = keys.board(projectId);
      const current = qc.getQueryData<Board>(key);
      if (!current) return;
      const actors = qc.getQueryData<ActorView[]>(keys.actors) ?? [];
      const names = Object.fromEntries(actors.map((a) => [a.id, a.name]));
      const { board, refetch } = applyEvent(current, ev, names);
      qc.setQueryData(key, board);
      if (refetch) void qc.invalidateQueries({ queryKey: key });
      if (ev.type.startsWith('lease.')) void qc.invalidateQueries({ queryKey: keys.actors });
      if (ev.task_id) {
        void qc.invalidateQueries({ queryKey: keys.task(ev.task_id) });
        void qc.invalidateQueries({ queryKey: keys.timeline(ev.task_id) });
      }
      if (ev.type.startsWith('question.')) void qc.invalidateQueries({ queryKey: ['questions'] });
    },
    () => void qc.invalidateQueries({ queryKey: keys.board(projectId) }),
  );
}

/** Task page: refresh the task and its timeline when one of its events arrives. */
export function useLiveTask(projectId: string, taskId: string): StreamStatus {
  const qc = useQueryClient();
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: keys.task(taskId) });
    void qc.invalidateQueries({ queryKey: keys.timeline(taskId) });
  };
  return useProjectEvents(
    projectId,
    null,
    (ev) => {
      if (ev.task_id === taskId) refresh();
    },
    refresh,
  );
}

/** Questions inbox: cross-project stream; any question event refreshes the inbox. */
export function useLiveQuestions(): StreamStatus {
  const qc = useQueryClient();
  const [status, setStatus] = useState<StreamStatus>('connecting');
  useEffect(() => {
    const es = new EventSource(`${streamOrigin}/api/stream?topics=questions`, {
      withCredentials: true,
    });
    const refresh = () => void qc.invalidateQueries({ queryKey: ['questions'] });
    for (const t of ['question.asked', 'question.answered', 'resync']) es.addEventListener(t, refresh);
    // No resume on this stream: refetch after every (re)connection.
    es.onopen = () => {
      setStatus('live');
      refresh();
    };
    es.onerror = () => setStatus('reconnecting');
    return () => es.close();
  }, [qc]);
  return status;
}
