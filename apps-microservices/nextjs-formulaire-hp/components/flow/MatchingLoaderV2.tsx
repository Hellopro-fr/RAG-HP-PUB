'use client';

import { useEffect, useMemo, useState } from 'react';
import { Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useFlowStore } from '@/lib/stores/flow-store';
import { extractChipsFromAnswers } from '@/lib/utils/exclude-chips';

interface MatchingLoaderV2Props {
  /** Progression externe (0-100) pilotée par les appels API */
  externalProgress?: number;
  /** Utilisé seulement si externalProgress n'est pas fourni */
  onComplete?: () => void;
  /** Utilisé seulement si externalProgress n'est pas fourni */
  duration?: number;
}

const STEP_LABELS = [
  'Analyse de vos critères',
  'Recherche des produits',
  'Sélection des fournisseurs',
  'Finalisation',
];

export default function MatchingLoaderV2({
  externalProgress,
  onComplete,
  duration = 5000,
}: MatchingLoaderV2Props) {
  const useExternal = externalProgress !== undefined;

  const [displayProgress, setDisplayProgress] = useState(0);
  const [internalTarget, setInternalTarget] = useState(0);

  const targetProgress = useExternal ? (externalProgress ?? 0) : internalTarget;

  const currentStep =
    displayProgress >= 75 ? 3 : displayProgress >= 50 ? 2 : displayProgress >= 25 ? 1 : 0;
  const stepLabel = STEP_LABELS[currentStep];

  // Smooth interpolation vers targetProgress — comportement identique à MatchingLoader v1
  useEffect(() => {
    const interval = setInterval(() => {
      setDisplayProgress((prev) => {
        if (targetProgress === 0) {
          if (prev >= 24) return prev;
          return prev + 0.2;
        }
        if (prev >= targetProgress) {
          const softCeiling = Math.min(targetProgress + 24, 95);
          if (prev >= softCeiling) return prev;
          return prev + 0.12;
        }
        return Math.min(prev + 1, targetProgress);
      });
    }, 50);
    return () => clearInterval(interval);
  }, [targetProgress]);

  // Fallback interne (mode timer) — identique à MatchingLoader v1
  useEffect(() => {
    if (useExternal) return;
    const progressInterval = setInterval(() => {
      setInternalTarget((prev) => {
        const newProgress = prev + (100 / (duration / 50));
        return Math.min(newProgress, 100);
      });
    }, 50);
    const completeTimer = setTimeout(() => {
      onComplete?.();
    }, duration);
    return () => {
      clearInterval(progressInterval);
      clearTimeout(completeTimer);
    };
  }, [duration, onComplete, useExternal]);

  const userQuestionAnswers = useFlowStore((s) => s.userQuestionAnswers);
  const chips = useMemo(() => extractChipsFromAnswers(userQuestionAnswers), [userQuestionAnswers]);

  return (
    <div className="min-h-screen bg-muted/30">
      {/* Couche 1 : gradient radial + skeleton fantôme */}
      <div className="fixed inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-primary/5 via-background to-background" />
      <div className="relative z-0 p-8 opacity-50">
        <div className="max-w-4xl mx-auto space-y-6">
          <div className="h-16 bg-card rounded-lg animate-pulse" />
          <div className="grid grid-cols-3 gap-4">
            <div className="h-40 bg-card rounded-lg animate-pulse" />
            <div className="h-40 bg-card rounded-lg animate-pulse" />
            <div className="h-40 bg-card rounded-lg animate-pulse" />
          </div>
          <div className="h-64 bg-card rounded-lg animate-pulse" />
        </div>
      </div>

      {/* Couche 2 : carte centrée */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-background px-4">
        <div className="w-full max-w-3xl transition-all duration-500 opacity-100 scale-100">
          <div
            className={cn(
              'grid gap-10 md:gap-14 items-center',
              chips.length > 0 ? 'md:grid-cols-2' : 'grid-cols-1'
            )}
          >
            {chips.length > 0 && (
              <div className="order-2 md:order-1">
                <p className="text-xs uppercase tracking-wide text-muted-foreground mb-3">
                  Votre besoin
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {chips.map((chip, i) => (
                    <span
                      key={`${chip}-${i}`}
                      className="inline-flex items-center rounded-full bg-muted/60 px-2.5 py-1 text-xs text-foreground"
                    >
                      {chip}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div
              className={cn(
                'flex flex-col items-center md:items-start text-center md:text-left',
                chips.length > 0 ? 'order-1 md:order-2' : ''
              )}
            >
              <div className="relative mb-6">
                <div className="absolute inset-0 rounded-full bg-primary/20 animate-ping" />
                <div className="relative flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 border border-primary/30">
                  <Sparkles className="h-6 w-6 text-primary" />
                </div>
              </div>

              <div className="min-h-[3.5rem]">
                <p className="text-sm text-muted-foreground mb-1">Recherche en cours…</p>
                <p
                  key={stepLabel}
                  className="text-xl sm:text-2xl font-semibold text-foreground animate-in fade-in slide-in-from-bottom-1 duration-500"
                >
                  {stepLabel}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
