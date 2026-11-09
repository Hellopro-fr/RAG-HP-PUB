import { NoAccess } from '@/components/no-access';
import { AgentsTable } from '@/features/agents';
import { currentUser, load, serverApi } from '@/lib/api/server';

export const dynamic = 'force-dynamic';

export default async function AgentsPage() {
  const me = await currentUser();
  if (!me?.permissions.includes('agents.view')) return <NoAccess />;
  const api = await serverApi();
  const actors = await load(api.GET('/api/actors'), '/agents');
  return <AgentsTable initial={actors} />;
}
