'use client';

import { useEffect, useState } from 'react';
import { ShieldCheck, Star, Check, ArrowRight } from 'lucide-react';
import type { AoFormQuestion, AoChoix } from '@/types/conseils';
import { IframeFormModal } from './IframeFormModal';

interface HeroQuoteFormProps {
  question?: AoFormQuestion | null;
  infoRubrique?: { id: number; libelle: string } | null;
}

/**
 * Formulaire devis — slot droit du Hero.
 *
 * Comportement :
 *   - typeSelection == 1 (radio) : clic sur un choix → ouvre directement le modal
 *   - typeSelection != 1 (checkbox) : sélection multiple, bouton CTA → ouvre modal
 *
 * Visuels :
 *   - Choix avec image : cercle image + label
 *   - Choix sans image : cercle check (transparent / orange si sélectionné)
 *   - Choix avec typeInput=1 (champ libre) :
 *       non sélectionné → icône + label normal
 *       sélectionné     → label remonté, champ texte affiché en bas
 */
export function HeroQuoteForm({ question, infoRubrique }: HeroQuoteFormProps) {
  const [selected, setSelected]         = useState<Set<string | number>>(new Set());
  const [modalOpen, setModalOpen]       = useState(false);
  const [startStep1, setStartStep1]     = useState(false);
  const [pendingChoix, setPendingChoix] = useState<AoChoix | null>(null);
  const [showError, setShowError]       = useState(false);
  /** Valeurs saisies dans les champs libres : { id_choix → texte } */
  const [autreValues, setAutreValues]   = useState<Record<string | number, string>>({});

  const questionLabel = question?.question ?? 'Quel est votre besoin ?';
  const choix         = question?.choix ?? [];
  const isMultiple    = question ? Number(question.typeSelection) !== 1 : false;
  const isObligatoire = question ? Number(question.obligatoire) === 1 : true; // défaut = obligatoire

  /* Auto-dismiss du message d'erreur après 5s */
  useEffect(() => {
    if (!showError) return;
    const t = setTimeout(() => setShowError(false), 5000);
    return () => clearTimeout(t);
  }, [showError]);

  const idRubrique = infoRubrique?.id ?? question?.id ?? '';
  const category   = infoRubrique?.libelle ?? questionLabel;

  /* ── Helpers ─────────────────────────────────────────────────────────────── */

  /**
   * Normalise un libellé de choix : décode les entités HTML courantes + minuscules.
   * Permet la comparaison insensible à la casse et aux entités HTML.
   */
  function normalizeLabel(label: string): string {
    return label
      .replace(/&ecirc;/gi, 'ê')
      .replace(/&egrave;/gi, 'è')
      .replace(/&eacute;/gi, 'é')
      .replace(/&agrave;/gi, 'à')
      .replace(/&amp;/gi, '&')
      .toLowerCase();
  }

  /**
   * "Ne sais pas / souhaite être conseillé" → ouvre directement le modal
   * même en mode choix multiple, car c'est une réponse finale.
   */
  function isNeSaisPas(label: string): boolean {
    const n = normalizeLabel(label);
    return n.includes('ne sais pas') || n.includes('souhaite être conseillé');
  }

  /* ── Handlers ────────────────────────────────────────────────────────────── */

  function handleChoixClick(c: AoChoix) {
    if (!isMultiple || isNeSaisPas(c.label)) {
      // Choix unique OU "Ne sais pas…" → ouvre directement le modal
      setSelected(new Set([c.id]));
      setPendingChoix(c);
      setModalOpen(true);
    } else {
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(c.id)) {
          next.delete(c.id);
          // Effacer la valeur du champ libre si on décoche
          setAutreValues((v) => { const nv = { ...v }; delete nv[c.id]; return nv; });
        } else {
          next.add(c.id);
        }
        return next;
      });
    }
  }

  function handleAutreChange(choixId: string | number, value: string) {
    setAutreValues((prev) => ({ ...prev, [choixId]: value }));
  }

  function handleCtaClick() {
    const hasSelection = isMultiple ? selected.size > 0 : pendingChoix !== null;
    if (!hasSelection) {
      if (isObligatoire) {
        // Question obligatoire → message d'erreur 5s, pas d'ouverture
        setShowError(true);
        return;
      } else {
        // Question facultative → ouvrir le formulaire depuis l'étape 1
        setStartStep1(true);
        setModalOpen(true);
        return;
      }
    }
    setStartStep1(false);
    setModalOpen(true);
  }

  function handleModalClose() {
    setModalOpen(false);
    setPendingChoix(null);
    setStartStep1(false);
  }

  /* ── Données pour le modal ───────────────────────────────────────────────── */

  const selectedChoixIds = isMultiple
    ? [...selected]
    : pendingChoix ? [pendingChoix.id] : [];

  const autresNonVides = Object.fromEntries(
    Object.entries(autreValues).filter(([, v]) => v.trim() !== '')
  );

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
          {questionLabel}
          {isObligatoire && <span className="text-cta"> *</span>}
        </h3>

        {/* Message d'erreur — visible si obligatoire + aucune réponse au clic du CTA */}
        {showError && (
          <p className="mb-3 flex items-center gap-1.5 text-xs font-medium text-destructive">
            <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-destructive text-[10px] text-white">✕</span>
            Vous devez sélectionner une réponse avant de valider
          </p>
        )}

        {choix.length > 0 && (
          <div className="grid grid-cols-4 gap-2">
            {choix.map((c) => {
              const isActive       = selected.has(c.id);
              const hasTypeInput   = String(c.typeInput) === '1';
              const hasImage       = Boolean(c.image);
              const autreVal       = autreValues[c.id] ?? '';

              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => handleChoixClick(c)}
                  className={`group flex flex-col items-center gap-2 rounded-lg border bg-background px-2 pb-2 pt-3 text-center transition hover:border-primary hover:shadow-sm ${
                    isActive ? 'border-primary ring-2 ring-primary/30' : 'border-border'
                  }`}
                >
                  {/* ── Icône ── */}
                  {hasTypeInput && isActive ? (
                    /* Champ libre sélectionné : icône masquée, label remonté */
                    null
                  ) : hasImage ? (
                    /* Image produit */
                    <div className="flex h-14 w-14 items-center justify-center overflow-hidden rounded-full bg-muted ring-1 ring-border">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={c.image} alt={c.label} className="h-full w-full object-cover" />
                    </div>
                  ) : (
                    /* Pas d'image : cercle check (transparent / orange si sélectionné) */
                    <div
                      className={`flex h-14 w-14 items-center justify-center rounded-full border-2 transition ${
                        isActive
                          ? 'border-cta bg-cta'
                          : 'border-border bg-transparent'
                      }`}
                    >
                      <Check
                        className={`h-6 w-6 transition ${
                          isActive ? 'text-cta-foreground' : 'text-border'
                        }`}
                      />
                    </div>
                  )}

                  {/* ── Label ── */}
                  <div className={`text-[11px] font-medium leading-tight group-hover:text-primary ${
                    isActive ? 'text-primary' : 'text-foreground'
                  }`}>
                    {c.label}
                  </div>

                  {/* ── Champ libre (typeInput=1, visible seulement si sélectionné) ── */}
                  {hasTypeInput && isActive && (
                    <input
                      type="text"
                      placeholder="Précisez..."
                      value={autreVal}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => handleAutreChange(c.id, e.target.value)}
                      className="mt-1 w-full rounded border border-border px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30"
                    />
                  )}
                </button>
              );
            })}
          </div>
        )}

        <button
          type="button"
          onClick={handleCtaClick}
          className="mt-4 inline-flex h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-md bg-cta px-4 text-sm font-bold uppercase tracking-wide text-cta-foreground shadow-lg transition hover:bg-cta-hover"
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

      <IframeFormModal
        idRubrique={idRubrique}
        category={category}
        selectedChoixIds={selectedChoixIds}
        autres={Object.keys(autresNonVides).length > 0 ? autresNonVides : undefined}
        startFromStep1={startStep1}
        open={modalOpen}
        onClose={handleModalClose}
      />
    </>
  );
}
