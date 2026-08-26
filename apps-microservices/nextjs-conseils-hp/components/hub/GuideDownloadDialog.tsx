'use client';

import { useEffect, useState } from 'react';
import { ArrowRight, BookOpen, FileText, Mail } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { HubTitle } from './primitives';
import { DIALOG_TITLE } from './typography';
import { CoordinatesStep, DownloadStep } from './GuideSteps';
import { useGuideLead } from '@/lib/hub/useGuideLead';
import { isLeadKnown, markLeadKnown } from '@/lib/hub/leadEmailCookie';
import {
  GUIDE_DIALOG_EVENT,
  DEFAULT_GUIDE_ENTRY_POINT,
  readGuideEntryPoint,
} from '@/lib/hub/guideDialogEvent';
import { pushHubEvent, type HubEntryPoint } from '@/lib/analytics/hub';
import type { HubGuideDialog } from '@/types/hub';

// Re-export : l'opener vit dans un module léger (voir guideDialogEvent.ts) pour ne
// pas embarquer ce dialog lourd dans le bundle des déclencheurs. Ré-exposé ici par
// compatibilité d'API (importé tel quel par les tests).
export { openGuideDialog } from '@/lib/hub/guideDialogEvent';

/**
 * Dialog de téléchargement du guide — ouvert par tous les boutons « guide » de
 * la page via l'événement window `hp:open-guide-dialog`.
 *
 * Parcours (spec `spec_hub/hub_guide.txt`), même endpoint `/api/demande` que le
 * projet, flux partagé via `useGuideLead` (voir aussi `LeadPopup`) :
 *   1. e-mail (+ consentement) → APPEL 1 → 201 (reconnu) `download` / 200 `coordinates`
 *   2. coordonnées (nom, téléphone, code postal) → APPEL 2 → 201 → `download`
 *
 * `id_page_hub` = prop `idPageHub` (dérivée de l'id de la page, distincte du
 * projet — cf. `guideIdPageHub`). Le consentement reste purement front (non transmis).
 */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function GuideDownloadDialog({
  data,
  idPageHub,
  pageId,
  autoOpenOnMount = false,
  autoOpenEntryPoint,
}: {
  data: HubGuideDialog;
  /** `id_page_hub` du TUNNEL guide — ce qui part à l'API. */
  idPageHub: number;
  /** Id du PROJET — portée du drapeau « déjà converti » (cf. `HubOverlays`). */
  pageId: number;
  /**
   * Emplacement du CTA à rejouer avec `autoOpenOnMount`.
   *
   * ⚠️ INDISPENSABLE au montage paresseux. Le rejeu appelle le handler SANS
   * événement : sans cette prop, `hub_entry_point` retomberait sur la valeur par
   * défaut et le PREMIER clic guide de chaque visiteur — donc la majorité des
   * ouvertures — serait attribué au bandeau, quel que soit le CTA réellement
   * cliqué. Erreur invisible : la dimension serait remplie, simplement fausse.
   */
  autoOpenEntryPoint?: HubEntryPoint;
  /**
   * Ouvre le dialog dès le montage, comme si `hp:open-guide-dialog` venait d'être
   * reçu. Utilisé quand le dialog est monté PARESSEUSEMENT en réponse à cet
   * événement (cf. `HubOverlays`) : le chunk se charge en async, l'événement
   * d'origine est donc manqué par le listener interne → on le rejoue ici. Défaut
   * `false` : montage direct (page, tests) = comportement inchangé.
   */
  autoOpenOnMount?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [emailError, setEmailError] = useState('');
  // Emplacement du CTA qui a ouvert le dialog — dimension `hub_entry_point`.
  const [entryPoint, setEntryPoint] = useState<HubEntryPoint>('banner_guide');
  // Visiteur déjà converti (cookie posé) : re-téléchargement, pas une conversion.
  const [alreadyConverted, setAlreadyConverted] = useState(false);
  const lead = useGuideLead(idPageHub, entryPoint, pageId);
  const { reset } = lead;

  useEffect(() => {
    const handler = (event?: Event) => {
      // Rejeu au montage (pas d'événement) → on reprend l'emplacement capté par
      // `HubOverlays` au moment du clic. Sinon, lecture du `detail`.
      const from = event
        ? readGuideEntryPoint(event)
        : (autoOpenEntryPoint ?? DEFAULT_GUIDE_ENTRY_POINT);
      setEntryPoint(from);
      // Réinitialise le parcours à chaque ouverture.
      reset();
      setEmailError('');
      setOpen(true);
      // Visiteur déjà converti SUR CE PROJET (drapeau 30j, cf. leadEmailCookie :
      // la portée est par `id_page_hub`) → écran de téléchargement DIRECT. On ne
      // stocke plus l'e-mail, donc aucun ré-enregistrement : on affiche juste le
      // remerciement et on rafraîchit le drapeau (fenêtre glissante de 30 j).
      if (isLeadKnown(pageId)) {
        markLeadKnown(pageId);
        lead.setPhase('download');
        setAlreadyConverted(true);
        // RACCOURCI : aucun formulaire, aucun appel API. `hub_guide_shortcut`
        // décrit exactement ce parcours et devient émettable maintenant que le
        // comportement existe (il ne l'était pas tant que cette branche relançait
        // un APPEL 1 : l'événement aurait décrit un parcours fictif).
        //
        // Surtout PAS de `hub_form_view` ici : le dialog s'ouvre, mais aucun
        // formulaire ne sera présenté. Le compter ajouterait au tunnel guide des
        // vues sans suite possible et écraserait son taux de conversion.
        pushHubEvent('hub_guide_shortcut', 'guide', {
          form_id: 'guide',
          hub_entry_point: from,
          hub_lead_path: 'deja_converti',
        });
      } else {
        setAlreadyConverted(false);
        pushHubEvent('hub_form_view', 'guide', {
          form_id: 'guide',
          hub_entry_point: from,
          // Le dialog s'ouvre DIRECTEMENT sur l'écran e-mail : pas de
          // `hub_form_email_view`, il serait simultané avec celui-ci.
        });
      }
    };
    window.addEventListener(GUIDE_DIALOG_EVENT, handler);
    // Monté en réponse à l'événement mais après coup (chunk lazy) → on rejoue
    // l'ouverture manquée. `reset` étant stable, cet effet ne s'exécute qu'au montage.
    if (autoOpenOnMount) handler();
    return () => window.removeEventListener(GUIDE_DIALOG_EVENT, handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reset]);

  const submitEmail = (event: React.FormEvent) => {
    event.preventDefault();
    if (!EMAIL_RE.test(lead.email)) {
      setEmailError('Veuillez saisir une adresse e-mail valide.');
      return;
    }
    setEmailError('');
    if (lead.submitting) return;
    pushHubEvent('hub_form_email_submit', 'guide', {
      form_id: 'guide',
      hub_entry_point: entryPoint,
    });
    // APPEL 1 — sans coordonnées.
    void lead.send(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // Abandon : fermeture avant d'avoir atteint l'écran de téléchargement.
        if (!next && lead.phase !== 'download') {
          pushHubEvent('hub_form_abandon', 'guide', {
            form_id: 'guide',
            hub_entry_point: entryPoint,
            last_step_name: lead.phase,
          });
        }
        setOpen(next);
      }}
    >
      <DialogContent className="max-w-[42rem]">
        <DialogHeader className="sr-only">
          <DialogTitle>{data.badge}</DialogTitle>
          <DialogDescription>Recevez gratuitement le guide complet.</DialogDescription>
        </DialogHeader>

        {/* Barre de progression sur les étapes coordonnées (66%) et remerciement (100%). */}
        {lead.phase !== 'email' && (
          <div className="pl-6 pr-14 pt-7 sm:pl-8">
            <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-cta transition-all duration-500"
                style={{ width: lead.phase === 'download' ? '100%' : '66%' }}
              />
            </div>
          </div>
        )}

        <div className="px-6 py-5 sm:px-8">
          {lead.phase === 'email' && (
            <>
              <h2 className={`mx-auto mb-6 max-w-sm px-6 text-center ${DIALOG_TITLE} text-foreground`}>
                <HubTitle parts={data.titleParts} />
              </h2>

              <form onSubmit={submitEmail} className="space-y-3" noValidate>
                <div>
                  <label htmlFor="guide-email" className="block text-sm font-bold text-foreground">
                    {data.fields.email}
                  </label>
                  <div className="relative mt-2">
                    <Mail className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <input
                      id="guide-email"
                      type="email"
                      required
                      value={lead.email}
                      onChange={(event) => lead.setEmail(event.target.value)}
                      placeholder={data.emailPlaceholder}
                      className="h-12 w-full rounded-xl border border-border bg-card pl-11 pr-4 text-sm outline-none focus:border-cta focus:ring-2 focus:ring-cta/20"
                    />
                  </div>
                </div>
                {emailError && (
                  <p role="alert" className="text-xs font-medium text-destructive">
                    {emailError}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={lead.submitting}
                  className="inline-flex h-14 w-full items-center justify-center gap-3 rounded-xl bg-cta text-base font-bold text-cta-foreground shadow-cta transition hover:bg-cta-hover disabled:opacity-50"
                >
                  {data.emailSubmitLabel}
                  <ArrowRight className="h-4 w-4" />
                </button>
                {lead.errorMsg && (
                  <p role="alert" className="text-xs font-medium text-destructive">
                    {lead.errorMsg}
                  </p>
                )}

                {data.trust.length > 0 && (
                  <ul className="mt-3 flex items-center rounded-xl bg-primary/5 p-3">
                    {data.trust.map((item, index) => (
                      <li
                        key={item}
                        className={`flex flex-1 items-center gap-2 text-xs text-foreground ${
                          index > 0 ? 'border-l border-primary/20 pl-3' : ''
                        }`}
                      >
                        {index === 0 ? (
                          <BookOpen className="h-4 w-4 shrink-0 text-primary" />
                        ) : (
                          <FileText className="h-4 w-4 shrink-0 text-primary" />
                        )}
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </form>
            </>
          )}

          {lead.phase === 'coordinates' && (
            <CoordinatesStep
              guide={data}
              lead={lead}
              idPrefix="guide"
              entryPoint={entryPoint}
              onBack={() => lead.setPhase('email')}
            />
          )}

          {lead.phase === 'download' && (
            <DownloadStep
              download={data.download}
              group="guide"
              entryPoint={entryPoint}
              leadPath={alreadyConverted ? 'deja_converti' : undefined}
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
