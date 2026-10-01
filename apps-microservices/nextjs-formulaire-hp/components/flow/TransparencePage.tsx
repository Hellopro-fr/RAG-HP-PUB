'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Image from 'next/image';
import { ArrowLeft, ArrowRight, CheckCircle, Lock, Mail, ShieldCheck } from 'lucide-react';
import QuestionnaireProgressBar from './QuestionnaireProgressBar';
import TransparenceTableBackground from './TransparenceTableBackground';
import { getAssetPath } from '@/lib/utils';
import { useFlowStore } from '@/lib/stores/flow-store';
import { useBuyerCheck } from '@/hooks/api';
import { trackTransparenceView, trackTransparenceComplete } from '@/lib/analytics';
import type { ContactFormData } from '@/types';

const hpLogo = getAssetPath('/images/hp-logo.svg');

// Même stack système que AssurancePage (override de la font Inter globale)
const SYSTEM_FONT_STACK =
  'ui-sans-serif, system-ui, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji"';

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Délai avant de déclencher la vérification acheteur pendant la frappe :
// chaque email valide intermédiaire ("a@b.co" puis "a@b.com"...) déclencherait
// sinon les 2 appels API de checkBuyerExists.
const BUYER_CHECK_DEBOUNCE_MS = 350;

interface TransparencePageProps {
  /** Retour à la dernière question du questionnaire */
  onBack: () => void;
  /** Email validé et persisté → passage au loader de matching */
  onContinue: () => void;
}

/**
 * Étape « transparence » — affichée entre la dernière question du questionnaire
 * et le loader de matching, pour toutes les variantes A/B.
 *
 * Fond : le tableau final de produits (même composant que /selection), flouté.
 * Premier plan : champ email obligatoire. La vérification acheteur
 * (useBuyerCheck) tourne pendant la frappe ; acheteur reconnu → badge
 * « Nous vous avons reconnu ». Les données reconnues sont persistées dans le
 * store (contactData) au clic CTA pour pré-remplir les formulaires des étapes
 * suivantes.
 */
