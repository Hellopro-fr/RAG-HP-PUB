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
import { CoordinatesStep, DownloadStep } from './GuideSteps';
import { useGuideLead } from '@/lib/hub/useGuideLead';
import { isLeadKnown, markLeadKnown } from '@/lib/hub/leadEmailCookie';
import type { HubGuideDialog } from '@/types/hub';

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
const GUIDE_DIALOG_EVENT = 'hp:open-guide-dialog';

/** Ouvre le dialog depuis n'importe où (client uniquement). */
export function openGuideDialog() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(GUIDE_DIALOG_EVENT));
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function GuideDownloadDialog({
  data,
  idPageHub,
}: {
  data: HubGuideDialog;
  idPageHub: number;
}) {
  const [open, setOpen] = useState(false);
  const [emailError, setEmailError] = useState('');
  const lead = useGuideLead(idPageHub);
  const { reset } = lead;

  useEffect(() => {
    const handler = () => {
      // Réinitialise le parcours à chaque ouverture.
      reset();
      setEmailError('');
      setOpen(true);
      // Visiteur reconnu (drapeau 30j) → écran de téléchargement DIRECT. On ne
      // stocke plus l'e-mail, donc aucun ré-enregistrement : on affiche juste le
      // remerciement et on rafraîchit le drapeau (fenêtre glissante de 30 j).
      if (isLeadKnown()) {
        markLeadKnown();
        lead.setPhase('download');
      }
    };
    window.addEventListener(GUIDE_DIALOG_EVENT, handler);
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
    // APPEL 1 — sans coordonnées.
    void lead.send(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
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
              <h2 className="mx-auto mb-6 max-w-sm px-6 text-center text-xl font-bold leading-snug text-foreground sm:text-2xl">
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
              onBack={() => lead.setPhase('email')}
            />
          )}

          {lead.phase === 'download' && <DownloadStep download={data.download} />}
        </div>
      </DialogContent>
    </Dialog>
  );
}
