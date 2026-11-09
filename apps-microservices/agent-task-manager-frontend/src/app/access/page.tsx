import { NoAccess } from '@/components/no-access';
import { AccessPage } from '@/features/access';
import { currentUser, load, serverApi } from '@/lib/api/server';

export const dynamic = 'force-dynamic';

export default async function Access() {
  const me = await currentUser();
  if (!me?.permissions.includes('access.manage')) return <NoAccess />;
  const api = await serverApi();
  const overview = await load(api.GET('/api/access'), '/access');
  return <AccessPage initial={overview} meId={me.id} />;
}
