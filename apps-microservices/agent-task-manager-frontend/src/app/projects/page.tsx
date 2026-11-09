import { ProjectList } from '@/features/projects';
import { currentUser, load, serverApi } from '@/lib/api/server';

export const dynamic = 'force-dynamic';

export default async function ProjectsPage() {
  const api = await serverApi();
  const [projects, invitations, me] = await Promise.all([
    load(api.GET('/api/projects'), '/projects'),
    load(api.GET('/api/invitations'), '/projects'),
    currentUser(),
  ]);
  return (
    <ProjectList
      initial={projects}
      invitations={invitations}
      canCreate={!!me?.permissions.includes('projects.create')}
    />
  );
}
