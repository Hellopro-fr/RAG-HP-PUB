'use client';

import { useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';
import { useIframeAutoRetry } from '@/hooks/useIframeAutoRetry';
import { handleFormStepMessage } from '@/lib/analytics/formFunnelBridge';
import { sendPageView, resolveTrackingSessionId } from '@/lib/analytics/sessionTracking';

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
  /** Valeurs des champs libres (type_input=1) : { id_choix: texte_saisi } */
  autres?: Record<string | number, string>;
  /**
   * Démarre le formulaire à l'étape 1 au lieu de l'étape 2.
   * Utiliser pour les CTA mid-article (demande_info.php) où l'utilisateur
   * n'a pas encore sélectionné de choix. Ajoute &start=1 à l'URL iframe.
   */
  startFromStep1?: boolean;
  /**
   * Ajoute &prev=1 à l'URL iframe.
   * À utiliser uniquement depuis le Hero et le bloc QuoteForm du milieu de page.
   */
  withPrev?: boolean;
  /** Paramètres supplémentaires à ajouter tels quels à l'URL iframe (ex: soc, origine…) */
  extraParams?: Record<string, string>;
  /**
   * Le bloc appelant a déjà poussé lui-même l'étape 1 du funnel (`1ere-question`) — cas du
   * Hero et du bloc QuoteForm, qui affichent la 1re question inline et la mesurent au scroll.
   * → on déduplique l'étape 1 relayée par l'iframe (sinon double comptage quand la modale
   * démarre à l'étape 1 sans pré-remplissage). Les blocs qui ne poussent pas (TexteImage, CTA)
   * laissent l'iframe mesurer l'étape 1.
   */
  ownsStep1?: boolean;
  open: boolean;
  onClose: () => void;
}

export function IframeFormModal({
  idRubrique,
  category,
  referer = 'conseilsnextjs',
  selectedChoixIds,
  autres,
  startFromStep1 = false,
  withPrev = false,
  extraParams,
  ownsStep1 = false,
  open,
  onClose,
}: IframeFormModalProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  // Étapes funnel déjà poussées (dédup), réinitialisées à chaque ouverture de la modale.
  const pushedStepsRef = useRef<Set<string>>(new Set());
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
    `${HP_FORM_BASE}` +
    `?id_rubrique=${encodeURIComponent(idRubrique)}` +
    `&category=${encodeURIComponent(category)}` +
    `&referer=${encodeURIComponent(referer)}` +
    `&ctx=next` +
    `&tracking_session_id=${encodeURIComponent(resolveTrackingSessionId())}` +
    (startFromStep1 ? '&start=1' : '') +
    (withPrev ? '&prev=1' : '') +
    extraParamsStr +
    `&_retry=${attempt}`;

  /* postMessages */
  useEffect(() => {
    if (!open) return;

    // Re-envoie un page_view à l'ouverture du formulaire avec le cookie courant.
    // Raison : ajax_trace_session.php (www.hellopro.fr) écrase notre cookie avec le
    // PHPSESSID lors du premier appel. Si l'utilisateur ouvre le formulaire sans avoir
    // navigué (SPA) entre-temps, il n'y a pas encore de page_vue sous la nouvelle session
    // → tracer_lead_conversion_php ne trouve rien. Ce page_view garantit qu'il en existe un.
    sendPageView();

    // reset dédup funnel à chaque ouverture ; si le bloc possède déjà l'étape 1, on la pré-marque
    pushedStepsRef.current = new Set(ownsStep1 ? ['1ere-question'] : []);

    function onMessage(e: MessageEvent) {
      if (e.origin !== 'https://www.hellopro.fr') return;
      const data = e.data as Record<string, unknown>;

      /* 0. Étape funnel relayée par l'iframe → URI conseils + push dataLayer parent */
      if (handleFormStepMessage(data, pushedStepsRef.current)) return;

      /* 1. Formulaire prêt → masquer le loader + pré-remplir step 1 */
      if (data?.type === 'hellopro_form_ready_for_minisite' && data?.loaded) {
        markReady();
        // Pré-remplir les choix step 1 déjà sélectionnés dans HeroQuoteForm (README §7.4)
        // Fonctionne pour choix unique (radio) ET choix multiple (checkbox)
        // Nécessite le listener dans formulaire_minisite.js côté HelloPro
        if (selectedChoixIds && selectedChoixIds.length > 0 && iframeRef.current?.contentWindow) {
          const autresNonVides = autres
            ? Object.fromEntries(
                Object.entries(autres).filter(([, v]) => v.trim() !== '')
              )
            : undefined;
          const prefillPayload = {
            type: 'hellopro_prefill_step1',
            choixIds: selectedChoixIds,
            ...(autresNonVides && Object.keys(autresNonVides).length > 0
              ? { autres: autresNonVides }
              : {}),
          };
          console.log('[Next → iframe prefill]', JSON.stringify(prefillPayload, null, 2));
          iframeRef.current.contentWindow.postMessage(prefillPayload, 'https://www.hellopro.fr');
        }
        return;
      }

      /* 2. Fermeture demandée par le X interne du formulaire */
      if (data?.type === 'hellopro_close_modal') {
        onClose();
        return;
      }

      /* 3. Soumission réussie → redirection MCA (README §8bis.3 Option A) */
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
        key={attempt}
        ref={iframeRef}
        src={src}
        title="Formulaire de demande de devis HelloPro"
        allowTransparency
        onError={handleIframeError}
        style={{
          position: 'fixed',
          inset: 0,
          width: '100vw',
          // 100dvh = hauteur réellement visible sur mobile (évite que le bas de la modale —
          // bouton "Suivant" — passe sous la barre de navigation / l'UI du navigateur).
          // inset:0 (ci-dessus) sert de fallback pour les navigateurs sans support dvh.
          height: '100dvh',
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
