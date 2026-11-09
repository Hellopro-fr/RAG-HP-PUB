import { Card } from '@/components/ui';
import { fr } from '@/lib/i18n/fr';

/** Shown instead of a page the user has no permission for. */
export function NoAccess() {
  return (
    <Card className="mx-auto mt-12 max-w-md space-y-2 p-6 text-center" data-testid="no-access">
      <h1 className="text-lg font-semibold">{fr.noAccess.title}</h1>
      <p className="text-sm text-slate-600">{fr.noAccess.body}</p>
    </Card>
  );
}
