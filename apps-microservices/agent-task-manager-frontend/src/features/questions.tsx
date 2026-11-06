'use client';

// /questions: open questions across projects, blocking first, answerable inline (§10).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';

import { Badge, Button, Card, Textarea } from '@/components/ui';
import { type QuestionView, ApiError, api, keys, unwrap } from '@/lib/api/client';
import { formatDate, fr } from '@/lib/i18n/fr';
import { useLiveQuestions } from '@/realtime/stream';

export function AnswerForm({ question, onDone }: { question: QuestionView; onDone?: () => void }) {
  const qc = useQueryClient();
  const [answer, setAnswer] = useState('');
  const [error, setError] = useState<string | null>(null);
  const options = Array.isArray(question.options) ? (question.options as unknown[]).map(String) : [];
  const send = useMutation({
    mutationFn: (text: string) =>
      unwrap(
        api.POST('/api/questions/{id}/answer', {
          params: { path: { id: question.id } },
          body: { answer: text },
        }),
      ),
    onSuccess: () => {
      setAnswer('');
      void qc.invalidateQueries({ queryKey: ['questions'] });
      void qc.invalidateQueries({ queryKey: keys.task(question.task_id) });
      onDone?.();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : fr.errors.generic),
  });
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (answer.trim()) send.mutate(answer.trim());
      }}
    >
      {options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {options.map((o) => (
            <Button key={o} type="button" variant="outline" size="sm" onClick={() => send.mutate(o)}>
              {o}
            </Button>
          ))}
        </div>
      )}
      <Textarea
        aria-label={fr.questions.answer}
        placeholder={fr.questions.placeholder}
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
      />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <Button type="submit" size="sm" disabled={send.isPending || !answer.trim()}>
        {fr.questions.answer}
      </Button>
    </form>
  );
}

export function QuestionsInbox({ initial }: { initial: QuestionView[] }) {
  useLiveQuestions();
  const { data } = useQuery({
    queryKey: keys.questions('open'),
    queryFn: () => unwrap(api.GET('/api/questions', { params: { query: { status: 'open' } } })),
    initialData: initial,
  });
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">{fr.questions.title}</h1>
      {data.length === 0 && <p className="text-slate-500">{fr.questions.empty}</p>}
      {data.map((q) => (
        <Card key={q.id} className="space-y-2 p-4" data-testid="question">
          <div className="flex items-center gap-2 text-sm">
            {q.blocking && <Badge tone="danger">{fr.questions.blocking}</Badge>}
            <Link className="font-medium hover:underline" href={`/tasks/${q.task_id}`}>
              {fr.questions.task} : {q.task_title}
            </Link>
            <span className="text-slate-500">
              {fr.questions.askedBy(q.asked_by_name)} · {formatDate(q.created_at)}
            </span>
          </div>
          <p className="whitespace-pre-wrap">{q.body}</p>
          <AnswerForm question={q} />
        </Card>
      ))}
    </div>
  );
}
