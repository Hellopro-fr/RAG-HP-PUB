import { useEffect, useState } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { HeartPulse, AlertTriangle, AlertCircle, Info, CheckCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { cn } from '../../lib/utils';
import Pill from '../../components/ui/Pill';
import { useCoherenceSummary } from '../hooks';
import { RULES } from '../rules';

const SEVERITY_ICON = {
  info: Info,
  warning: AlertTriangle,
  critical: AlertCircle,
};

const SEVERITY_COLOR = {
  info:     'text-info border-info/20 bg-info-soft',
  warning:  'text-warn border-warn/20 bg-warn-soft',
  critical: 'text-err border-err/20 bg-err-soft',
};

const KPICELL_TONES = {
  neutral: 'text-ink-0',
  ok: 'text-ok',
  warn: 'text-warn',
  err: 'text-err',
};

function KpiCell({ label, value, tone = 'neutral' }) {
  return (
    <div className="px-4 py-3 border-r border-hairline last:border-r-0">
      <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-3 mb-1">{label}</div>
      <div className={`text-[22px] font-semibold tracking-[-0.025em] tabular-nums font-display ${KPICELL_TONES[tone] ?? 'text-ink-0'}`}>
        {value ?? '—'}
      </div>
    </div>
  );
}

export default function CoherenceHealthPage() {
  const { hash } = useLocation();
  const { verdicts, ignoredRules, setIgnored, byStatus, total, lastEvaluatedAt, retryState, manualRetry } =
    useCoherenceSummary();
  const [showOk, setShowOk] = useState(false);

  // Hash scroll + 2s highlight ring
  useEffect(() => {
    if (!hash) return;
    const id = hash.replace('#', '');
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    el.classList.add('ring-2', 'ring-accent');
    const t = setTimeout(() => {
      el.classList.remove('ring-2', 'ring-accent');
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
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-3 mb-5">
        <HeartPulse className="h-5 w-5 text-ink-2" />
        <h1 className="text-[26px] font-semibold tracking-[-0.025em] text-ink-0 font-display">
          Cohérence des données
        </h1>
        {violated.length === 0
          ? <span aria-label="Aucune violation détectée"><Pill tone="ok">tout vert</Pill></span>
          : <span aria-label={`${violated.length} violation${violated.length > 1 ? 's' : ''} détectée${violated.length > 1 ? 's' : ''}`}><Pill tone="err" dot>{violated.length} violation{violated.length > 1 ? 's' : ''}</Pill></span>
        }
        <span className="ml-auto font-mono text-[11px] text-ink-3">
          {total} règles · évalué il y a {lastEvaluatedAt > 0
            ? `${Math.max(0, Math.round((Date.now() - lastEvaluatedAt) / 1000))}s`
            : '—'}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 border border-hairline rounded-lg mb-5">
        <KpiCell label="Total" value={total} tone="neutral" />
        <KpiCell label="Warnings" value={byStatus.warning} tone={byStatus.warning > 0 ? 'warn' : 'neutral'} />
        <KpiCell label="Critique" value={byStatus.critical} tone={byStatus.critical > 0 ? 'err' : 'neutral'} />
        <KpiCell label="OK" value={ok.length} tone="ok" />
      </div>

      {violated.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">
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
          aria-expanded={showOk}
          aria-controls="ok-rules-list"
          className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3 hover:text-ink-1"
        >
          {showOk ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          OK ({ok.length})
        </button>
        {showOk && (
          <ul id="ok-rules-list" className="space-y-1 text-sm">
            {ok.map((rule) => (
              <li key={rule.id} className="flex items-center gap-2 text-ink-3">
                <CheckCircle className="h-3.5 w-3.5 text-ok" />
                <span className="font-mono">{rule.id}</span>
                <span>— {rule.label}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {ignored.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-3">
            Ignorées ({ignored.length})
          </h2>
          <ul className="space-y-2">
            {ignored.map((rule) => (
              <li key={rule.id} className="flex items-center justify-between rounded-md border border-hairline bg-bg-2 px-3 py-2 text-sm">
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

function RuleViolationCard({ rule, violations, retryState, onCopy, onIgnore, onManualRetry }) {
  const Icon = SEVERITY_ICON[rule.severity] ?? AlertTriangle;
  const color = SEVERITY_COLOR[rule.severity] ?? SEVERITY_COLOR.warning;
  const rs = retryState ?? { attempts: 0, exhausted: false };
  const canRefresh = !!rule.autoRetry;

  return (
    <div id={`rule-${rule.id}`} className={cn('p-4 border-2 transition-shadow rounded-lg', color)}>
      <div className="flex items-start gap-3">
        <Icon className="h-5 w-5 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0 space-y-2">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-sm">{rule.id}</span>
              <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] uppercase">
                {rule.severity}
              </span>
              {rs.exhausted && (
                <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] font-mono">
                  🔁 {rs.attempts}/{rule.autoRetry.maxAttempts} refetch sans effet
                </span>
              )}
              {!rs.exhausted && rs.attempts > 0 && (
                <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] font-mono">
                  🔁 retry {rs.attempts}/{rule.autoRetry.maxAttempts}
                </span>
              )}
            </div>
            <div className="mt-0.5 font-semibold text-ink-0">{rule.label}</div>
            <div className="mt-1 text-xs text-ink-3">{rule.description}</div>
          </div>

          <div className="space-y-1">
            {violations.map((v, i) => (
              <div key={`${v.itemKey ?? 'global'}-${v.message ?? i}`} className="rounded bg-surface p-2 text-sm">
                {v.itemKey && <span className="font-mono text-xs text-ink-3">[{v.itemKey}] </span>}
                {v.message}
              </div>
            ))}
          </div>

          <div className="text-[11px] text-ink-3">
            Sources : {(rule.sources ?? []).join(', ')}
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
    </div>
  );
}
