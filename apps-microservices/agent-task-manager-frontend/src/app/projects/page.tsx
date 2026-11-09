import { ProjectList } from '@/features/projects';
import { currentUser, load, serverApi } from '@/lib/api/server';

export const dynamic = 'force-dynamic';

export default async function ProjectsPage() {
  const api = await serverApi();
  const projects = await load(api.GET('/api/projects'), '/projects');
  const me = await currentUser();
  return <ProjectList initial={projects} canCreate={!!me?.permissions.includes('projects.create')} />;
}
