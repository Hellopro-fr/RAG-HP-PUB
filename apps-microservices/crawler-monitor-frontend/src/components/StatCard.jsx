import { cn } from '../lib/utils';
import { Card } from './ui/card';

/**
 * StatCard — dense KPI tile.
 *
 * `variant` (not color) drives the icon-tint + optional accent rail.
 * Tints come from theme tokens so the card looks right in both themes.
 */

const VARIANTS = {
  default: {
    iconBg: 'bg-bg-2',
    iconFg: 'text-ink-3',
    rail:   'bg-border',
  },
  success: {
    iconBg: 'bg-ok-soft',
    iconFg: 'text-ok',
    rail:   'bg-ok/70',
  },
  destructive: {
    iconBg: 'bg-err-soft',
    iconFg: 'text-err',
    rail:   'bg-err/70',
  },
  info: {
    iconBg: 'bg-info/15',
    iconFg: 'text-info',
    rail:   'bg-info/70',
  },
  warning: {
    iconBg: 'bg-warn-soft',
    iconFg: 'text-warn',
    rail:   'bg-warn/70',
  },
};

const StatCard = ({ title, value, icon: Icon, variant = 'default', trend }) => {
  const v = VARIANTS[variant] ?? VARIANTS.default;
  return (
    <Card className="relative flex items-center gap-3 overflow-hidden p-3 transition-colors hover:bg-accent/30">
      <span className={cn('absolute inset-y-0 left-0 w-0.5', v.rail)} aria-hidden="true" />
      <div className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-md', v.iconBg)}>
        {Icon && <Icon className={cn('h-5 w-5', v.iconFg)} />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-mono text-2xl font-bold tracking-tight leading-none text-ink-0">
          {value}
        </p>
        <p className="mt-1 text-xs uppercase tracking-wider text-ink-3">
          {title}
        </p>
        {trend != null && (
          <p
            className={cn(
              'mt-0.5 text-xs font-medium',
              trend > 0 ? 'text-ok' : trend < 0 ? 'text-err' : 'text-ink-3'
            )}
          >
            {trend > 0 ? '↑' : trend < 0 ? '↓' : '→'} {Math.abs(trend)}%
          </p>
        )}
      </div>
    </Card>
  );
};

export default StatCard;
