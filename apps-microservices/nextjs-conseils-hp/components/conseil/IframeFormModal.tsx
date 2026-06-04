'use client';

import { useEffect, useRef, useState } from 'react';
import { Loader2, X } from 'lucide-react';

/**
 * Overlay iframe plein écran — Formulaire demande groupée HelloPro
 *
 * Avec &ctx=next, le formulaire livre la modale "clé en main" :
 *   - voile semi-transparent (body rgba(29,29,27,.84))
 *   - modale centrée ~1200px
 *   - départ étape 2 (scroll non envoyé)
 *   - bouton Retour masqué sur le premier écran
 *
 * Côté Next : simple iframe transparente plein écran.
 * Aucun habillage (backdrop, panneau, bordures) — tout vient de l'iframe.
 *
 * postMessages écoutés (README §5 et §5.2) :
 *   1. {type:'hellopro_form_ready_for_minisite', loaded:true} → masquer loader
 *   2. {status:'success', extraData: urlMCA}                 → rediriger top vers MCA
 */

const HP_FORM_BASE =
  'https://www.hellopro.fr/hellopro_fr/formulaire_demande_groupee.php';

interface IframeFormModalProps {
  idRubrique: string | number;
  category: string;
  /** Clé minisite → charte graphique (README §3). */
  referer?: string;
  /**
   * IDs des choix sélectionnés en step 1 (HeroQuoteForm).
   * - Choix unique (radio)    : tableau d'un seul élément
   * - Choix multiple (checkbox) : tableau de N éléments
   * Transmis à l'iframe via postMessage une fois formReady (README §7.4).
   * Nécessite le listener dans formulaire_minisite.js côté HelloPro.
   */
  selectedChoixIds?: Array<string | number>;
  open: boolean;
  onClose: () => void;
}

export function IframeFormModal({
  idRubrique,
  category,
  referer = 'conseils_next',
  selectedChoixIds,
  open,
  onClose,
}: IframeFormModalProps) {
  const [formReady, setFormReady] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const src =
    `${HP_FORM_BASE}` +
    `?id_rubrique=${encodeURIComponent(idRubrique)}` +
    `&category=${encodeURIComponent(category)}` +
    `&referer=${encodeURIComponent(referer)}` +
    `&ctx=next`;

  /* Reset à chaque ouverture */
  useEffect(() => {
    if (open) setFormReady(false);
  }, [open]);

  /* postMessages */
  useEffect(() => {
    if (!open) return;

    function onMessage(e: MessageEvent) {
      if (e.origin !== 'https://www.hellopro.fr') return;
      const data = e.data as Record<string, unknown>;

      /* 1. Formulaire prêt → masquer le loader + pré-remplir step 1 */
      if (data?.type === 'hellopro_form_ready_for_minisite' && data?.loaded) {
        setFormReady(true);
        // Pré-remplir les choix step 1 déjà sélectionnés dans HeroQuoteForm (README §7.4)
        // Fonctionne pour choix unique (radio) ET choix multiple (checkbox)
        // Nécessite le listener dans formulaire_minisite.js côté HelloPro
        if (selectedChoixIds && selectedChoixIds.length > 0 && iframeRef.current?.contentWindow) {
          iframeRef.current.contentWindow.postMessage(
            { type: 'hellopro_prefill_step1', choixIds: selectedChoixIds },
            'https://www.hellopro.fr'
          );
        }
        return;
      }

      /* 2. Soumission réussie → redirection MCA (README §8bis.3 Option A) */
      if (data?.status === 'success' && typeof data.extraData === 'string') {
        const url = data.extraData;
        if (/^https?:/.test(url)) {
          onClose();
          window.top!.location.href = url;
        }
      }
    }

    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [open, onClose]);

  /* Bloquer le scroll body */
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  if (!open) return null;

  return (
    <>
      {/*
        Bouton X — affiché uniquement quand le formulaire est prêt (formReady)
        Positionné au même endroit que le X natif du formulaire hellopro.fr :
        - La modale interne est centrée, max-width 1200px
        - right = (100vw - 1200px) / 2 + ~20px de padding interne
        - top   = ~100px (modale démarre à ~80px + ~20px padding)
        - max(16px, ...) = fallback sur mobile quand viewport < 1200px
      */}
      {formReady && (
      <button
        type="button"
        onClick={onClose}
        aria-label="Fermer le formulaire"
        style={{
          position: 'fixed',
          right: 'max(16px, calc((100vw - 1200px) / 2 + 20px))',
          top: '100px',
          zIndex: 10001,
        }}
        className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-full bg-white text-foreground shadow-md hover:bg-secondary"
      >
        <X className="h-5 w-5" />
      </button>
      )}

      {/* Loader — visible pendant que l'iframe charge, disparaît dès formReady */}
      {!formReady && (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/80">
          <Loader2 className="h-10 w-10 animate-spin text-white" />
        </div>
      )}

      {/*
        Iframe transparente plein écran.
        - background:transparent + colorScheme:light → Chrome ne force pas de fond opaque
        - allowTransparency → le voile semi-transparent du formulaire laisse voir la page derrière
        - opacity:0 → invisible pendant le chargement (le loader est au-dessus),
          puis opacity:1 dès formReady
      */}
      <iframe
        ref={iframeRef}
        src={src}
        title="Formulaire de demande de devis HelloPro"
        allowTransparency
        style={{
          position: 'fixed',
          inset: 0,
          width: '100vw',
          height: '100vh',
          border: 0,
          zIndex: 9999,
          background: 'transparent',
          colorScheme: 'light',
          opacity: formReady ? 1 : 0,
          transition: 'opacity 0.2s',
        }}
      />
    </>
  );
}
