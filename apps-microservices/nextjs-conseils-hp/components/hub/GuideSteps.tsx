'use client';

import { useEffect } from 'react';
import Image from 'next/image';
import { ArrowRight, Download, MapPin, ShieldCheck, User } from 'lucide-react';
import { PhoneField } from './PhoneField';
import { Confetti } from './Confetti';
import { DIALOG_TITLE, META, TAG } from './typography';
import { useAutoDownload } from '@/lib/hub/useAutoDownload';
import { pushHubEvent, type HubEntryPoint, type HubGroup } from '@/lib/analytics/hub';
import type { HubGuideDialog } from '@/types/hub';
import type { GuideLead } from '@/lib/hub/useGuideLead';

/**
 * Étapes « coordonnées » et « téléchargement » du parcours guide, partagées par
 * `GuideDownloadDialog` (dialog) et `LeadPopup` (pop-up) — elles sont identiques
 * dans les deux, seul l'écran e-mail diffère. Alimentées par le hook `useGuideLead`.
 */

/**
 * Champ de saisie. Le libellé sert de placeholder ET d'`aria-label` : la maquette
 * n'a pas de labels visibles, mais un champ sans nom accessible est inutilisable
 * au lecteur d'écran.
 */
export function Field({
  id,
  icon,
  label,
  value,
  onChange,
  type,
}: {
  id: string;
  icon: React.ReactNode;
  label: string;
  value: string;
  onChange: (value: string) => void;
  type: string;
}) {
  return (
    <div className="relative">
      <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground">
        {icon}
      </span>
      <input
        id={id}
        type={type}
        required
        aria-label={label}
        placeholder={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-12 w-full rounded-xl border border-border bg-card pl-11 pr-4 text-sm outline-none focus:border-cta focus:ring-2 focus:ring-cta/20"
      />
    </div>
  );
}

/**
 * Étape coordonnées : civilité (facultative) + Prénom + Nom + Téléphone
 * (indicateur pays) + Code postal → APPEL 2. Même design que le questionnaire projet.
 */
export function CoordinatesStep({
  guide,
  lead,
  idPrefix,
  entryPoint,
  onBack,
}: {
  guide: HubGuideDialog;
  lead: GuideLead;
  /** Préfixe des `id`/`name` (évite toute collision entre les 2 points d'entrée). */
  idPrefix: string;
  /** Emplacement d'origine — dimension `entry_point` du tracking. */
  entryPoint: HubEntryPoint;
  onBack?: () => void;
}) {
  return (
    <>
      <span
        className={`inline-flex w-fit items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-primary ${TAG}`}
      >
        {guide.coordinatesBadge}
      </span>
      <div className="mt-2">
        <h2 className={`${DIALOG_TITLE} text-foreground`}>{guide.coordinatesTitle}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{guide.coordinatesSubtitle}</p>
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!lead.coordinatesValid || lead.submitting) return;
          pushHubEvent('hub_form_coordinates_submit', 'guide', {
            form_id: 'guide',
            entry_point: entryPoint,
          });
          void lead.send(true);
        }}
        className="mt-2 space-y-2"
        noValidate
      >
        {/* Civilité — encart avec libellé + options (facultative). */}
        <div className="rounded-xl border border-border bg-card px-4 py-2">
          <p className="text-xs text-muted-foreground">{guide.civilityLabel}</p>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {guide.civilityOptions.map((option) => (
              <label
                key={option}
                className="flex cursor-pointer items-center gap-2 text-sm text-foreground"
              >
                <input
                  type="radio"
                  name={`${idPrefix}-civilite`}
                  checked={lead.civilite === option}
                  onChange={() => lead.setCivilite(option)}
                  className="h-4 w-4 accent-[var(--color-cta)]"
                />
                <span className={lead.civilite === option ? 'font-semibold text-primary' : ''}>
                  {option}
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* Champs empilés pleine largeur (Prénom avant Nom, cf. maquette). */}
        <div className="space-y-2">
          <Field
            id={`${idPrefix}-prenom`}
            icon={<User className="h-4 w-4" />}
            label={guide.fields.prenom}
            value={lead.prenom}
            onChange={lead.setPrenom}
            type="text"
          />
          <Field
            id={`${idPrefix}-nom`}
            icon={<User className="h-4 w-4" />}
            label={guide.fields.name}
            value={lead.nom}
            onChange={lead.setNom}
            type="text"
          />
          <PhoneField
            value={lead.phone}
            ariaLabel={guide.fields.phone}
            onChange={(nextPhone, country, code) => {
              lead.setPhone(nextPhone);
              lead.setPays(country);
              lead.setDialCode(code);
            }}
          />
          {lead.phoneError && (
            <p role="alert" className="text-xs font-medium text-destructive">
              Veuillez saisir un numéro de téléphone valide.
            </p>
          )}
          <Field
            id={`${idPrefix}-postal`}
            icon={<MapPin className="h-4 w-4" />}
            label={guide.fields.postalCode}
            value={lead.postalCode}
            onChange={lead.setPostalCode}
            type="text"
          />
        </div>

        {lead.errorMsg && (
          <p role="alert" className="text-xs font-medium text-destructive">
            {lead.errorMsg}
          </p>
        )}

        <button
          type="submit"
          disabled={!lead.coordinatesValid || lead.submitting}
          className="inline-flex h-12 w-full items-center justify-center gap-3 rounded-xl bg-cta text-base font-bold text-cta-foreground shadow-cta transition hover:bg-cta-hover disabled:opacity-50"
        >
          {guide.coordinatesSubmitLabel}
          <ArrowRight className="h-4 w-4" />
        </button>

        <p className={`flex items-center justify-center gap-2 ${META} text-muted-foreground`}>
          <ShieldCheck className="h-3.5 w-3.5 text-primary" />
          100% gratuit, sans engagement
        </p>

        {onBack && (
          <button
            type="button"
            disabled={lead.submitting}
            onClick={onBack}
            className="text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            ← Retour
          </button>
        )}
      </form>
    </>
  );
}

