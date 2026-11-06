import { QuestionsInbox } from '@/features/questions';
import { load, serverApi } from '@/lib/api/server';

export const dynamic = 'force-dynamic';

export default async function QuestionsPage() {
  const api = await serverApi();
  const questions = await load(
    api.GET('/api/questions', { params: { query: { status: 'open' } } }),
    '/questions',
  );
  return <QuestionsInbox initial={questions} />;
}
