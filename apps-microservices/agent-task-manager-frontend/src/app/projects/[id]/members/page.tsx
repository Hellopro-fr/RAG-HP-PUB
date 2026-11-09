import { MembersPage } from '@/features/members';
import { load, serverApi } from '@/lib/api/server';

export const dynamic = 'force-dynamic';

export default async function ProjectMembersPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const api = await serverApi();
  const members = await load(
    api.GET('/api/projects/{id}/members', { params: { path: { id } } }),
    `/projects/${id}/members`,
  );
  return <MembersPage projectId={id} initial={members} />;
}
