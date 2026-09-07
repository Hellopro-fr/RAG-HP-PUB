import { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { CoherenceContext } from './context';
import {
  useJobsQuery,
  useCapacityQuery,
  useCapacityPlanningQuery,
} from '../hooks/queries';
import { RULES } from './rules';

// FIX A: évaluation découplée du flux 1 Hz (tick toutes les EVAL_INTERVAL_MS)
const EVAL_INTERVAL_MS = 5000;
// FIX B: une violation doit persister >= HYSTERESIS_MS avant d'être affichée
const HYSTERESIS_MS = 4000;

/**
 * Abonnement au cache SANS déclencher de fetch : le provider est monté sur
 * toutes les pages, il ne doit jamais maintenir /api/jobs (≈ 6 Mo) actif.
 * `enabled: false` → l'observer ne rend pas la query « active », donc une
 * invalidation ne la refetch pas ; on ne fait que lire le cache et re-rendre
 * quand quelqu'un d'autre l'a rafraîchie.
 *
 * Deux conséquences assumées de ce mode, à connaître avant de « corriger » :
 *
 *  1. PAS DE GARBAGE COLLECTION. Un observer désactivé reste un observer :
 *     React Query ne purge jamais ces entrées au bout du `gcTime`. Les données
 *     de jobs / capacity restent donc en mémoire tant que le provider est monté
 *     — c'est le prix à payer pour ne pas re-télécharger 6 Mo à chaque page.
 *
 *  2. LES RETRY (auto ET manuel) N'ONT D'EFFET QUE SUR LES PAGES QUI MONTENT
 *     LA QUERY. `invalidateFor` marque la query périmée, mais seule une page
 *     qui l'observe vraiment (Overview pour jobs/capacity, Capacity planning
 *     pour le planning) déclenchera le refetch. Depuis /health, un retry sur
 *     une règle nourrie par /api/jobs ne rappelle rien : il prépare seulement
 *     le rafraîchissement du prochain retour sur la page concernée.
 */
const CACHE_ONLY = { enabled: false, notifyOnChangeProps: ['data'] };

/**
 * Runs all coherence rules against the current sources.
 * Each rule's evaluate() is wrapped in try/catch: a bug in one rule does not
 * break the framework. Errors are logged; the rule's verdict becomes null
 * (indéterminé — on ne prétend pas que tout va bien).
 *
 * Convention de retour d'une règle :
 *   - []            → évaluée, aucune violation
 *   - [violations]  → évaluée, violations trouvées
 *   - null          → NON évaluable (source absente / pas encore chargée)
 */
function runRules(sources) {
  const result = {};
  for (const rule of RULES) {
    try {
      const v = rule.evaluate(sources);
      result[rule.id] = Array.isArray(v) ? v : null;
    } catch (err) {
      console.error(`[coherence] rule ${rule.id} threw:`, err);
      result[rule.id] = null;
    }
  }
  return result;
}

/**
 * Stable key for a single violation used by the hysteresis map.
 * Combines ruleId + itemKey (per-item rules) + data.kind.
 *
 * IMPORTANT : jamais de repli sur `message`. Les messages embarquent les
 * compteurs courants (« 6 jobs en cours … 2 affichés ») : une clé bâtie
 * dessus change à chaque tick, la violation est vue comme « nouvelle » et
 * l'hystérésis n'est jamais atteinte — la règle ne sonne donc jamais.
 */
function violationKey(ruleId, violation) {
  return `${ruleId}|${violation.itemKey ?? ''}|${violation.data?.kind ?? ''}`;
}

/**
 * Deep-equality check for verdicts objects via a stable JSON projection.
 * Projects { ruleId: [{itemKey, message, data}][] | null } and compares as JSON.
 */
function verdictsEqual(a, b) {
  if (a === b) return true;
  const project = (v) =>
    Object.fromEntries(
      Object.entries(v).map(([ruleId, violations]) => [
        ruleId,
        violations === null
          ? null
          : violations.map((viol) => ({
              itemKey: viol.itemKey,
              message: viol.message,
              data: viol.data,
            })),
      ]),
    );
  try {
    return JSON.stringify(project(a)) === JSON.stringify(project(b));
  } catch {
    return false;
  }
}

export function CoherenceProvider({ token, replicas, children }) {
  const queryClient = useQueryClient();
  // Sources lues DEPUIS LE CACHE React Query (aucun fetch déclenché ici) :
  // c'est la page affichée qui décide de charger jobs / capacity / planning.
  const jobsQuery = useJobsQuery(token, CACHE_ONLY);
  const capacityQuery = useCapacityQuery(token, CACHE_ONLY);
  const capacityPlanningQuery = useCapacityPlanningQuery(token, '1h', CACHE_ONLY);

  // FIX A: garde la dernière valeur de replicas dans un ref mis à jour à chaque render.
  // Cela permet à sources de ne lire replicas qu'au rythme du tick (pas au rythme 1 Hz).
  const replicasRef = useRef(replicas);
  replicasRef.current = replicas;

  // FIX A: tick incrémenté toutes les EVAL_INTERVAL_MS pour déclencher une réévaluation.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const i = setInterval(() => setTick((t) => t + 1), EVAL_INTERVAL_MS);
    return () => clearInterval(i);
  }, []);

  // FIX A: sources dépend du tick (+ données REST qui, elles, peuvent changer
  // indépendamment du tick). replicasRef.current est lu à l'intérieur du memo
  // au moment du tick — pas en dep directe, pour rompre le couplage 1 Hz.
  const sources = useMemo(
    () => ({
      replicas: replicasRef.current || {},
      jobs: jobsQuery.data ?? null,
      capacity: capacityQuery.data ?? null,
      capacityPlanning: capacityPlanningQuery.data ?? null,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tick, jobsQuery.data, capacityQuery.data, capacityPlanningQuery.data],
  );

  // FIX B: hystérésis — une violation doit persister HYSTERESIS_MS avant affichage.
  // seenSinceRef: Map<clé, timestamp première observation continue>
  const seenSinceRef = useRef(new Map());

  // Calcule rawVerdicts puis applique l'hystérésis pour produire verdicts filtré.
  // prevVerdictsRef permet de stabiliser l'identité de l'objet verdicts exposé.
  const prevVerdictsRef = useRef({});

  const verdicts = useMemo(() => {
    const rawVerdicts = runRules(sources);
    const now = Date.now();
    const seenSince = seenSinceRef.current;

    // Collecte toutes les clés présentes dans rawVerdicts
    const presentKeys = new Set();
    for (const [ruleId, violations] of Object.entries(rawVerdicts)) {
      if (violations === null) continue;
      for (const v of violations) {
        presentKeys.add(violationKey(ruleId, v));
      }
    }

    // Enregistre les nouvelles violations, purge les disparues
    for (const key of seenSince.keys()) {
      if (!presentKeys.has(key)) seenSince.delete(key);
    }
    for (const key of presentKeys) {
      if (!seenSince.has(key)) seenSince.set(key, now);
    }

    // Filtre : ne garder que les violations persistantes (>= HYSTERESIS_MS).
    // Une règle non évaluable reste null (indéterminé) et traverse le filtre.
    const filtered = {};
    for (const [ruleId, violations] of Object.entries(rawVerdicts)) {
      if (violations === null) {
        filtered[ruleId] = null;
        continue;
      }
      filtered[ruleId] = violations.filter((v) => {
        const key = violationKey(ruleId, v);
        const since = seenSince.get(key);
        return since !== undefined && now - since >= HYSTERESIS_MS;
      });
    }

    // FIX A (stabilisation): réutilise la référence précédente si le contenu est identique
    if (verdictsEqual(filtered, prevVerdictsRef.current)) {
      return prevVerdictsRef.current;
    }
    prevVerdictsRef.current = filtered;
    return filtered;
  }, [sources]);

  const [ignoredRules, setIgnoredRules] = useState(() => new Set());
  const setIgnored = useCallback((ruleId, value) => {
    setIgnoredRules((prev) => {
      const next = new Set(prev);
      if (value) next.add(ruleId);
      else next.delete(ruleId);
      return next;
    });
  }, []);

  // retryState: { [ruleId]: { attempts, lastTriedAt, exhausted } }
  const [retryState, setRetryState] = useState({});
  const timersRef = useRef({}); // ruleId -> timerId

  // Invalidate queries listed in rule.autoRetry.invalidate.
  // `refetchType: 'all'` : par défaut React Query ne refetch que les queries
  // ACTIVES, et les nôtres ne le sont jamais (CACHE_ONLY ci-dessus). Sans ce
  // réglage, une page qui monte réellement la query au même moment ne serait
  // pas rafraîchie par le retry — elle attendrait son propre staleTime.
  const invalidateFor = useCallback(
    (rule) => {
      if (!rule?.autoRetry?.invalidate) return;
      for (const key of rule.autoRetry.invalidate) {
        queryClient.invalidateQueries({ queryKey: key, refetchType: 'all' });
      }
    },
    [queryClient],
  );

  // FIX C: l'effet auto-retry référence verdicts stabilisé (post-hystérésis).
  // Avec verdicts stable, le cleanup n'annule plus le setTimeout chaque seconde.
  useEffect(() => {
    for (const rule of RULES) {
      if (!rule.autoRetry) continue;
      if (ignoredRules.has(rule.id)) continue;

      const violated = (verdicts[rule.id] ?? []).length > 0;
      const state = retryState[rule.id] ?? { attempts: 0, lastTriedAt: 0, exhausted: false };

      if (!violated) {
        // Healed — reset retry state for this rule (if we have any)
        if (state.attempts > 0 || state.exhausted) {
          if (timersRef.current[rule.id]) {
            clearTimeout(timersRef.current[rule.id]);
            delete timersRef.current[rule.id];
          }
          setRetryState((prev) => {
            if (!prev[rule.id]) return prev;
            const next = { ...prev };
            delete next[rule.id];
            return next;
          });
        }
        continue;
      }

      // Violated. If exhausted or timer already pending, do nothing.
      if (state.exhausted) continue;
      if (timersRef.current[rule.id]) continue;

      // Schedule a retry after delayMs
      const timerId = setTimeout(() => {
        delete timersRef.current[rule.id];
        invalidateFor(rule);
        setRetryState((prev) => {
          const prior = prev[rule.id] ?? { attempts: 0, lastTriedAt: 0, exhausted: false };
          const attempts = prior.attempts + 1;
          const exhausted = attempts >= rule.autoRetry.maxAttempts;
          return { ...prev, [rule.id]: { attempts, lastTriedAt: Date.now(), exhausted } };
        });
      }, rule.autoRetry.delayMs);
      timersRef.current[rule.id] = timerId;
    }
  }, [verdicts, ignoredRules, invalidateFor, retryState]);

  // Les timers d'auto-retry ne sont purgés qu'au DÉMONTAGE. Les nettoyer dans le
  // cleanup de l'effet ci-dessus revenait à réarmer un timer à chaque re-render
  // (retryState change → cleanup → clearTimeout → jamais de retry).
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      for (const id of Object.values(timers)) clearTimeout(id);
      timersRef.current = {};
    };
  }, []);

  // Manual retry: user clicks "Refresh" in /health — bypasses delay, invalidates now.
  const manualRetry = useCallback(
    (ruleId) => {
      const rule = RULES.find((r) => r.id === ruleId);
      if (!rule) return;
      invalidateFor(rule);
      setRetryState((prev) => {
        const prior = prev[ruleId] ?? { attempts: 0, lastTriedAt: 0, exhausted: false };
        return {
          ...prev,
          [ruleId]: { ...prior, lastTriedAt: Date.now(), exhausted: false },
        };
      });
    },
    [invalidateFor],
  );

  const byStatus = useMemo(() => {
    let info = 0, warning = 0, critical = 0, indeterminate = 0;
    for (const rule of RULES) {
      if (ignoredRules.has(rule.id)) continue;
      const verdict = verdicts[rule.id];
      if (verdict === null || verdict === undefined) { indeterminate += 1; continue; }
      if (verdict.length === 0) continue;
      if (rule.severity === 'critical') critical += 1;
      else if (rule.severity === 'warning') warning += 1;
      else info += 1;
    }
    return { info, warning, critical, indeterminate };
  }, [verdicts, ignoredRules]);

  const total = RULES.length;
  // Horodatage de la DERNIÈRE ÉVALUATION, pas du dernier changement de verdict :
  // /health affiche « évalué il y a Ns ». Adossé à `verdicts` (stabilisé par
  // verdictsEqual), le compteur restait figé à plusieurs minutes tant que rien
  // ne bougeait — et donnait à croire que le moteur était mort alors qu'il
  // tournait bien toutes les EVAL_INTERVAL_MS. `sources` change à chaque tick.
  const lastEvaluatedAt = useMemo(() => Date.now(), [sources]); // eslint-disable-line react-hooks/exhaustive-deps

  const value = useMemo(
    () => ({
      verdicts,
      ignoredRules,
      setIgnored,
      byStatus,
      total,
      lastEvaluatedAt,
      retryState,
      manualRetry,
    }),
    [verdicts, ignoredRules, setIgnored, byStatus, total, lastEvaluatedAt, retryState, manualRetry],
  );

  return (
    <CoherenceContext.Provider value={value}>
      {children}
    </CoherenceContext.Provider>
  );
}
