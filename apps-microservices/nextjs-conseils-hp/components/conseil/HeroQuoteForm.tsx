'use client';

import { useState } from 'react';
import { ShieldCheck, Star, Check, ArrowRight } from 'lucide-react';
import type { AoFormQuestion, AoChoix } from '@/types/conseils';
import { IframeFormModal } from './IframeFormModal';

interface HeroQuoteFormProps {
  question?: AoFormQuestion | null;
  infoRubrique?: { id: number; libelle: string } | null;
}

/**
 * Formulaire devis affiché dans le slot droit du Hero (pages prix et autre).
 * Reçoit la première question AO depuis l'API (formulaire_ao[0]).
 *
 * Comportement (calqué sur hellopro.fr) :
 *   - typeSelection == 1 (radio / choix unique) : clic sur un choix → ouvre directement le modal
 *   - typeSelection != 1 (checkbox / choix multiple) : sélection multiple, puis bouton CTA → ouvre modal
 */
export function HeroQuoteForm({ question, infoRubrique }: HeroQuoteFormProps) {
  const [selected, setSelected] = useState<Set<string | number>>(new Set());
  const [modalOpen, setModalOpen] = useState(false);
  const [pendingChoix, setPendingChoix] = useState<AoChoix | null>(null);

  const questionLabel = question?.question ?? 'Quel est votre besoin ?';
  const choix = question?.choix ?? [];
  const isMultiple = question ? Number(question.typeSelection) !== 1 : false;

  /* ── Choix sélectionné pour l'iframe ─────────────────────────────────────── */
  // Le dernier choix cliqué (single) ou le premier sélectionné (multiple)
  const activeChoix: AoChoix | null =
    pendingChoix ??
    (selected.size > 0
      ? choix.find((c) => selected.has(c.id)) ?? null
      : null);

  const idRubrique = infoRubrique?.id ?? question?.id ?? '';
  const category = infoRubrique?.libelle ?? activeChoix?.label ?? questionLabel;

  /* ── Handlers ────────────────────────────────────────────────────────────── */

  function handleChoixClick(c: AoChoix) {
    if (!isMultiple) {
      // Choix unique → sélectionner + ouvrir modal immédiatement
      setSelected(new Set([c.id]));
      setPendingChoix(c);
      setModalOpen(true);
    } else {
      // Choix multiple → toggle
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(c.id)) next.delete(c.id);
        else next.add(c.id);
        return next;
      });
    }
  }

  function handleCtaClick() {
    setModalOpen(true);
  }

  function handleModalClose() {
    setModalOpen(false);
    setPendingChoix(null);
  }

  /* ── Rendu ───────────────────────────────────────────────────────────────── */

  return (
    <>
      <div className="rounded-2xl bg-card p-5 text-card-foreground shadow-2xl ring-1 ring-black/5">
        <div className="mb-1 flex items-center gap-2 text-sm">
          <ShieldCheck className="h-5 w-5 text-success" />
          <span className="font-semibold text-foreground">
            Recevez jusqu&apos;à 3 devis gratuits
          </span>
        </div>
        <p className="mb-3 text-xs text-muted-foreground">
          En 30 secondes, sans engagement. Comparez les meilleurs constructeurs de France.
        </p>
        <h3 className="mb-3 text-sm font-bold text-foreground">
          {questionLabel} <span className="text-cta">*</span>
        </h3>

        {choix.length > 0 && (
          <div className="grid grid-cols-4 gap-2">
            {choix.map((c) => {
              const isActive = selected.has(c.id);
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => handleChoixClick(c)}
                  className={`group flex flex-col items-center gap-2 rounded-lg border bg-background px-2 pb-2 pt-3 text-center transition hover:border-primary hover:shadow-sm ${
                    isActive
                      ? 'border-primary ring-2 ring-primary/30'
                      : 'border-border'
                  }`}
                >
                  <div className="flex h-14 w-14 items-center justify-center overflow-hidden rounded-full bg-muted ring-1 ring-border">
                    {c.image ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={c.image}
                        alt={c.label}
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <span className="text-xs text-muted-foreground">···</span>
                    )}
                  </div>
                  <div className="text-[11px] font-medium leading-tight text-foreground group-hover:text-primary">
                    {c.label}
                  </div>
                </button>
              );
            })}
          </div>
        )}

        {/*
          Bouton CTA :
          - Choix unique  → toujours visible (s'ouvre au clic sur un choix),
            ici il reste affiché comme CTA secondaire en cas de doute.
          - Choix multiple → requis pour valider et ouvrir le modal.
        */}
        <button
          type="button"
          onClick={handleCtaClick}
          disabled={isMultiple && selected.size === 0}
          className="mt-4 inline-flex h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-md bg-cta px-4 text-sm font-bold uppercase tracking-wide text-cta-foreground shadow-lg transition hover:bg-cta-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          Faire une demande groupée (1 min) <ArrowRight className="h-4 w-4" />
        </button>

        <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
          {['100 % gratuit', 'Sans engagement', 'Pros vérifiés près de chez vous'].map((t) => (
            <li key={t} className="flex items-center gap-1.5">
              <Check className="h-3.5 w-3.5 text-success" /> {t}
            </li>
          ))}
        </ul>

        <div className="mt-3 flex items-center justify-center gap-1 border-t border-border pt-2 text-xs">
          <div className="flex" aria-label="4,2 sur 5">
            {[1, 2, 3, 4].map((i) => (
              <Star key={i} className="h-3.5 w-3.5 fill-rating text-rating" />
            ))}
            <Star className="h-3.5 w-3.5 fill-rating/40 text-rating" />
          </div>
          <span className="font-semibold text-foreground">4,2/5</span>
          <span className="text-muted-foreground">&nbsp;· 9 697 avis vérifiés</span>
        </div>
      </div>

      {/* Modal iframe formulaire groupée */}
      <IframeFormModal
        idRubrique={idRubrique}
        category={category}
        selectedChoixIds={
          isMultiple
            ? [...selected]                           // choix multiple → tous les IDs cochés
            : pendingChoix ? [pendingChoix.id] : []   // choix unique → tableau d'un élément
        }
        open={modalOpen}
        onClose={handleModalClose}
      />
    </>
  );
}
