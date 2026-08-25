'use client';

import dynamic from 'next/dynamic';
import { useEffect, useState } from 'react';
import {
  GUIDE_DIALOG_EVENT,
  DEFAULT_GUIDE_ENTRY_POINT,
  readGuideEntryPoint,
} from '@/lib/hub/guideDialogEvent';
import type { HubEntryPoint } from '@/lib/analytics/hub';
import type { HubGuideDialog, HubLeadPopup } from '@/types/hub';

/**
 * Loader des surcouches « guide » (dialog + pop-up scroll). Ces deux composants
 * ne rendent RIEN tant qu'ils ne sont pas déclenchés (Radix Portal fermé), mais
 * leur code (Radix Dialog + étapes + `react-international-phone` déjà lazy) pesait
 * dans le bundle initial et s'hydratait au chargement (coût INP/TBT).
 *
 * On les charge donc PARESSEUSEMENT (`ssr:false`), armés au bon moment pour ne
 * jamais rater un déclenchement :
 *  - Guide : le listener `hp:open-guide-dialog` reste TOUJOURS monté ici (coût
 *    ~nul). Au 1er clic guide on monte le corps ; comme le chunk se charge en
 *    async, `autoOpenOnMount` rejoue l'ouverture → aucune fenêtre morte. Les
 *    ouvertures suivantes passent par le listener interne du dialog.
 *  - Pop-up : elle ne s'affiche qu'après avoir DÉPASSÉ une section (donc bien
 *    après le 1er scroll). On l'arme au tout 1er scroll → son listener est en
 *    place largement avant que l'utilisateur atteigne la section de déclenchement.
 *
 * Rien de visible ni d'indexable n'est perdu : ces surcouches n'ont aucun contenu
 * SEO et n'apparaissent que sur action utilisateur.
 */
const GuideDownloadDialog = dynamic(
  () => import('./GuideDownloadDialog').then((m) => m.GuideDownloadDialog),
  { ssr: false }
);
const LeadPopup = dynamic(() => import('./LeadPopup').then((m) => m.LeadPopup), {
  ssr: false,
});

export function HubOverlays({
  guide,
  leadPopup,
  guideIdPageHub,
  pageId,
}: {
  guide: HubGuideDialog;
  leadPopup: HubLeadPopup;
  /** `id_page_hub` du parcours guide (partagé par le dialog et la pop-up). */
  guideIdPageHub: number;
  /**
   * Id de la PAGE, distinct de `guideIdPageHub` — il sert de portée au drapeau
   * « déjà converti » (cf. `lib/hub/leadEmailCookie.ts`).
   *
   * Les deux ne peuvent pas être confondus : le premier identifie un TUNNEL
   * auprès de l'API (les leads guide sont volontairement séparés des leads
   * projet), le second identifie un PROJET côté visiteur. Le drapeau suit le
   * projet, sinon remplir le questionnaire ne dispenserait pas du formulaire
   * guide sur la même page.
   */
  pageId: number;
}) {
  const [guideArmed, setGuideArmed] = useState(false);
  const [popupArmed, setPopupArmed] = useState(false);
  /**
   * Emplacement du CTA qui a provoqué le tout PREMIER clic guide.
   *
   * Il doit être capté ICI : le chunk du dialog se charge en async, son propre
   * écouteur n'existe pas encore et manque donc l'événement d'origine. Sans cette
   * capture, le rejeu au montage perdrait `entry_point` et attribuerait au
   * bandeau le premier clic de chaque visiteur — la majorité des ouvertures.
   */
  const [guideEntryPoint, setGuideEntryPoint] =
    useState<HubEntryPoint>(DEFAULT_GUIDE_ENTRY_POINT);

  useEffect(() => {
    const armGuide = (event: Event) => {
      setGuideEntryPoint(readGuideEntryPoint(event));
      setGuideArmed(true);
    };
    window.addEventListener(GUIDE_DIALOG_EVENT, armGuide);

    const armPopup = () => setPopupArmed(true);
    window.addEventListener('scroll', armPopup, { once: true, passive: true });

    return () => {
      window.removeEventListener(GUIDE_DIALOG_EVENT, armGuide);
      window.removeEventListener('scroll', armPopup);
    };
  }, []);

  return (
    <>
      {guideArmed && (
        <GuideDownloadDialog
          data={guide}
          idPageHub={guideIdPageHub}
          pageId={pageId}
          autoOpenOnMount
          autoOpenEntryPoint={guideEntryPoint}
        />
      )}
      {popupArmed && (
        <LeadPopup
          data={leadPopup}
          guide={guide}
          idPageHub={guideIdPageHub}
          pageId={pageId}
        />
      )}
    </>
  );
}
