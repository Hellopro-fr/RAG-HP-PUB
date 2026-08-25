'use client';

import { useEffect, useState } from 'react';
import Image from 'next/image';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { CoordinatesStep, DownloadStep } from './GuideSteps';
import { CARD_BODY, FEATURE_TITLE, META, TAG } from './typography';
import { useGuideLead } from '@/lib/hub/useGuideLead';
import { isLeadKnown } from '@/lib/hub/leadEmailCookie';
import { pushHubEvent } from '@/lib/analytics/hub';
import type { HubLeadPopup, HubGuideDialog } from '@/types/hub';

/**
 * Pop-up de capture d'e-mail, déclenchée quand le visiteur a dépassé une section
 * donnée (`triggerSectionId`) — signe qu'il a lu une part significative de la page.
 * Ne s'affiche qu'UNE FOIS par session (`sessionStorage`).
 *
 * Même parcours « guide » que `GuideDownloadDialog` (flux partagé `useGuideLead`,
 * endpoint `/api/demande`, `id_page_hub` identique au dialog guide).
 *
 * DEUX modals pilotés par la phase :
 *  - `email` : le GRAND modal riche (bandeau, livre, pastille) — l'accroche.
 *  - `coordinates`/`download` : un PETIT modal (`max-w-md`), au design identique
 *    au dialog guide. Au clic sur « Recevoir mon guide gratuit », la phase change
 *    → le grand modal se ferme et le petit s'ouvre (transition nette, pas de gros
 *    modal qui traîne derrière).
 */
