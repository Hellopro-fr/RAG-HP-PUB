'use client';

import { useEffect, useState } from 'react';
import type { AoFormQuestion, AoChoix } from '@/types/conseils';

/**
 * Hook partagé entre HeroQuoteForm et QuoteFormBlock.
 * Centralise toute la logique de sélection des choix AO et d'ouverture du modal.
 */
export function useAoQuoteForm(
  question?: AoFormQuestion | null,
  infoRubrique?: { id: number; libelle: string } | null,
) {
  const [selected, setSelected]         = useState<Set<string | number>>(new Set());
  const [modalOpen, setModalOpen]       = useState(false);
  const [startStep1, setStartStep1]     = useState(false);
  const [pendingChoix, setPendingChoix] = useState<AoChoix | null>(null);
  const [showError, setShowError]       = useState(false);
  const [autreValues, setAutreValues]   = useState<Record<string | number, string>>({});

  const choix         = question?.choix ?? [];
  const questionLabel = question?.question ?? 'Quel est votre besoin ?';
  const isMultiple    = question ? Number(question.typeSelection) !== 1 : false;
  const isObligatoire = question ? Number(question.obligatoire) === 1 : true;

  const idRubrique = infoRubrique?.id ?? question?.id ?? '';
  const category   = infoRubrique?.libelle ?? questionLabel;

  /* Auto-dismiss erreur après 5s */
  useEffect(() => {
    if (!showError) return;
    const t = setTimeout(() => setShowError(false), 5000);
    return () => clearTimeout(t);
  }, [showError]);

  /* ── Helpers ── */

  function normalizeLabel(label: string): string {
    return label
      .replace(/&ecirc;/gi, 'ê')
      .replace(/&egrave;/gi, 'è')
      .replace(/&eacute;/gi, 'é')
      .replace(/&agrave;/gi, 'à')
      .replace(/&amp;/gi, '&')
      .toLowerCase();
  }

  function isNeSaisPas(label: string): boolean {
    const n = normalizeLabel(label);
    return n.includes('ne sais pas') || n.includes('souhaite être conseillé');
  }

  /* ── Handlers ── */

  function handleChoixClick(c: AoChoix) {
    if (!isMultiple || isNeSaisPas(c.label)) {
      setSelected(new Set([c.id]));
      setPendingChoix(c);
      setStartStep1(false);
      setModalOpen(true);
    } else {
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(c.id)) {
          next.delete(c.id);
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
        setShowError(true);
        return;
      } else {
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

  /* ── Données pour le modal ── */

  const selectedChoixIds = isMultiple
    ? [...selected]
    : pendingChoix ? [pendingChoix.id] : [];

  const autresNonVides = Object.fromEntries(
    Object.entries(autreValues).filter(([, v]) => v.trim() !== '')
  );

  return {
    /* state */
    selected, modalOpen, startStep1, showError, autreValues,
    /* dérivés */
    choix, questionLabel, isMultiple, isObligatoire,
    idRubrique, category,
    selectedChoixIds,
    autresNonVides,
    /* helpers */
    isNeSaisPas,
    /* handlers */
    handleChoixClick, handleAutreChange, handleCtaClick, handleModalClose,
  };
}
