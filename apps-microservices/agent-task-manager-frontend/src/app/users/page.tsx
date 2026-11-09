import { NoAccess } from '@/components/no-access';
import { UsersPage } from '@/features/users';
import { currentUser, load, serverApi } from '@/lib/api/server';

export const dynamic = 'force-dynamic';

export default async function Users() {
  const me = await currentUser();
  if (!me?.permissions.includes('users.view')) return <NoAccess />;
  const api = await serverApi();
  const users = await load(api.GET('/api/users'), '/users');
  return <UsersPage initial={users} meId={me.id} isAdmin={me.level === 'admin'} />;
}
