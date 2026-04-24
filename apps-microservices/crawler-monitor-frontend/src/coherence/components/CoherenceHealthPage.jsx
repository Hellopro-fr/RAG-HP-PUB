import { useEffect, useRef, useState } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { HeartPulse, AlertTriangle, AlertCircle, Info, CheckCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { Card } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { cn } from '../../lib/utils';
import { useCoherenceSummary } from '../hooks';
import { RULES } from '../rules';

const SEVERITY_ICON = {
  info: Info,
  warning: AlertTriangle,
  critical: AlertCircle,
};

const SEVERITY_COLOR = {
  info: 'text-info border-info/40 bg-info/5',
  warning: 'text-warning border-warning/40 bg-warning/5',
  critical: 'text-destructive border-destructive/40 bg-destructive/5',
};

export default function CoherenceHealthPage() {
  const { hash } = useLocation();
  const { verdicts, ignoredRules, setIgnored, byStatus, total, lastEvaluatedAt, retryState, manualRetry } =
    useCoherenceSummary();
  const [showOk, setShowOk] = useState(false);
  const highlightRef = useRef(null);

  // Hash scroll + 2s highlight ring
  useEffect(() => {
    if (!hash) return;
    const id = hash.replace('#', '');
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    el.classList.add('ring-2', 'ring-ring');
    const t = setTimeout(() => {
      el.classList.remove('ring-2', 'ring-ring');
    }, 2000);
    return () => clearTimeout(t);
  }, [hash]);

  // Categorize rules: violated, ok, ignored
  const violated = [];
  const ok = [];
  const ignored = [];
  for (const rule of RULES) {
    if (ignoredRules.has(rule.id)) {
      ignored.push(rule);
    } else if ((verdicts[rule.id] ?? []).length > 0) {
      violated.push(rule);
    } else {
      ok.push(rule);
    }
  }

  const copyContext = (rule, rviolations) => {
    const payload = {
      ruleId: rule.id,
      label: rule.label,
      severity: rule.severity,
      violations: rviolations,
      timestamp: new Date().toISOString(),
      url: window.location.href,
      userAgent: navigator.userAgent,
    };
    navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
  };

  return (
    <div ref={highlightRef} className="p-4 space-y-4">
      <Card className="p-4">
        <div className="flex items-center gap-3">
          <HeartPulse className="h-5 w-5 text-primary" />
          <div>
            <h1 className="text-base font-semibold">Cohérence des données</h1>
            <p className="text-xs text-muted-foreground font-mono">
              {total} règles · évalué il y a {Math.max(0, Math.round((Date.now() - lastEvaluatedAt) / 1000))}s
            </p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiBox label="Total" value={total} />
          <KpiBox label="Warning" value={byStatus.warning} cls="text-warning" />
          <KpiBox label="Critical" value={byStatus.critical} cls="text-destructive" />
          <KpiBox label="OK" value={ok.length} cls="text-success" />
        </div>
      </Card>

      {violated.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Violations ({violated.length})
          </h2>
          {violated.map((rule) => (
            <RuleViolationCard
              key={rule.id}
              rule={rule}
              violations={verdicts[rule.id] ?? []}
              retryState={retryState[rule.id]}
              onCopy={() => copyContext(rule, verdicts[rule.id] ?? [])}
              onIgnore={() => setIgnored(rule.id, true)}
              onManualRetry={() => manualRetry(rule.id)}
            />
          ))}
        </div>
      )}

      <div className="space-y-3">
        <button
          type="button"
          onClick={() => setShowOk((s) => !s)}
          className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
        >
          {showOk ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          OK ({ok.length})
        </button>
        {showOk && (
          <ul className="space-y-1 text-sm">
            {ok.map((rule) => (
              <li key={rule.id} className="flex items-center gap-2 text-muted-foreground">
                <CheckCircle className="h-3.5 w-3.5 text-success" />
                <span className="font-mono">{rule.id}</span>
                <span>— {rule.label}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {ignored.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Ignorées ({ignored.length})
          </h2>
          <ul className="space-y-2">
            {ignored.map((rule) => (
              <li key={rule.id} className="flex items-center justify-between rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
                <span>
                  <span className="font-mono">{rule.id}</span> — {rule.label}
                </span>
                <Button variant="outline" size="sm" onClick={() => setIgnored(rule.id, false)}>
                  Réactiver
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function KpiBox({ label, value, cls = 'text-foreground' }) {
  return (
    <div className="rounded-md border border-border bg-muted/30 p-3">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn('font-mono text-2xl font-bold', cls)}>{value}</div>
    </div>
  );
}

function RuleViolationCard({ rule, violations, retryState, onCopy, onIgnore, onManualRetry }) {
  const Icon = SEVERITY_ICON[rule.severity] ?? AlertTriangle;
  const color = SEVERITY_COLOR[rule.severity] ?? SEVERITY_COLOR.warning;
  const rs = retryState ?? { attempts: 0, exhausted: false };
  const canRefresh = !!rule.autoRetry;

  return (
    <Card id={`rule-${rule.id}`} className={cn('p-4 border-2 transition-shadow', color)}>
      <div className="flex items-start gap-3">
        <Icon className="h-5 w-5 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0 space-y-2">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-sm">{rule.id}</span>
              <span className="rounded bg-background/50 px-1.5 py-0.5 text-[10px] uppercase">
                {rule.severity}
              </span>
              {rs.exhausted && (
                <span className="rounded bg-background/50 px-1.5 py-0.5 text-[10px] font-mono">
                  🔁 {rs.attempts}/{rule.autoRetry.maxAttempts} refetch sans effet
                </span>
              )}
              {!rs.exhausted && rs.attempts > 0 && (
                <span className="rounded bg-background/50 px-1.5 py-0.5 text-[10px] font-mono">
                  🔁 retry {rs.attempts}/{rule.autoRetry.maxAttempts}
                </span>
              )}
            </div>
            <div className="mt-0.5 font-semibold">{rule.label}</div>
            <div className="mt-1 text-xs text-muted-foreground">{rule.description}</div>
          </div>

          <div className="space-y-1">
            {violations.map((v, i) => (
              <div key={i} className="rounded bg-background/50 p-2 text-sm">
                {v.itemKey && <span className="font-mono text-xs text-muted-foreground">[{v.itemKey}] </span>}
                {v.message}
              </div>
            ))}
          </div>

          <div className="text-[11px] text-muted-foreground">
            Sources : {rule.sources.join(', ')}
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            {canRefresh && (
              <Button variant="outline" size="sm" onClick={onManualRetry}>🔄 Rafraîchir</Button>
            )}
            <Button variant="outline" size="sm" onClick={onCopy}>📋 Copier contexte</Button>
            <Button variant="outline" size="sm" onClick={onIgnore}>🔕 Ignorer session</Button>
            {rule.attachUiHint && (
              <Button variant="outline" size="sm" asChild>
                <Link to={rule.attachUiHint.path}>↗ {rule.attachUiHint.label}</Link>
              </Button>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
