import { Link, useLocation } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { resolveBreadcrumbs } from '../../lib/navigation';
import { cn } from '../../lib/utils';

/**
 * Breadcrumbs — reflects the current pathname.
 * Non-current crumbs are Links; the last crumb is plain text.
 */
export function Breadcrumbs({ className }) {
  const { pathname } = useLocation();
  const crumbs = resolveBreadcrumbs(pathname);

  return (
    <nav
      aria-label="Fil d'Ariane"
      className={cn('flex items-center gap-1 text-sm text-ink-3 min-w-0', className)}
    >
      {crumbs.map((crumb, i) => {
        const isLast = i === crumbs.length - 1;
        return (
          <span key={`${crumb.label}-${i}`} className="flex items-center gap-1 min-w-0">
            {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-ink-3/50 shrink-0" />}
            {crumb.to && !isLast ? (
              <Link
                to={crumb.to}
                className="truncate hover:text-ink-0 transition-colors"
              >
                {crumb.label}
              </Link>
            ) : (
              <span className={cn('truncate', isLast && 'text-ink-0 font-medium')}>
                {crumb.label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