const TransparencePage = ({ onBack, onContinue }: TransparencePageProps) => {
  const { categoryName, categoryId, contactData, setContactData } = useFlowStore();

  // Pré-rempli si l'utilisateur revient après avoir déjà validé cette étape
  const [email, setEmail] = useState<string>(() => contactData?.email ?? '');
  const [showError, setShowError] = useState(false);

  const isEmailValid = useMemo(() => EMAIL_REGEX.test(email.trim()), [email]);

  // Débounce de l'email avant la vérification acheteur
  const [debouncedEmail, setDebouncedEmail] = useState(email);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedEmail(email), BUYER_CHECK_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [email]);

  // Vérification pendant la frappe : même queryKey que les formulaires aval
  // (email + rubriqueId) → le cache react-query (2 min) leur évite un
  // nouvel appel. Acheteur reconnu → badge « Nous vous avons reconnu ».
  const { data: buyerCheckResult } = useBuyerCheck(
    {
      email: debouncedEmail,
      rubriqueId: categoryId?.toString(),
    },
    EMAIL_REGEX.test(debouncedEmail.trim())
  );

  const isKnownBuyer = buyerCheckResult?.isKnown || false;

  // Tracking vue (une seule fois, hors retour navigateur — pattern AssurancePage)
  const hasTrackedView = useRef(false);
  useEffect(() => {
    if (hasTrackedView.current) return;

    const navEntries = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[];
    const navType = navEntries.length > 0 ? navEntries[0].type : 'navigate';
    if (navType === 'back_forward') return;

    hasTrackedView.current = true;
    trackTransparenceView();
  }, []);

  const handleContinue = () => {
    if (!isEmailValid) {
      setShowError(true);
      return;
    }

    // Snapshot contactData : mapper infoBuyer champ par champ UNIQUEMENT si
    // l'acheteur est reconnu (l'objet brut contient une clé `verif` sinon).
    // Si la vérification est encore en vol, on n'attend pas : les formulaires
    // aval relancent le même queryKey depuis l'email semé.
    let snapshot: ContactFormData;
    if (buyerCheckResult?.isKnown && buyerCheckResult.infoBuyer) {
      const info = buyerCheckResult.infoBuyer as any;
      snapshot = {
        email,
        isKnown: true,
        civility: info.cv || '',
        firstName: info.prenom || '',
        lastName: info.nom || '',
        company: info.societe || '',
        phone: info.tel || '',
        countryCode: '+33',
        id_pays_tel: 1,
        message: '',
        id_acheteur: info.id || undefined,
      };
    } else {
      snapshot = {
        email,
        isKnown: false,
        civility: '',
        firstName: '',
        lastName: '',
        phone: '',
        countryCode: '+33',
        id_pays_tel: 1,
        message: '',
      };
    }

    setContactData(snapshot);
    trackTransparenceComplete(snapshot.isKnown);
    onContinue();
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background">
      {/* Header simplifié — logo seul */}
      <div className="px-4 py-2.5 sm:px-6 border-b border-border">
        <Image src={hpLogo} alt="Hellopro" width={120} height={28} className="h-6 sm:h-7 w-auto" />
      </div>

      {/* Bandeau catégorie + barre de progression pleine (questionnaire terminé).
          Pas d'override de police ici : rendu strictement identique au bandeau
          du questionnaire (Inter globale). */}
      <QuestionnaireProgressBar
        categoryName={categoryName || ''}
        currentIndex={1}
        totalQuestions={1}
      />

      <div
        className="relative flex-1 overflow-hidden"
        style={{ fontFamily: SYSTEM_FONT_STACK }}
      >
        {/* Fond : tableau final de produits flouté (décoratif) */}
        <TransparenceTableBackground />

        {/* Premier plan : carte email */}
        <div className="absolute inset-0 overflow-y-auto">
          {/* Contenu ancré en haut (proportions de la maquette), pas centré verticalement */}
          <div className="px-4 sm:px-6 lg:px-10 pt-5 sm:pt-8 pb-24 sm:pb-8">
            <div className="mx-auto w-full max-w-2xl space-y-5">
              <div className="text-center space-y-2">
                <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-primary/10 text-primary ring-1 ring-primary/15">
                  <Mail className="h-5 w-5" strokeWidth={2.25} />
                </div>
                <h2 className="text-lg sm:text-xl lg:text-2xl font-bold text-foreground leading-tight">
                  Où souhaitez-vous recevoir vos devis ?
                </h2>
                <p className="text-sm text-muted-foreground max-w-md mx-auto">
                  Votre&nbsp;sélection est prête&nbsp;— recevez vos devis personnalisés
                </p>
              </div>

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleContinue();
                }}
                className="space-y-4 rounded-2xl border border-border/60 bg-card/95 backdrop-blur-sm shadow-xl shadow-foreground/5 p-4 sm:p-6"
              >
                <div
                  className={`rounded-xl border-2 bg-background transition-all ${
                    showError ? 'border-destructive/60' : 'border-border focus-within:border-primary/50'
                  }`}
                >
                  <label
                    htmlFor="transparence-email"
                    className="block px-4 pt-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
                  >
                    Adresse e-mail professionnelle
                  </label>
                  <div className="flex items-center gap-3 px-4 pb-3">
                    <input
                      id="transparence-email"
                      type="email"
                      inputMode="email"
                      autoComplete="email"
                      placeholder="prenom.nom@entreprise.fr"
                      maxLength={255}
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        if (showError) setShowError(false);
                      }}
                      className="flex-1 bg-transparent text-base text-foreground placeholder:text-muted-foreground/70 focus:outline-none"
                    />
                  </div>
                </div>

                {showError && (
                  <p className="text-xs text-destructive px-1">Ajouter votre adresse mail</p>
                )}

                {/* Acheteur reconnu — même badge que les formulaires de contact */}
                {isKnownBuyer && (
                  <div className="flex items-center gap-2 text-sm text-green-600 px-1">
                    <CheckCircle className="h-4 w-4" />
                    <span>Nous vous avons reconnu ! Vos informations sont pré-enregistrées.</span>
                  </div>
                )}

                {/* CTA mobile — pleine largeur dans la carte */}
                <button
                  type="submit"
                  className="sm:hidden flex w-full items-center justify-center gap-2 rounded-lg py-3 text-base font-semibold bg-accent text-accent-foreground shadow-lg shadow-accent/25 transition-all"
                >
                  Voir ma sélection et Recevoir mes devis
                </button>

                {/* Encart réassurance */}
                <div className="rounded-lg border border-primary/15 bg-primary/5 px-4 py-3 space-y-1.5">
                  <p className="flex items-center gap-2 text-xs text-foreground">
                    <ShieldCheck className="h-3.5 w-3.5 text-primary shrink-0" />
                    <span>Vos coordonnées restent strictement confidentielles.</span>
                  </p>
                  <p className="flex items-center gap-2 text-xs text-foreground">
                    <Lock className="h-3.5 w-3.5 text-primary shrink-0" />
                    <span>Aucune diffusion sans votre accord — zéro spam.</span>
                  </p>
                </div>

                {/* Footer desktop — Précédent + CTA */}
                <div className="hidden sm:flex items-center justify-between pt-2">
                  <button
                    type="button"
                    onClick={onBack}
                    className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-foreground hover:text-foreground/70 transition-colors"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    Précédent
                  </button>
                  <button
                    type="submit"
                    className="flex items-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold bg-accent text-accent-foreground hover:bg-accent/90 shadow-lg shadow-accent/25 transition-all"
                  >
                    Voir ma sélection et Recevoir mes devis
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>

      {/* Barre sticky mobile */}
      <div
        className="sm:hidden fixed bottom-0 left-0 right-0 z-20 bg-background/95 backdrop-blur border-t border-border/40 px-4 py-2.5 text-center"
        style={{ fontFamily: SYSTEM_FONT_STACK }}
      >
        <p className="text-xs text-foreground">
          À la fin →{' '}
          <span className="font-semibold text-primary">💰 Estimation de prix</span> +{' '}
          <span className="font-semibold text-primary">📦 Produits adaptés</span>
        </p>
      </div>
    </div>
  );
};

export default TransparencePage;
