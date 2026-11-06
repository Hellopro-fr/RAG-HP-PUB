import { BoardView } from '@/features/board';
import { load, serverApi } from '@/lib/api/server';

export const dynamic = 'force-dynamic';

// Server Component: initial board snapshot (with its seq); the client component then streams
// every later event from that seq.
export default async function BoardPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const api = await serverApi();
  const board = await load(
    api.GET('/api/projects/{id}/board', { params: { path: { id } } }),
    `/projects/${id}`,
  );
  return <BoardView projectId={id} initial={board} />;
}
