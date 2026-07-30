'use client';

import { useEffect, useState } from 'react';
import { ArrowRight, Check, Home, Mail, MapPin, Phone, ShieldCheck, User } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { HubIcon } from './primitives';
import type { HubAssistant } from '@/types/hub';

/**
 * Questionnaire du hero — « Recevez votre plan projet personnalisé ».
 *
 * ⚠️ POC : ce formulaire n'envoie RIEN. Aucun `fetch`, aucun lead collecté
 * (décision du 28/07/2026, cf. CLAUDE.md §11bis.4). Les réponses vivent en état
 * React et sont perdues à la fermeture. Le branchement réel — iframe formulaire
 * HP ou route API — reste à arbitrer.
 *
 * Architecture reprise du prototype : l'étape 1 est rendue INLINE dans le hero
 * (elle doit être visible sans clic, c'est l'accroche), les étapes suivantes,
 * l'e-mail et l'écran de confirmation passent dans un dialog. La progression
 * commence donc dès le hero.
 *
 * Un événement window `hp:open-assistant-dialog` permet à n'importe quel CTA de
 * la page d'ouvrir le questionnaire sans prop drilling à travers des Server
 * Components — le couplage est volontaire et documenté.
 */
export const ASSISTANT_DIALOG_EVENT = 'hp:open-assistant-dialog';

