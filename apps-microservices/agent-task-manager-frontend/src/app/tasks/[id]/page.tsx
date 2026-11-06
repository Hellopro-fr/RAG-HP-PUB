import { TaskDetail } from '@/features/task-detail';
import { load, serverApi } from '@/lib/api/server';

export const dynamic = 'force-dynamic';

export default async function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const api = await serverApi();
  const ctx = await load(api.GET('/api/tasks/{id}', { params: { path: { id } } }), `/tasks/${id}`);
  return <TaskDetail initial={ctx} />;
}
