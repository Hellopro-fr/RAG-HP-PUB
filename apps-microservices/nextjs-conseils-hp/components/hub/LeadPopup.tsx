'use client';

import { useEffect, useState } from 'react';
import Image from 'next/image';
import { Download, ShieldCheck } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { HubIcon } from './primitives';
import type { HubLeadPopup } from '@/types/hub';

/**
 * Pop-up de capture d'e-mail, déclenchée quand le visiteur a dépassé une section
 * donnée (`triggerSectionId`) — signe qu'il a lu une part significative de la page.
 *
 * Ne s'affiche qu'UNE FOIS par session (`sessionStorage`), sinon elle devient
 * pénible sur une page longue.
 *
 * ⚠️ POC : aucune donnée transmise.
 */
const SEEN_KEY = 'hubLeadPopupSeen';

export function LeadPopup({ data }: { data: HubLeadPopup }) {
  const [open, setOpen] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [email, setEmail] = useState('');

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
      setOpen(true);
      try {
        window.sessionStorage.setItem(SEEN_KEY, '1');
      } catch {
        /* stockage indisponible : la pop-up réapparaîtra au rechargement */
      }
      window.removeEventListener('scroll', onScroll);
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [data.triggerSectionId]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {/* ⚠️ PAS `max-w-2xl` : globals.css redéfinit `--container-2xl: 1400px` pour
          la largeur de page, et Tailwind 4 fait lire ce même token à `max-w-2xl`.
          La pop-up ferait donc 1400 px de large. Valeur explicite obligatoire. */}
      <DialogContent className="max-w-[42rem] p-0">
        <DialogHeader className="sr-only">
          <DialogTitle>{data.title}</DialogTitle>
          <DialogDescription>{data.text}</DialogDescription>
        </DialogHeader>

        {/* Bandeau photo pleine largeur, cadré légèrement haut pour garder les
            sujets dans le champ malgré le recadrage. */}
        {data.bannerImage && (
          <div className="relative h-44 w-full overflow-hidden bg-surface sm:h-52">
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
          className={`relative bg-background px-6 pb-7 sm:px-8 ${
            // La pastille chevauche le bandeau : on remonte le panneau et on
            // arrondit son bord haut. Sans bandeau, padding normal.
            data.bannerImage ? 'rounded-t-3xl pt-10' : 'pt-7'
          }`}
        >
          {data.circleBadgeLines && data.circleBadgeLines.length > 0 && (
            // Avec bandeau : la pastille le chevauche (marge négative).
            // Sans bandeau : elle se cale en haut à droite du panneau plutôt que
            // d'occuper une ligne à elle seule, ce qui la laissait flotter dans le
            // vide au-dessus du titre.
            <div
              className={
                data.bannerImage
                  ? 'flex justify-center -mt-10 sm:-mt-14'
                  : 'pointer-events-none absolute right-14 top-5 sm:right-16'
              }
            >
              {/* `grid` en colonne unique : une ligne par entrée, sans <br>. */}
              <span className="grid h-16 w-16 place-items-center rounded-full bg-cta text-center text-[10px] font-black uppercase leading-tight text-cta-foreground shadow-lg sm:h-20 sm:w-20 sm:text-xs">
                {data.circleBadgeLines.map((line) => (
                  <span key={line}>{line}</span>
                ))}
              </span>
            </div>
          )}

          {/* ⚠️ La colonne image ne doit exister QUE si l'image existe. Sinon le
              texte hérite d'une colonne de 140 px et se casse en un mot par ligne
              (le cas par défaut aujourd'hui : visuel non livré). */}
          <div
            className={`grid gap-6 sm:gap-8 ${
              data.bannerImage ? 'mt-4' : ''
            } ${data.image ? 'sm:grid-cols-[140px_minmax(0,1fr)]' : 'sm:grid-cols-1'}`}
          >
            {data.image && (
              <div className="relative mx-auto h-40 w-32 sm:h-44 sm:w-full">
                <Image
                  src={data.image.src}
                  alt={data.image.alt}
                  fill
                  sizes="140px"
                  className="object-contain"
                />
              </div>
            )}
            <div>
              <span className="inline-flex items-center gap-2 rounded-full bg-cta/10 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-cta">
                {data.badge}
              </span>
              <h2 className="mt-3 text-2xl font-bold leading-tight text-foreground sm:text-3xl">
                {data.title}
              </h2>
              <p className="mt-1 text-xl font-semibold italic text-cta sm:text-2xl">
                {data.scriptLine}
              </p>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{data.text}</p>
            </div>
          </div>

          {submitted ? (
            <p
              role="status"
              className="mt-6 rounded-lg bg-primary/10 p-4 text-center text-sm font-semibold text-primary"
            >
              {data.successMessage}
            </p>
          ) : (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                // POC : rien n'est transmis.
                setSubmitted(true);
                setTimeout(() => setOpen(false), 1500);
              }}
              className="mt-6 flex flex-col gap-3 sm:flex-row"
            >
              <input
                type="email"
                required
                aria-label={data.emailPlaceholder}
                placeholder={data.emailPlaceholder}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="h-12 flex-1 rounded-lg border border-border bg-background px-4 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              />
              <button
                type="submit"
                className="inline-flex h-12 items-center justify-center gap-2 rounded-lg bg-cta px-5 text-sm font-bold uppercase text-cta-foreground shadow-cta transition hover:bg-cta-hover"
              >
                <Download className="h-4 w-4" />
                {data.submitLabel}
              </button>
            </form>
          )}

          <p className="mt-3 flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5" />
            {data.reassurance}
          </p>

          {data.items.length > 0 && (
            <ul className="mt-6 grid gap-4 rounded-xl bg-surface p-4 sm:grid-cols-3">
              {data.items.map((item) => (
                <li key={item.label} className="flex items-center gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-primary/10">
                    <HubIcon name={item.icon} className="h-4 w-4 text-primary" />
                  </span>
                  <span className="text-xs text-foreground">{item.label}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
