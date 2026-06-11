'use client';

import { useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';
import { useIframeAutoRetry } from '@/hooks/useIframeAutoRetry';

/**
 * Overlay iframe plein écran — Formulaire demande produit HelloPro
 *
 * URL : formulaire_demande_produit.php?id_produit=X&src_integ=0&referer=conseilsnextjs&ctx=next
 *
 * Avec &ctx=next, le formulaire gère lui-même son habillage (voile + modale).
 * Côté Next : simple iframe transparente plein écran, même pattern que IframeFormModal.
 *
 * postMessages écoutés :
 *   1. {type:'hellopro_form_ready_for_minisite', loaded:true} → masquer loader
 *   2. {type:'hellopro_close_modal'}                         → fermer la popup
 *   3. {status:'success', extraData: urlMCA}                 → rediriger top vers MCA
 */

const HP_PRODUIT_BASE =
  'https://www.hellopro.fr/hellopro_fr/formulaire_demande_produit.php';

interface IframeProduitModalProps {
  idProduit: string | number;
  /** 0 = base edgb2b (catalogue officiel), 1 = base hellopro_ia (scrapé). Défaut : 0 */
  srcInteg?: 0 | 1;
  /** Paramètres supplémentaires à ajouter à l'URL (ex: origine, soc…) */
  extraParams?: Record<string, string>;
  open: boolean;
  onClose: () => void;
}

export function IframeProduitModal({
  idProduit,
  srcInteg = 0,
  extraParams,
  open,
  onClose,
}: IframeProduitModalProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const { attempt, formReady, markReady, handleIframeError } = useIframeAutoRetry({
    open,
    onClose,
  });

  const extraParamsStr = extraParams
    ? Object.entries(extraParams)
        .map(([k, v]) => `&${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
        .join('')
    : '';

  const src =
    `${HP_PRODUIT_BASE}` +
    `?id_produit=${encodeURIComponent(idProduit)}` +
    `&src_integ=${srcInteg}` +
    `&referer=conseilsnextjs` +
    `&ctx=next` +
    extraParamsStr +
    `&_retry=${attempt}`;

  /* postMessages */
  useEffect(() => {
    if (!open) return;

    function onMessage(e: MessageEvent) {
      console.log('[produit msg reçu]', e.origin, e.data);
      if (e.origin !== 'https://www.hellopro.fr') return;
      const data = e.data as Record<string, unknown>;

      /* 1. Formulaire prêt → masquer le loader */
      if (data?.type === 'hellopro_form_ready_for_minisite' && data?.loaded) {
        markReady();
        return;
      }

      /* 2. Fermeture demandée par le X interne du formulaire */
      if (data?.type === 'hellopro_close_modal') {
        onClose();
        return;
      }

      /* 3. Soumission réussie → redirection MCA */
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, onClose]);

  /* Bloquer le scroll body */
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  if (!open) return null;

  return (
    <>
      {/* Loader — visible pendant que l'iframe charge */}
      {!formReady && (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/80">
          <Loader2 className="h-10 w-10 animate-spin text-white" />
        </div>
      )}

      <iframe
        key={attempt}
        ref={iframeRef}
        src={src}
        title="Formulaire de demande produit HelloPro"
        allowTransparency
        onError={handleIframeError}
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
