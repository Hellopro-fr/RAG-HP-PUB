'use client';

import { useCallback, useState } from 'react';
import { isValidPhone } from './validation';

/**
 * Flux commun aux deux points d'entrée « guide » (dialog `GuideDownloadDialog`
 * et pop-up `LeadPopup`) : même endpoint `/api/demande`, même parcours 2 appels
 * (spec `spec_hub/hub_guide.txt`).
 *
 *   e-mail → APPEL 1 (sans `reponses`/`coordonnees`)
 *              · 201 → phase `download` (e-mail reconnu)
 *              · 200 → phase `coordinates`
 *   coordonnées → APPEL 2 → 201 → `download`
 *
 * L'étape coordonnées collecte : civilité (facultative), Nom + Prénom (fusionnés
 * en `nom_prenom` relié par « _ »), téléphone (indicateur pays → `pays`), code
 * postal. Pas d'adresse. `civilite` et `pays` sont des colonnes serveur à créer
 * (ignorées d'ici là).
 *
 * Ne gère PAS l'écran e-mail spécifique (design de chaque composant) : chacun
 * valide son e-mail puis appelle `send(false)`.
 */
export type GuideLeadPhase = 'email' | 'coordinates' | 'download';

export function useGuideLead(idPageHub: number) {
  const [phase, setPhase] = useState<GuideLeadPhase>('email');
  const [email, setEmail] = useState('');
  const [civilite, setCivilite] = useState('');
  const [nom, setNom] = useState('');
  const [prenom, setPrenom] = useState('');
  const [phone, setPhone] = useState('');
  const [postalCode, setPostalCode] = useState('');
  const [pays, setPays] = useState('France');
  const [dialCode, setDialCode] = useState('33');
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const coordinatesValid =
    nom.trim() !== '' && prenom.trim() !== '' && isValidPhone(phone) && postalCode.trim() !== '';
  // Erreur tél seulement si un numéro national trop court est saisi (hors indicatif).
  const digitsOf = (s: string) => (s.match(/\d/g) ?? []).length;
  const phoneError = digitsOf(phone) > digitsOf(dialCode) && !isValidPhone(phone);

  const reset = useCallback(() => {
    setPhase('email');
    setEmail('');
    setCivilite('');
    setNom('');
    setPrenom('');
    setPhone('');
    setPostalCode('');
    setPays('France');
    setDialCode('33');
    setSubmitting(false);
    setErrorMsg('');
  }, []);

  /** Un seul appel en vol à la fois (§5). withCoordinates=false → APPEL 1. */
  const send = async (withCoordinates: boolean) => {
    if (submitting) return;
    setSubmitting(true);
    setErrorMsg('');
    try {
      const referer = typeof window !== 'undefined' ? window.location.href.slice(0, 500) : '';
      const payload = {
        email,
        id_page_hub: idPageHub,
        referer,
        ...(withCoordinates
          ? {
              coordonnees: {
                civilite,
                nom_prenom: `${nom.trim()}_${prenom.trim()}`,
                telephone: phone,
                code_postal: postalCode,
                pays,
              },
            }
          : {}),
      };
      const res = await fetch('/api/demande', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      let corps: { statut?: string } | null = null;
      try {
        corps = await res.json();
      } catch {
        corps = null;
      }

      if (res.status === 201 || corps?.statut === 'enregistre') {
        setPhase('download');
        setSubmitting(false);
        return;
      }
      if (res.status === 200 && corps?.statut === 'coordonnees_requises') {
        setPhase('coordinates');
        setSubmitting(false);
        return;
      }
      console.error('[useGuideLead] réponse inattendue', res.status, corps);
      setErrorMsg('Une erreur technique est survenue. Merci de réessayer.');
      setSubmitting(false);
    } catch (err) {
      console.error('[useGuideLead] échec réseau', err);
      setErrorMsg('Une erreur technique est survenue. Merci de réessayer.');
      setSubmitting(false);
    }
  };

  return {
    phase,
    setPhase,
    email,
    setEmail,
    civilite,
    setCivilite,
    nom,
    setNom,
    prenom,
    setPrenom,
    phone,
    setPhone,
    postalCode,
    setPostalCode,
    pays,
    setPays,
    dialCode,
    setDialCode,
    submitting,
    errorMsg,
    coordinatesValid,
    phoneError,
    send,
    reset,
  };
}

export type GuideLead = ReturnType<typeof useGuideLead>;