/**
 * Étape finale : remerciement + couverture du guide + bouton de téléchargement.
 *
 * `group` est une prop et non une constante : cet écran est aussi atteint depuis
 * le tunnel PROJET (le questionnaire offre le guide en fin de parcours). Coder
 * `'guide'` en dur attribuerait au tunnel guide des téléchargements issus du
 * questionnaire — et gonflerait sa performance apparente.
 */
export function DownloadStep({
  download,
  group,
  entryPoint,
}: {
  download: HubGuideDialog['download'];
  group: HubGroup;
  entryPoint?: HubEntryPoint;
}) {
  // Téléchargement auto dès l'affichage de l'écran de remerciement.
  useAutoDownload(download.fileUrl);

  // `auto` : déclenché par `useAutoDownload` à l'affichage. Le clic sur le lien
  // ci-dessous émet `manual`. Distinguer les deux dit si le téléchargement
  // automatique fonctionne réellement chez les visiteurs — un taux de `manual`
  // élevé signifierait que l'automatique est bloqué par le navigateur.
  useEffect(() => {
    pushHubEvent('hub_guide_download', group, {
      download_trigger: 'auto',
      entry_point: entryPoint,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="relative text-center">
      <Confetti />
      <h2 className={`${DIALOG_TITLE} text-foreground`}>{download.title}</h2>
      {download.subtitle && (
        <p className="mt-1 text-sm text-muted-foreground">{download.subtitle}</p>
      )}

      <div className="relative mx-auto mt-5 h-64 w-48">
        <Image
          src={download.image.src}
          alt={download.image.alt}
          fill
          sizes="160px"
          className="object-contain"
        />
      </div>

      {download.note && (
        <p className="mx-auto mt-5 max-w-sm text-sm text-muted-foreground">{download.note}</p>
      )}

      <a
        href={download.fileUrl ?? '#'}
        download
        onClick={() =>
          pushHubEvent('hub_guide_download', group, {
            download_trigger: 'manual',
            entry_point: entryPoint,
          })
        }
        className="mt-6 inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium text-muted-foreground transition hover:text-cta"
      >
        <Download className="h-4 w-4" />
        {download.buttonLabel}
      </a>
    </div>
  );
}
