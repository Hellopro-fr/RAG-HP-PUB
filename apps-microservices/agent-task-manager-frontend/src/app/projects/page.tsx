import { ProjectList } from '@/features/projects';
import { load, serverApi } from '@/lib/api/server';

export const dynamic = 'force-dynamic';

export default async function ProjectsPage() {
  const api = await serverApi();
  const projects = await load(api.GET('/api/projects'), '/projects');
  return <ProjectList initial={projects} />;
}