const SEEN_KEY = 'hubLeadPopupSeen';
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function LeadPopup({
  data,
  guide,
  idPageHub,
  pageId,
}: {
  data: HubLeadPopup;
  /** Données du guide, réutilisées pour les étapes coordonnées + téléchargement. */
  guide: HubGuideDialog;
  /** `id_page_hub` du TUNNEL guide — ce qui part à l'API. */
  idPageHub: number;
  /** Id du PROJET — portée du drapeau « déjà converti » (cf. `HubOverlays`). */
  pageId: number;
}) {
  const [open, setOpen] = useState(false);
  const lead = useGuideLead(idPageHub, 'popup_scroll', pageId);
  const { reset } = lead;

  useEffect(() => {
    // sessionStorage peut lever (navigation privée, cookies bloqués) : on
    // dégrade en affichant la pop-up plutôt qu'en cassant la page.
    let alreadySeen = false;
    try {
      alreadySeen = window.sessionStorage.getItem(SEEN_KEY) === '1';
    } catch {
      alreadySeen = false;
    }
    if (alreadySeen) return;

    const trigger = document.getElementById(data.triggerSectionId);
    if (!trigger) return;

    const onScroll = () => {
      if (trigger.getBoundingClientRect().bottom >= 0) return;
      window.removeEventListener('scroll', onScroll);
      try {
        window.sessionStorage.setItem(SEEN_KEY, '1');
      } catch {
        /* stockage indisponible : la pop-up réapparaîtra au rechargement */
      }
      // Visiteur déjà converti SUR CE PROJET (drapeau en cookie) → on ne le
      // dérange pas : aucune pop-up, aucun remerciement, aucun téléchargement.
      // La portée est bien par page : converti sur l'élevage, il doit quand même
      // voir la pop-up laverie, sinon aucun lead laverie n'est jamais créé.
      if (isLeadKnown(pageId)) return;
      setOpen(true);
      // Impression de la pop-up. ⚠️ `sessionStorage` étant propre à l'ONGLET, un
      // visiteur qui ouvre la page dans trois onglets produit trois impressions
      // dans UNE SEULE session GA4 : ne pas calculer le taux de conversion de la
      // pop-up sur le NOMBRE d'événements, mais sur les sessions ou les
      // utilisateurs (cf. docs/tracking-hub.md §8).
      pushHubEvent('hub_guide_popup_view', 'guide', {
        form_id: 'guide',
        entry_point: 'popup_scroll',
        trigger_section_id: data.triggerSectionId,
      });
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
    // Plus de `eslint-disable exhaustive-deps` ici : il couvrait les appels à
    // `lead.*` de l'ancienne branche « visiteur reconnu », supprimée depuis.
    // `pageId` figure bien dans les dépendances — le drapeau « déjà converti »
    // est lu par projet, l'effet doit donc être rejoué s'il change.
  }, [data.triggerSectionId, pageId]);

  const emailValid = EMAIL_RE.test(lead.email);

  const submitEmail = (event: React.FormEvent) => {
    event.preventDefault();
    if (!emailValid || lead.submitting) return;
    pushHubEvent('hub_form_email_submit', 'guide', {
      form_id: 'guide',
      entry_point: 'popup_scroll',
    });
    // APPEL 1 — sans coordonnées. Le passage de phase ferme ce grand modal et
    // ouvre le petit (coordonnées ou téléchargement).
    void lead.send(false);
  };

  const close = () => {
    // Abandon : fermeture avant l'écran de téléchargement. Émis AVANT `reset()`,
    // qui remet la phase à 'email' et effacerait l'étape réellement atteinte.
    if (lead.phase !== 'download') {
      pushHubEvent('hub_form_abandon', 'guide', {
        form_id: 'guide',
        entry_point: 'popup_scroll',
        last_step_name: lead.phase,
      });
    }
    setOpen(false);
    reset();
  };

  return (
    <>
      {/* ---- GRAND modal : étape e-mail (design riche) -------------------- */}
      <Dialog
        open={open && lead.phase === 'email'}
        onOpenChange={(next) => {
          if (!next) close();
        }}
      >
        {/* ⚠️ PAS `max-w-2xl` : globals.css redéfinit `--container-2xl: 1400px` et
            Tailwind 4 fait lire ce token à `max-w-2xl`. Valeur explicite obligatoire. */}
        <DialogContent
          className="max-w-[42rem] p-0"
          closeClassName="bg-white text-neutral-700 shadow-md hover:bg-white hover:text-neutral-900"
        >
          <DialogHeader className="sr-only">
            <DialogTitle>{data.title}</DialogTitle>
            <DialogDescription>{data.text}</DialogDescription>
          </DialogHeader>

          {/* Bandeau photo pleine largeur, cadré légèrement haut. */}
          {data.bannerImage && (
            <div className="relative h-28 w-full overflow-hidden bg-surface sm:h-52">
              <Image
                src={data.bannerImage.src}
                alt={data.bannerImage.alt}
                fill
                sizes="(max-width: 672px) 100vw, 672px"
                className="object-cover"
                style={{ objectPosition: 'center 25%' }}
              />
            </div>
          )}

          <div
            className={`relative bg-background px-6 pb-5 sm:px-8 sm:pb-7 ${
              // Carte blanche ENCARTÉE qui remonte dans le bandeau : celui-ci
              // apparaît en cadre sur les côtés et aux coins arrondis. Le padding
              // haut compense la remontée (-mt) pour garder la hauteur du contenu.
              data.bannerImage
                ? 'z-10 mx-3 -mt-10 rounded-3xl pt-4 sm:mx-5 sm:-mt-12 sm:pt-6'
                : 'pt-7'
            }`}
          >
            {/* ⚠️ Colonne image seulement si l'image existe (sinon le texte hérite
                d'une colonne de 140 px et se casse en un mot par ligne). */}
            <div
              className={`grid gap-3 sm:gap-8 ${
                data.image ? 'sm:grid-cols-[190px_minmax(0,1fr)]' : 'sm:grid-cols-1'
              }`}
            >
              {data.image && (
                // Le livre remonte pour chevaucher le bandeau ; la pastille
                // « 100% GRATUIT » se cale sur son coin haut-droit.
                <div className="relative z-10 mx-auto -mt-10 h-44 w-32 sm:-mt-16 sm:h-60 sm:w-full">
                  <Image
                    src={data.image.src}
                    alt={data.image.alt}
                    fill
                    sizes="220px"
                    className="object-contain"
                  />
                  {data.circleBadgeLines && data.circleBadgeLines.length > 0 && (
                    // Pastille : position visuelle conservée (le `top` compense la
                    // remontée du conteneur), elle sort à moitié en haut-droite.
                    <span className="absolute -right-2 top-1 flex h-14 w-14 flex-col items-center justify-center rounded-full bg-cta text-center text-[9px] font-black uppercase leading-tight text-cta-foreground shadow-lg sm:top-0 sm:h-16 sm:w-16 sm:text-[10px]">
                      {/* Anneau blanc pointillé, en retrait du bord (décoratif). */}
                      <span
                        aria-hidden
                        className="pointer-events-none absolute inset-[3px] rounded-full border-2 border-dashed border-white/80"
                      />
                      {data.circleBadgeLines.map((line) => (
                        <span key={line}>{line}</span>
                      ))}
                    </span>
                  )}
                </div>
              )}
              <div>
                <span
                  className={`inline-flex items-center gap-2 rounded-full bg-cta/10 px-3 py-1 text-cta ${TAG}`}
                >
                  {data.badge}
                </span>
                {/* `FEATURE_TITLE` : ce grand modal est l'accroche de la page, il
                    porte le même niveau qu'une carte vedette, non celui d'un
                    dialog de parcours (`DIALOG_TITLE`, un cran en dessous). */}
                <h2 className={`mt-3 ${FEATURE_TITLE} text-foreground`}>{data.title}</h2>
                <p className="mt-1 text-xl font-semibold italic text-cta sm:text-2xl">
                  {data.scriptLine}
                </p>
                {/* `mt-2` (son réglage) + `CARD_BODY` (l'échelle partagée) :
                    la constante ne porte que taille/interligne, la marge reste
                    au point d'appel. */}
                <p className={`mt-2 ${CARD_BODY} text-muted-foreground`}>{data.text}</p>
              </div>
            </div>

            <form onSubmit={submitEmail} className="mt-4 flex flex-col gap-3 sm:mt-6 sm:flex-row" noValidate>
              <input
                type="email"
                required
                aria-label={data.emailPlaceholder}
                placeholder={data.emailPlaceholder}
                value={lead.email}
                onChange={(event) => lead.setEmail(event.target.value)}
                // Mobile (colonne) : pleine largeur, hauteur normale. `flex-1` réservé
                // au `sm+` (ligne) — en colonne il écrasait la hauteur du champ.
                className="h-12 w-full rounded-lg border border-border bg-background px-4 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 sm:w-auto sm:flex-1"
              />
              <button
                type="submit"
                disabled={!emailValid || lead.submitting}
                // `min-w` conserve une largeur stable (proche de l'ancien libellé)
                // malgré le texte court, ce qui resserre aussi le champ e-mail voisin.
                className="inline-flex h-12 min-w-[12rem] items-center justify-center gap-2 rounded-lg bg-cta px-5 text-sm font-bold uppercase text-cta-foreground shadow-cta transition hover:bg-cta-hover disabled:opacity-50"
              >
                {data.submitLabel}
                <ArrowRight className="h-4 w-4" />
              </button>
            </form>
            {lead.errorMsg && (
              <p role="alert" className="mt-2 text-center text-xs font-medium text-destructive">
                {lead.errorMsg}
              </p>
            )}

            <p
              className={`mt-3 flex items-center justify-center gap-1.5 ${META} text-muted-foreground`}
            >
              <ShieldCheck className="h-3.5 w-3.5" />
              {data.reassurance}
            </p>
          </div>
        </DialogContent>
      </Dialog>

      {/* ---- PETIT modal : coordonnées + téléchargement (design = dialog guide) -- */}
      <Dialog
        open={open && lead.phase !== 'email'}
        onOpenChange={(next) => {
          if (!next) close();
        }}
      >
        <DialogContent
          className="max-w-[42rem]"
          closeClassName="bg-white text-neutral-700 shadow-md hover:bg-white hover:text-neutral-900"
        >
          <DialogHeader className="sr-only">
            <DialogTitle>{guide.badge}</DialogTitle>
            <DialogDescription>Recevez gratuitement le guide complet.</DialogDescription>
          </DialogHeader>

          {/* Barre de progression : coordonnées (66%) et remerciement (100%). */}
          <div className="pl-6 pr-14 pt-7 sm:pl-8">
            <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-cta transition-all duration-500"
                style={{ width: lead.phase === 'download' ? '100%' : '66%' }}
              />
            </div>
          </div>

          <div className="px-6 py-4 sm:px-8">
            {lead.phase === 'coordinates' && (
              <CoordinatesStep
                guide={guide}
                lead={lead}
                idPrefix="popup"
                entryPoint="popup_scroll"
                onBack={() => lead.setPhase('email')}
              />
            )}
            {/* `=== 'download'` STRICT : sinon, à la fermeture (reset → phase
                'email'), le `else` rendait DownloadStep et déclenchait le
                téléchargement auto alors que les coordonnées n'étaient pas finies.
                ⚠️ Côté tracking, ce `else` produisait EN PLUS un `hub_guide_download`
                fantôme à chaque fermeture. Ne pas revenir à un ternaire. */}
            {lead.phase === 'download' && (
              <DownloadStep download={guide.download} group="guide" entryPoint="popup_scroll" />
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
