import { AgentsTable } from '@/features/agents';
import { load, serverApi } from '@/lib/api/server';

export const dynamic = 'force-dynamic';

export default async function AgentsPage() {
  const api = await serverApi();
  const actors = await load(api.GET('/api/actors'), '/agents');
  return <AgentsTable initial={actors} />;
}
