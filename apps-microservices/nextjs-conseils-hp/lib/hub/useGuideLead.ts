'use client';

import { useCallback, useRef, useState } from 'react';
import { isValidPhone } from './validation';
import { markLeadKnown } from './leadEmailCookie';
import { pushHubEvent, type HubEntryPoint } from '@/lib/analytics/hub';

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

/**
 * `entryPoint` sert UNIQUEMENT au tracking : quatre emplacements de la page
 * ouvrent le même dialog, et savoir lequel convertit décide de ce qu'on garde.
 * Passé en argument plutôt que fixé dans le hook : le dialog est ouvert par un
 * événement `window`, donc l'emplacement n'est connu qu'au moment du clic.
 */
export function useGuideLead(
  idPageHub: number,
  entryPoint: HubEntryPoint,
  /**
   * Id du PROJET, portée du drapeau « déjà converti ».
   *
   * Distinct d'`idPageHub`, qui identifie le TUNNEL guide auprès de l'API (les
   * leads guide sont volontairement séparés des leads projet, cf.
   * `guideIdPageHub`). Le drapeau, lui, suit le projet : sinon remplir le
   * questionnaire ne dispenserait pas du formulaire guide sur la même page.
   */
  pageId: number
) {
  /**
   * ⚠️ Lu via un ref, pas via la closure.
   *
   * `GuideDownloadDialog` enregistre son écouteur d'ouverture UNE seule fois
   * (`useEffect` avec `[reset]`), et ce gestionnaire appelle `send()` pour le
   * visiteur reconnu. Cette closure capture le `send` du PREMIER rendu, donc la
   * valeur initiale d'`entryPoint` — la conversion serait attribuée au bandeau
   * guide même si le clic venait du CTA final. Le ref est réassigné à chaque
   * rendu : `send` y lit toujours la valeur courante, d'où qu'il soit appelé.
   */
  const entryPointRef = useRef(entryPoint);
  entryPointRef.current = entryPoint;

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

  /**
   * Un seul appel en vol à la fois (§5). withCoordinates=false → APPEL 1.
   * `emailOverride` permet d'envoyer un e-mail sans attendre la mise à jour de l'état.
   *
   * ⚠️ `send()` n'est appelé QUE sur une saisie réelle du visiteur. Le raccourci
   * « lead déjà connu » (cookie `hub_lead`) va directement à l'écran de
   * téléchargement sans passer par ici — donc sans appel API. Une option
   * `alreadyConverted` avait été ajoutée côté tracking pour neutraliser les
   * événements de tunnel dans ce cas : elle est devenue inutile et a été retirée
   * avec le comportement qu'elle compensait.
   */
  const send = async (withCoordinates: boolean, emailOverride?: string) => {
    if (submitting) return;
    const from = entryPointRef.current;
    const emailToUse = emailOverride ?? email;
    setSubmitting(true);
    setErrorMsg('');
    try {
      const referer = typeof window !== 'undefined' ? window.location.href.slice(0, 500) : '';
      const payload = {
        email: emailToUse,
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
        // ⚠️ La conversion est reconnue par CETTE condition, pas par le seul code
        // HTTP : l'API renvoie 200 + `statut:"enregistre"` sur certains
        // environnements (vérifié en recette le 2026-08-05, e-mail connu).
        if (!withCoordinates) {
          // Succès dès l'appel 1 ⇒ le serveur connaissait déjà le contact.
          pushHubEvent('hub_email_check', 'guide', { email_check_result:'known', hub_entry_point: from });
        }
        pushHubEvent('hub_form_submission', 'guide', {
          form_id: 'guide',
          id_page_hub: idPageHub,
          hub_entry_point: from,
          hub_lead_path: withCoordinates ? 'complet' : 'reconnu',
          user_known_status: withCoordinates ? 'Unknown' : 'Known',
        });
        // Marque le drapeau UNIQUEMENT après un enregistrement réel (201) : un
        // 200 (coordonnées requises, rien écrit) ne doit pas « reconnaître » le
        // visiteur au prochain passage. On ne stocke PAS l'e-mail (cf. cookie).
        markLeadKnown(pageId);
        setPhase('download');
        setSubmitting(false);
        return;
      }
      if (res.status === 200 && corps?.statut === 'coordonnees_requises') {
        // `result:'unknown'` vaut AUSSI « étape coordonnées affichée » : c'est la
        // même branche qui change de phase. Pas de `hub_form_coordinates_view`,
        // qui serait le même instant sous un second nom.
        pushHubEvent('hub_email_check', 'guide', { email_check_result:'unknown', hub_entry_point: from });
        setPhase('coordinates');
        setSubmitting(false);
        return;
      }
      console.error('[useGuideLead] réponse inattendue', res.status, corps);
      pushHubEvent('hub_form_error', 'guide', {
        form_id: 'guide',
        hub_entry_point: from,
        error_stage: withCoordinates ? 'coordinates' : 'email',
        http_status: res.status,
      });
      setErrorMsg('Une erreur technique est survenue. Merci de réessayer.');
      setSubmitting(false);
    } catch (err) {
      console.error('[useGuideLead] échec réseau', err);
      // `http_status: 0` = échec réseau, à distinguer d'une réponse serveur
      // inattendue : une coupure et un bug d'API ne se corrigent pas pareil.
      pushHubEvent('hub_form_error', 'guide', {
        form_id: 'guide',
        hub_entry_point: from,
        error_stage: withCoordinates ? 'coordinates' : 'email',
        http_status: 0,
      });
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
