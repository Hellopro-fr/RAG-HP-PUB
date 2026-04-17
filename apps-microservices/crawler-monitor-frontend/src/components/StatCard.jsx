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
    iconBg: 'bg-muted',
    iconFg: 'text-muted-foreground',
    rail:   'bg-border',
  },
  success: {
    iconBg: 'bg-success/15',
    iconFg: 'text-success',
    rail:   'bg-success/70',
  },
  destructive: {
    iconBg: 'bg-destructive/15',
    iconFg: 'text-destructive',
    rail:   'bg-destructive/70',
  },
  info: {
    iconBg: 'bg-info/15',
    iconFg: 'text-info',
    rail:   'bg-info/70',
  },
  warning: {
    iconBg: 'bg-warning/15',
    iconFg: 'text-warning',
    rail:   'bg-warning/70',
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
        <p className="font-mono text-2xl font-bold tracking-tight leading-none text-foreground">
          {value}
        </p>
        <p className="mt-1 text-xs uppercase tracking-wider text-muted-foreground">
          {title}
        </p>
        {trend != null && (
          <p
            className={cn(
              'mt-0.5 text-xs font-medium',
              trend > 0 ? 'text-success' : trend < 0 ? 'text-destructive' : 'text-muted-foreground'
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
