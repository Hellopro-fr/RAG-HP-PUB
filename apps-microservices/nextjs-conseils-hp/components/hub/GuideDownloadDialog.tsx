'use client';

import { useEffect, useState } from 'react';
import { ArrowRight, BookOpen, CheckCircle2, Download, FileText, Mail, MapPin, Phone, User } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { HubTitle } from './primitives';
import type { HubGuideDialog } from '@/types/hub';

/**
 * Dialog de téléchargement du guide — ouvert par tous les boutons « guide » de
 * la page via l'événement window `hp:open-guide-dialog`.
 *
 * ⚠️ POC : aucune donnée transmise. Les 4 champs et le consentement sont validés
 * côté client puis jetés (cf. CLAUDE.md §11bis.4).
 */
const GUIDE_DIALOG_EVENT = 'hp:open-guide-dialog';

/** Ouvre le dialog depuis n'importe où (client uniquement). */
export function openGuideDialog() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(GUIDE_DIALOG_EVENT));
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function GuideDownloadDialog({ data }: { data: HubGuideDialog }) {
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState<'form' | 'success'>('form');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [postalCode, setPostalCode] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [emailError, setEmailError] = useState('');
  const [consentError, setConsentError] = useState('');

  useEffect(() => {
    const handler = () => {
      setPhase('form');
      setEmailError('');
      setConsentError('');
      setOpen(true);
    };
    window.addEventListener(GUIDE_DIALOG_EVENT, handler);
    return () => window.removeEventListener(GUIDE_DIALOG_EVENT, handler);
  }, []);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const validEmail = EMAIL_RE.test(email);
    setEmailError(validEmail ? '' : 'Veuillez saisir une adresse e-mail valide.');
    setConsentError(
      accepted ? '' : 'Veuillez accepter de recevoir la lettre d’informations.'
    );
    if (!validEmail || !accepted) return;
    // POC : rien n'est transmis.
    setPhase('success');
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-md">
        <DialogHeader className="sr-only">
          <DialogTitle>{data.badge}</DialogTitle>
          <DialogDescription>
            Recevez gratuitement le guide complet par e-mail.
          </DialogDescription>
        </DialogHeader>

        <div className="px-6 py-7 sm:px-8">
          {phase === 'form' ? (
            <>
              <h2 className="mx-auto mb-6 max-w-sm px-6 text-center text-xl font-bold leading-snug text-foreground sm:text-2xl">
                <HubTitle parts={data.titleParts} />
              </h2>

              <form onSubmit={submit} className="space-y-3" noValidate>
                <Field
                  id="guide-name"
                  icon={<User className="h-4 w-4" />}
                  label={data.fields.name}
                  value={name}
                  onChange={setName}
                  type="text"
                />
                <Field
                  id="guide-email"
                  icon={<Mail className="h-4 w-4" />}
                  label={data.fields.email}
                  value={email}
                  onChange={setEmail}
                  type="email"
                />
                {emailError && (
                  <p role="alert" className="text-xs font-medium text-destructive">
                    {emailError}
                  </p>
                )}
                <Field
                  id="guide-phone"
                  icon={<Phone className="h-4 w-4" />}
                  label={data.fields.phone}
                  value={phone}
                  onChange={setPhone}
                  type="tel"
                />
                <Field
                  id="guide-postal"
                  icon={<MapPin className="h-4 w-4" />}
                  label={data.fields.postalCode}
                  value={postalCode}
                  onChange={setPostalCode}
                  type="text"
                />

                <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-card p-3 transition hover:border-cta/30">
                  <input
                    type="checkbox"
                    checked={accepted}
                    onChange={(event) => setAccepted(event.target.checked)}
                    className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-cta)]"
                  />
                  <span className="text-xs leading-snug text-muted-foreground">
                    {data.consentLabel}
                  </span>
                </label>
                {consentError && (
                  <p role="alert" className="text-xs font-medium text-destructive">
                    {consentError}
                  </p>
                )}

                <button
                  type="submit"
                  className="inline-flex h-14 w-full items-center justify-center gap-3 rounded-xl bg-cta text-sm font-bold text-cta-foreground shadow-cta transition hover:bg-cta-hover"
                >
                  <Download className="h-5 w-5" />
                  {data.submitLabel}
                  <ArrowRight className="h-4 w-4" />
                </button>

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
          ) : (
            <div className="py-4 text-center">
              <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-success/10">
                <CheckCircle2 className="h-7 w-7 text-success" />
              </span>
              <h2 className="mt-3 text-lg font-bold text-foreground">{data.success.title}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {data.success.text} <span className="font-semibold text-foreground">{email}</span>.
              </p>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="mt-5 inline-flex h-11 items-center justify-center rounded-lg bg-cta px-5 text-sm font-bold text-cta-foreground shadow-cta transition hover:bg-cta-hover"
              >
                {data.success.closeLabel}
              </button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Champ de saisie. Le libellé sert de placeholder ET de `aria-label` : la maquette
 * n'a pas de labels visibles, mais un champ sans nom accessible est inutilisable
 * au lecteur d'écran.
 */
function Field({
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
