'use client';

import { useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import { ArrowRight, Download, Mail, MapPin, ShieldCheck, User } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { HubIcon } from './primitives';
import { PhoneField } from './PhoneField';
import { Confetti } from './Confetti';
import { useAutoDownload } from '@/lib/hub/useAutoDownload';
import { getRememberedEmail, rememberEmail } from '@/lib/hub/leadEmailCookie';
import { isValidPhone } from '@/lib/hub/validation';
import type { HubAssistant } from '@/types/hub';

/**
 * Questionnaire du hero — « Recevez votre plan projet personnalisé ».
 *
 * Branché sur `POST /api/demande` (spec `spec_hub/hub_formulaire.txt`) : parcours
 * questionnaire → e-mail (APPEL 1) → coordonnées (APPEL 2) → succès. L'étape
 * coordonnées collecte : civilité, Nom + Prénom (fusionnés en `nom_prenom`
 * relié par « _ »), Téléphone (indicateur pays), Code postal.
 * Le pays choisi est envoyé dans `coordonnees.pays` (colonne serveur à créer).
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

export function AssistantForm({ data, idPageHub }: { data: HubAssistant; idPageHub: number }) {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string | string[]>>({});
  const [email, setEmail] = useState('');
  const [civilite, setCivilite] = useState('');
  const [nom, setNom] = useState('');
  const [prenom, setPrenom] = useState('');
  const [phone, setPhone] = useState('');
  const [postalCode, setPostalCode] = useState('');
  // Pays choisi dans l'indicateur téléphone (envoyé + stocké côté serveur).
  const [pays, setPays] = useState('France');
  // `dialCode` sert à distinguer « numéro national saisi » de « juste l'indicatif »
  // pour l'erreur de longueur.
  const [dialCode, setDialCode] = useState('33');
  const [submitted, setSubmitted] = useState(false);
  const [forceOpen, setForceOpen] = useState(false);
  // Fermeture en cours : garde le contenu (Success) affiché pendant l'animation
  // de sortie du dialog, puis on réinitialise. Sans ça, le reset synchrone fait
  // apparaître le questionnaire dans le dialog qui se ferme.
  const [closing, setClosing] = useState(false);
  // Verrou anti double-soumission (§11) + message d'erreur technique (§7/§9).
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  // Garde : ne déclenche qu'UNE fois l'auto-envoi « e-mail mémorisé » par parcours.
  const autoSentRef = useRef(false);
  // Visiteur reconnu : capturé UNE SEULE fois après le montage (pas lu à chaque
  // render). Sinon l'écriture du cookie à la soumission ferait clignoter le
  // remerciement pendant que la requête est en vol.
  const [recognized, setRecognized] = useState(false);

  // Flux : questionnaire (0..N-1) → e-mail (N) → coordonnées (N+1) → succès.
  const totalSteps = data.steps.length + 2;
  const isContact = step === data.steps.length;
  const isCoordinates = step === data.steps.length + 1;
  // Visiteur reconnu à l'étape e-mail → on affiche le remerciement (APPEL 1 en fond).
  const skipEmailStep = isContact && recognized;
  const current = step < data.steps.length ? data.steps[step] : null;
  // 100% au succès quel que soit le chemin (e-mail reconnu = 1 seul appel).
  const progressPct = submitted ? 100 : (step / totalSteps) * 100;

  const reset = () => {
    setStep(0);
    setAnswers({});
    setEmail('');
    setCivilite('');
    setNom('');
    setPrenom('');
    setPhone('');
    setPostalCode('');
    setPays('France');
    setDialCode('33');
    setSubmitted(false);
    setForceOpen(false);
    setSubmitting(false);
    setErrorMsg('');
    autoSentRef.current = false;
  };

  /**
   * Construit le payload attendu par `/api/demande` (spec §6). Les libellés font
   * foi (§4) : la question = `step.label`, les réponses = les libellés de choix
   * cochés. On omet les questions sans réponse. `coordonnees` n'est joint qu'à
   * l'appel 2. `referer` = URL réelle du visiteur, tronquée à 500 (§10).
   */
  const buildPayload = (withCoordinates: boolean, emailOverride?: string) => {
    const reponses = data.steps
      .map((s) => {
        const value = answers[s.id];
        const list = Array.isArray(value) ? value : value ? [value] : [];
        return { question: s.label, reponses: list };
      })
      .filter((r) => r.reponses.length > 0);

    const referer = typeof window !== 'undefined' ? window.location.href.slice(0, 500) : '';

    return {
      email: emailOverride ?? email,
      id_page_hub: idPageHub,
      referer,
      reponses,
      ...(withCoordinates
        ? {
            coordonnees: {
              // `civilite` : nouveau champ, colonne serveur à venir (ignoré d'ici là).
              civilite,
              // Nom et Prénom reliés par « _ » pour être re-séparables dans le BO.
              nom_prenom: `${nom.trim()}_${prenom.trim()}`,
              telephone: phone,
              code_postal: postalCode,
              pays, // pays choisi dans l'indicateur téléphone
            },
          }
        : {}),
    };
  };

  /**
   * Envoie un appel à `/api/demande`. Un seul appel en vol à la fois (§11).
   * 201 / `statut:"enregistre"` → succès (bouton jamais réactivé).
   * 200 / `statut:"coordonnees_requises"` → passe à l'étape coordonnées.
   * Tout le reste → message technique générique, bouton réactivé (§7/§9).
   */
  const send = async (withCoordinates: boolean, emailOverride?: string) => {
    if (submitting) return;
    setSubmitting(true);
    setErrorMsg('');
    try {
      const res = await fetch('/api/demande', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload(withCoordinates, emailOverride)),
      });
      let corps: { statut?: string } | null = null;
      try {
        corps = await res.json();
      } catch {
        corps = null;
      }

      if (res.status === 201 || corps?.statut === 'enregistre') {
        // Mémorise l'e-mail seulement après un enregistrement réel (201).
        rememberEmail(emailOverride ?? email);
        setSubmitted(true); // succès : le bouton disparaît, on ne réactive pas.
        return;
      }
      if (res.status === 200 && corps?.statut === 'coordonnees_requises') {
        setStep((s) => s + 1);
        setSubmitting(false);
        return;
      }
      console.error('[AssistantForm] réponse inattendue', res.status, corps);
      setErrorMsg('Une erreur technique est survenue. Merci de réessayer.');
      setSubmitting(false);
    } catch (err) {
      console.error('[AssistantForm] échec réseau', err);
      setErrorMsg('Une erreur technique est survenue. Merci de réessayer.');
      setSubmitting(false);
    }
  };

  useEffect(() => {
    const handler = () => {
      reset();
      setClosing(false); // annule une fermeture en cours si on rouvre aussitôt
      setForceOpen(true);
    };
    window.addEventListener(ASSISTANT_DIALOG_EVENT, handler);
    return () => window.removeEventListener(ASSISTANT_DIALOG_EVENT, handler);
  }, []);

  // Lit le cookie UNE fois après le montage (client-only, pas de mismatch SSR).
  useEffect(() => {
    setRecognized(getRememberedEmail() !== '');
  }, []);

  // Visiteur reconnu : dès que les réponses sont finies (étape e-mail atteinte),
  // on lance l'APPEL 1 en arrière-plan. Le remerciement est déjà affiché par
  // `skipEmailStep` — aucune étape e-mail, aucune transition.
  useEffect(() => {
    if (!isContact || !recognized || autoSentRef.current || submitting || submitted) return;
    autoSentRef.current = true;
    const remembered = getRememberedEmail();
    setEmail(remembered);
    void send(false, remembered);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isContact, recognized, submitting, submitted]);

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
  const modalOpen = (forceOpen || step > 0 || submitted) && !closing;
  const emailValid = EMAIL_RE.test(email);
  const coordinatesValid =
    nom.trim() !== '' &&
    prenom.trim() !== '' &&
    isValidPhone(phone) &&
    postalCode.trim() !== '';
  // Nombre de chiffres saisis, hors indicatif : distingue « juste l'indicatif »
  // (pas d'erreur) d'un « numéro national trop court » (erreur).
  const digitsOf = (s: string) => (s.match(/\d/g) ?? []).length;
  const phoneError = digitsOf(phone) > digitsOf(dialCode) && !isValidPhone(phone);

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
          // La croix ferme entièrement le questionnaire. On ferme d'abord (le
          // contenu reste stable pendant l'animation de sortie) puis on
          // réinitialise après l'animation → pas de flash du questionnaire.
          if (!open) {
            setClosing(true);
            window.setTimeout(() => {
              reset();
              setClosing(false);
            }, 250);
          }
        }}
      >
        <DialogContent className="max-w-lg p-0">
          <DialogHeader className="sr-only">
            <DialogTitle>{data.cardTitle}</DialogTitle>
            <DialogDescription>
              Questionnaire en {totalSteps} étapes pour recevoir votre plan projet.
            </DialogDescription>
          </DialogHeader>

          <div className="pl-6 pr-14 pt-5 sm:pl-8">
            <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-cta transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          <div className="px-6 py-4 sm:px-8">
            {submitted || skipEmailStep ? (
              // Visiteur reconnu : remerciement DIRECT (optimiste), pas d'étape vide.
              <Success data={data} />
            ) : isContact ? (
              <form
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!emailValid || submitting) return;
                  // APPEL 1 — sans coordonnées (§5).
                  void send(false);
                }}
              >
                <span className="inline-flex w-fit items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">
                  {data.contact.badge}
                </span>
                <div>
                  <label htmlFor="hub-assistant-email" className="block text-base font-bold text-foreground">
                    {data.contact.label}
                  </label>
                  {data.contact.helper && (
                    <p className="mt-1 text-xs text-muted-foreground">{data.contact.helper}</p>
                  )}
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
                {errorMsg && (
                  <p role="alert" className="text-xs font-medium text-destructive">
                    {errorMsg}
                  </p>
                )}
                <button
                  type="submit"
                  disabled={!emailValid || submitting}
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
                  disabled={submitting}
                  onClick={() => setStep((s) => Math.max(0, s - 1))}
                  className="text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
                >
                  ← Retour
                </button>
              </form>
            ) : isCoordinates ? (
              <form
                className="space-y-3"
                noValidate
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!coordinatesValid || submitting) return;
                  // APPEL 2 — avec coordonnées (§5). nom_prenom non vide (§8).
                  void send(true);
                }}
              >
                <span className="inline-flex w-fit items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">
                  {data.coordinates.badge}
                </span>
                <div>
                  <p className="text-base font-bold text-foreground">{data.coordinates.label}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{data.coordinates.helper}</p>
                </div>

                {/* Civilité — encart avec libellé + options (facultative). */}
                <div className="rounded-xl border border-border bg-card px-4 py-2">
                  <p className="text-xs text-muted-foreground">
                    {data.coordinates.civilityLabel}
                  </p>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    {data.coordinates.civilityOptions.map((option) => (
                      <label
                        key={option}
                        className="flex cursor-pointer items-center gap-2 text-sm text-foreground"
                      >
                        <input
                          type="radio"
                          name="hub-assistant-civilite"
                          checked={civilite === option}
                          onChange={() => setCivilite(option)}
                          className="h-4 w-4 accent-[var(--color-cta)]"
                        />
                        <span className={civilite === option ? 'font-semibold text-primary' : ''}>
                          {option}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Champs empilés pleine largeur (Prénom avant Nom, cf. maquette). */}
                <div className="space-y-2">
                  <CoordinateField
                    id="hub-assistant-prenom"
                    icon={<User className="h-4 w-4" />}
                    label={data.coordinates.fields.prenom}
                    value={prenom}
                    onChange={setPrenom}
                    type="text"
                  />
                  <CoordinateField
                    id="hub-assistant-nom"
                    icon={<User className="h-4 w-4" />}
                    label={data.coordinates.fields.name}
                    value={nom}
                    onChange={setNom}
                    type="text"
                  />
                  <PhoneField
                    value={phone}
                    ariaLabel={data.coordinates.fields.phone}
                    onChange={(nextPhone, country, code) => {
                      setPhone(nextPhone);
                      setPays(country);
                      setDialCode(code);
                    }}
                  />
                  {phoneError && (
                    <p role="alert" className="text-xs font-medium text-destructive">
                      Veuillez saisir un numéro de téléphone valide.
                    </p>
                  )}
                  <CoordinateField
                    id="hub-assistant-postal"
                    icon={<MapPin className="h-4 w-4" />}
                    label={data.coordinates.fields.postalCode}
                    value={postalCode}
                    onChange={setPostalCode}
                    type="text"
                  />
                </div>
                {errorMsg && (
                  <p role="alert" className="text-xs font-medium text-destructive">
                    {errorMsg}
                  </p>
                )}
                <button
                  type="submit"
                  disabled={!coordinatesValid || submitting}
                  className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-2xl bg-cta text-sm font-bold text-cta-foreground shadow-cta transition hover:bg-cta-hover disabled:opacity-50"
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
                  disabled={submitting}
                  onClick={() => setStep((s) => Math.max(0, s - 1))}
                  className="text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
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

/**
 * Écran de remerciement : merci + couverture du guide + bouton de téléchargement
 * (outline). Le guide est proposé au visiteur une fois sa demande enregistrée.
 */
function Success({ data }: { data: HubAssistant }) {
  const { success } = data;
  // Téléchargement auto du guide dès l'affichage de l'écran de remerciement.
  useAutoDownload(success.fileUrl);
  return (
    <div className="relative text-center">
      <Confetti />
      <h3 className="text-xl font-bold text-foreground sm:text-2xl">{success.title}</h3>

      <div className="relative mx-auto mt-5 h-56 w-40">
        <Image
          src={success.image.src}
          alt={success.image.alt}
          fill
          sizes="160px"
          className="object-contain"
        />
      </div>

      <p className="mx-auto mt-5 max-w-sm text-sm leading-relaxed text-muted-foreground">
        {success.subtitle}
      </p>

      <a
        href={success.fileUrl ?? '#'}
        download
        className="mt-6 inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium text-muted-foreground transition hover:text-cta"
      >
        <Download className="h-4 w-4" />
        {success.downloadLabel}
      </a>
    </div>
  );
}