/** Ouvre le questionnaire depuis n'importe où (client uniquement). */
export function openAssistantDialog() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(ASSISTANT_DIALOG_EVENT));
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function AssistantForm({ data }: { data: HubAssistant }) {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string | string[]>>({});
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [postalCode, setPostalCode] = useState('');
  const [address, setAddress] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [forceOpen, setForceOpen] = useState(false);

  // Flux : questionnaire (0..N-1) → e-mail (N) → coordonnées (N+1) → succès.
  const totalSteps = data.steps.length + 2;
  const isContact = step === data.steps.length;
  const isCoordinates = step === data.steps.length + 1;
  const current = step < data.steps.length ? data.steps[step] : null;
  const progressPct = ((step + (submitted ? 1 : 0)) / totalSteps) * 100;

  const reset = () => {
    setStep(0);
    setAnswers({});
    setEmail('');
    setName('');
    setPhone('');
    setPostalCode('');
    setAddress('');
    setSubmitted(false);
    setForceOpen(false);
  };

  useEffect(() => {
    const handler = () => {
      reset();
      setForceOpen(true);
    };
    window.addEventListener(ASSISTANT_DIALOG_EVENT, handler);
    return () => window.removeEventListener(ASSISTANT_DIALOG_EVENT, handler);
  }, []);

  const isSelected = (id: string, option: string) => {
    const value = answers[id];
    return Array.isArray(value) ? value.includes(option) : value === option;
  };

  const selectOption = (id: string, option: string, multi: boolean) => {
    if (multi) {
      setAnswers((prev) => {
        const list = Array.isArray(prev[id]) ? (prev[id] as string[]) : [];
        return {
          ...prev,
          [id]: list.includes(option) ? list.filter((v) => v !== option) : [...list, option],
        };
      });
      return;
    }
    setAnswers((prev) => ({ ...prev, [id]: option }));
    // Avance automatiquement sur un choix unique, après un court délai pour que
    // la sélection soit visible.
    setTimeout(() => setStep((s) => s + 1), 180);
  };

  const hasAnswer = current
    ? Array.isArray(answers[current.id])
      ? (answers[current.id] as string[]).length > 0
      : Boolean(answers[current.id])
    : false;

  const inlineStep = data.steps[0];
  const inlineAnswered = Boolean(answers[inlineStep?.id ?? '']);
  const modalOpen = forceOpen || step > 0 || submitted;
  const emailValid = EMAIL_RE.test(email);
  const coordinatesValid =
    name.trim() !== '' &&
    phone.trim() !== '' &&
    postalCode.trim() !== '' &&
    address.trim() !== '';

  return (
    <>
      {/* ---------------------------------------------------- Carte du hero --- */}
      <div className="w-full overflow-hidden rounded-3xl border border-border bg-card shadow-elegant">
        <div className="px-6 pt-5 sm:px-8 sm:pt-6">
          <div className="flex items-start justify-between gap-4">
            <h2 className="text-lg font-bold text-foreground sm:text-xl">{data.cardTitle}</h2>
            <span className="shrink-0 rounded-full bg-cta/10 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-cta">
              Question 1/{totalSteps}
            </span>
          </div>
          <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-cta transition-all duration-500" style={{ width: '0%' }} />
          </div>
        </div>

        {inlineStep && (
          <div className="space-y-4 px-6 py-5 sm:px-8 sm:py-6">
            <h3 className="text-base font-bold text-foreground sm:text-lg">{inlineStep.label}</h3>
            <div className="flex flex-col gap-2">
              {inlineStep.options.map((option, index) => (
                <OptionButton
                  key={option}
                  label={option}
                  icon={inlineStep.illustrations?.[index]}
                  selected={isSelected(inlineStep.id, option)}
                  onClick={() => selectOption(inlineStep.id, option, inlineStep.multi)}
                />
              ))}
            </div>
            <button
              type="button"
              disabled={!inlineAnswered}
              onClick={() => setStep((s) => (s === 0 ? 1 : s))}
              className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-cta text-sm font-bold text-cta-foreground shadow-cta transition hover:bg-cta-hover disabled:opacity-50"
            >
              {data.ctaLabel}
              <ArrowRight className="h-4 w-4" />
            </button>
            <p className="flex items-center justify-center gap-2 text-center text-xs text-muted-foreground">
              <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
              {data.reassurance}
            </p>
          </div>
        )}
      </div>

      {/* --------------------------------------------------------- Dialog --- */}
      <Dialog
        open={modalOpen}
        onOpenChange={(open) => {
          // La croix ferme entièrement le questionnaire et revient à l'état
          // initial, plutôt que de reculer d'une étape.
          if (!open) reset();
        }}
      >
        <DialogContent className="max-w-xl p-0">
          <DialogHeader className="sr-only">
            <DialogTitle>{data.cardTitle}</DialogTitle>
            <DialogDescription>
              Questionnaire en {totalSteps} étapes pour recevoir votre plan projet.
            </DialogDescription>
          </DialogHeader>

          <div className="px-6 pt-6 sm:px-8">
            <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-cta transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          <div className="px-6 py-6 sm:px-8">
            {submitted ? (
              <Success data={data} onRestart={reset} />
            ) : isContact ? (
              <form
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!emailValid) return;
                  // Avance vers l'étape coordonnées (aucune donnée transmise — POC).
                  setStep((s) => s + 1);
                }}
              >
                <span className="inline-flex w-fit items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">
                  {data.contact.badge}
                </span>
                <div>
                  <label htmlFor="hub-assistant-email" className="block text-base font-bold text-foreground">
                    {data.contact.label}
                  </label>
                  <p className="mt-1 text-xs text-muted-foreground">{data.contact.helper}</p>
                </div>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <input
                    id="hub-assistant-email"
                    type="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder={data.contact.emailPlaceholder}
                    className="h-12 w-full rounded-xl border border-border bg-surface pl-11 pr-4 text-sm outline-none focus:border-cta focus:ring-2 focus:ring-cta/20"
                  />
                </div>
                <button
                  type="submit"
                  disabled={!emailValid}
                  className="inline-flex h-14 w-full items-center justify-center gap-2 rounded-2xl bg-cta text-sm font-bold text-cta-foreground shadow-cta transition hover:bg-cta-hover disabled:opacity-50"
                >
                  {data.contact.submitLabel}
                  <ArrowRight className="h-4 w-4" />
                </button>
                <p className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
                  <ShieldCheck className="h-3.5 w-3.5 text-primary" />
                  100% gratuit, sans engagement
                </p>
                <button
                  type="button"
                  onClick={() => setStep((s) => Math.max(0, s - 1))}
                  className="text-xs font-medium text-muted-foreground hover:text-foreground"
                >
                  ← Retour
                </button>
              </form>
            ) : isCoordinates ? (
              <form
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!coordinatesValid) return;
                  // POC : rien n'est transmis.
                  setSubmitted(true);
                }}
              >
                <span className="inline-flex w-fit items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">
                  {data.coordinates.badge}
                </span>
                <div>
                  <p className="text-base font-bold text-foreground">{data.coordinates.label}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{data.coordinates.helper}</p>
                </div>
                <div className="space-y-3">
                  <CoordinateField
                    id="hub-assistant-name"
                    icon={<User className="h-4 w-4" />}
                    label={data.coordinates.fields.name}
                    value={name}
                    onChange={setName}
                    type="text"
                  />
                  <CoordinateField
                    id="hub-assistant-phone"
                    icon={<Phone className="h-4 w-4" />}
                    label={data.coordinates.fields.phone}
                    value={phone}
                    onChange={setPhone}
                    type="tel"
                  />
                  <CoordinateField
                    id="hub-assistant-postal"
                    icon={<MapPin className="h-4 w-4" />}
                    label={data.coordinates.fields.postalCode}
                    value={postalCode}
                    onChange={setPostalCode}
                    type="text"
                  />
                  <CoordinateField
                    id="hub-assistant-address"
                    icon={<Home className="h-4 w-4" />}
                    label={data.coordinates.fields.address}
                    value={address}
                    onChange={setAddress}
                    type="text"
                  />
                </div>
                <button
                  type="submit"
                  disabled={!coordinatesValid}
                  className="inline-flex h-14 w-full items-center justify-center gap-2 rounded-2xl bg-cta text-sm font-bold text-cta-foreground shadow-cta transition hover:bg-cta-hover disabled:opacity-50"
                >
                  {data.coordinates.submitLabel}
                  <ArrowRight className="h-4 w-4" />
                </button>
                <p className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
                  <ShieldCheck className="h-3.5 w-3.5 text-primary" />
                  100% gratuit, sans engagement
                </p>
                <button
                  type="button"
                  onClick={() => setStep((s) => Math.max(0, s - 1))}
                  className="text-xs font-medium text-muted-foreground hover:text-foreground"
                >
                  ← Retour
                </button>
              </form>
            ) : (
              current && (
                <div className="space-y-4">
                  <h3 className="text-base font-bold text-foreground sm:text-lg">{current.label}</h3>
                  <div className="flex flex-col gap-2">
                    {current.options.map((option, index) => (
                      <OptionButton
                        key={option}
                        label={option}
                        icon={current.illustrations?.[index]}
                        selected={isSelected(current.id, option)}
                        onClick={() => selectOption(current.id, option, current.multi)}
                      />
                    ))}
                  </div>
                  {current.multi && (
                    <button
                      type="button"
                      disabled={!hasAnswer}
                      onClick={() => setStep((s) => s + 1)}
                      className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-cta text-sm font-bold text-cta-foreground shadow-cta transition hover:bg-cta-hover disabled:opacity-50"
                    >
                      Continuer
                      <ArrowRight className="h-4 w-4" />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setStep((s) => Math.max(0, s - 1))}
                    className="text-xs font-medium text-muted-foreground hover:text-foreground"
                  >
                    ← Retour
                  </button>
                </div>
              )
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

/** Option de réponse — icône facultative, pastille de sélection à droite. */
function OptionButton({
  label,
  icon,
  selected,
  onClick,
}: {
  label: string;
  icon?: Parameters<typeof HubIcon>[0]['name'];
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`group flex items-center justify-between gap-3 rounded-2xl border-2 px-4 py-2.5 text-left text-sm transition ${
        selected ? 'border-cta bg-cta/5' : 'border-border bg-card hover:border-cta/30 hover:bg-surface'
      }`}
    >
      <span className="flex items-center gap-3">
        {icon && (
          <span
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition ${
              selected ? 'bg-cta/10 text-cta' : 'bg-primary/5 text-primary'
            }`}
          >
            <HubIcon name={icon} className="h-4 w-4" />
          </span>
        )}
        <span className={`font-semibold ${selected ? 'text-primary' : 'text-foreground'}`}>
          {label}
        </span>
      </span>
      <span
        className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 transition ${
          selected ? 'border-cta bg-card' : 'border-border group-hover:border-cta/50'
        }`}
      >
        {selected && <span className="h-2.5 w-2.5 rounded-full bg-cta" />}
      </span>
    </button>
  );
}

/**
 * Champ de l'étape coordonnées. Calqué sur l'input e-mail (même arrondi, même
 * focus orange) pour rester dans le langage visuel du questionnaire. Le libellé
 * sert de placeholder ET d'`aria-label` (pas de label visible dans la maquette).
 */
function CoordinateField({
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
        className="h-12 w-full rounded-xl border border-border bg-surface pl-11 pr-4 text-sm outline-none focus:border-cta focus:ring-2 focus:ring-cta/20"
      />
    </div>
  );
}

/** Écran de confirmation. Aucune donnée n'a été envoyée (POC). */
function Success({ data, onRestart }: { data: HubAssistant; onRestart: () => void }) {
  return (
    <div className="text-center">
      <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-success/10">
        <Check className="h-7 w-7 text-success" />
      </span>
      <h3 className="mt-3 text-lg font-bold text-foreground">{data.success.title}</h3>
      <p className="mt-2 text-sm text-muted-foreground">{data.success.subtitle}</p>

      <div className="mt-5 rounded-2xl border border-border bg-surface p-5">
        <p className="text-center text-sm font-bold text-primary">{data.success.nextStepsTitle}</p>
        <span className="mx-auto mt-1 block h-0.5 w-10 rounded-full bg-primary" />
        <ol className="mt-5 grid grid-cols-3 gap-3">
          {data.success.nextSteps.map((next, index) => (
            <li key={next.title} className="flex flex-col items-center text-center">
              <span className="relative flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                <HubIcon name={next.icon} className="h-6 w-6 text-primary" />
                <span className="absolute -bottom-1 flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground">
                  {index + 1}
                </span>
              </span>
              <span className="mt-3 text-xs font-bold text-foreground sm:text-sm">{next.title}</span>
              {next.desc && (
                <span className="mt-1 text-[11px] leading-snug text-muted-foreground">
                  {next.desc}
                </span>
              )}
            </li>
          ))}
        </ol>
      </div>

      <button
        type="button"
        onClick={onRestart}
        className="mt-5 inline-flex h-14 w-full items-center justify-center gap-2 rounded-2xl bg-cta text-sm font-bold text-cta-foreground shadow-cta transition hover:bg-cta-hover"
      >
        {data.success.ctaLabel}
        <ArrowRight className="h-4 w-4" />
      </button>
      <p className="mt-4 border-t border-border pt-4 text-xs text-muted-foreground">
        {data.success.helpLine}
      </p>
    </div>
  );
}
