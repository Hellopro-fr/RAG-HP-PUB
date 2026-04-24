import { Link } from 'react-router-dom';
import { Info, AlertTriangle, AlertCircle } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '../../components/ui/tooltip';
import { cn } from '../../lib/utils';
import { useCoherenceVerdict } from '../hooks';
import { RULES } from '../rules';

const ICON_BY_SEVERITY = {
  info: Info,
  warning: AlertTriangle,
  critical: AlertCircle,
};

const COLOR_BY_SEVERITY = {
  info: 'text-info',
  warning: 'text-warning',
  critical: 'text-destructive',
};

/**
 * Inline pastille that appears next to a metric when a coherence rule is violated.
 * Renders null (zero placeholder) when OK. Click → /health#rule-<id>.
 *
 * @param {{ ruleId: string, itemKey?: string, className?: string }} props
 */
export function CoherencePastille({ ruleId, itemKey, className }) {
  const violations = useCoherenceVerdict(ruleId, itemKey);
  if (violations.length === 0) return null;

  const rule = RULES.find((r) => r.id === ruleId);
  if (!rule) return null;

  const Icon = ICON_BY_SEVERITY[rule.severity] ?? AlertTriangle;
  const color = COLOR_BY_SEVERITY[rule.severity] ?? 'text-warning';
  const message = violations[0].message;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          to={`/health#rule-${ruleId}`}
          aria-label={`Incohérence détectée : ${message}`}
          className={cn('inline-flex shrink-0 hover:opacity-80', color, className)}
        >
          <Icon className="h-3.5 w-3.5" />
        </Link>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        <div className="font-medium">{rule.label}</div>
        <div className="mt-0.5 text-xs">{message}</div>
        <div className="mt-1 text-[10px] text-muted-foreground">
          Cliquer pour diagnostic
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
