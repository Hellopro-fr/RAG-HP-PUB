'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Gestion du chargement d'une iframe formulaire avec retry automatique silencieux.
 *
 * Principe :
 *   - Tant que le formulaire n'a pas signalé `formReady`, un timeout par tentative
 *     (`timeoutMs`) est armé. S'il expire (ou si l'iframe renvoie une erreur de
 *     chargement), la tentative est considérée comme échouée.
 *   - Sur échec : on incrémente `attempt` (qui sert de `key` à l'iframe → remount =
 *     rechargement propre), jusqu'à `maxAttempts`.
 *   - Après `maxAttempts` échecs : on appelle `onClose()` → l'iframe est démontée et
 *     le scroll de la page est restauré (aucun bouton, tout est automatique).
 *   - Dès que le formulaire est prêt (`markReady()`), les retries s'arrêtent.
 *
 * Le consommateur doit :
 *   - poser `key={attempt}` sur l'<iframe> et ajouter un anti-cache (`&_retry=${attempt}`),
 *   - appeler `markReady()` à la réception de `hellopro_form_ready_for_minisite`,
 *   - brancher `onError={handleIframeError}` sur l'<iframe>.
 */

interface UseIframeAutoRetryOptions {
  /** Modal ouvert ? Réinitialise tout à chaque passage à true. */
  open: boolean;
  /** Fermeture (démonte l'iframe + restaure le scroll). Appelée après épuisement des tentatives. */
  onClose: () => void;
  /** Nombre de tentatives avant abandon. Défaut : 5. */
  maxAttempts?: number;
  /** Délai max d'une tentative avant retry (ms). Défaut : 7000. */
  timeoutMs?: number;
}

interface UseIframeAutoRetryResult {
  /** Compteur de tentative (0-indexé). À utiliser comme `key` de l'iframe + anti-cache. */
  attempt: number;
  /** true dès que le formulaire a signalé qu'il est prêt. */
  formReady: boolean;
  /** À appeler à la réception du message "form ready". */
  markReady: () => void;
  /** À brancher sur `onError` de l'iframe (échec réseau / chargement). */
  handleIframeError: () => void;
}

export function useIframeAutoRetry({
  open,
  onClose,
  maxAttempts = 5,
  timeoutMs = 7000,
}: UseIframeAutoRetryOptions): UseIframeAutoRetryResult {
  const [attempt, setAttempt] = useState(0);
  const [formReady, setFormReady] = useState(false);

  /* Refs : éviter les closures périmées et les re-armements parasites du timeout. */
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const formReadyRef = useRef(false);
  formReadyRef.current = formReady;
  const closedRef = useRef(false);

  /* Reset complet à chaque ouverture. */
  useEffect(() => {
    if (open) {
      setAttempt(0);
      setFormReady(false);
      closedRef.current = false;
    }
  }, [open]);

  /* Succès : le formulaire est prêt → on fige, plus aucun retry. */
  const markReady = useCallback(() => {
    if (closedRef.current) return;
    setFormReady(true);
  }, []);

  /* Échec d'une tentative (timeout ou onError) → retry ou abandon. */
  const failAttempt = useCallback(() => {
    if (formReadyRef.current || closedRef.current) return;
    setAttempt((prev) => {
      const next = prev + 1;
      if (next >= maxAttempts) {
        closedRef.current = true;
        onCloseRef.current();
        return prev;
      }
      return next;
    });
  }, [maxAttempts]);

  /* Timeout par tentative : ré-armé à chaque `attempt`, annulé dès `formReady`/fermeture/démontage. */
  useEffect(() => {
    if (!open || formReady) return;
    const id = window.setTimeout(failAttempt, timeoutMs);
    return () => window.clearTimeout(id);
  }, [open, formReady, attempt, timeoutMs, failAttempt]);

  return { attempt, formReady, markReady, handleIframeError: failAttempt };
}
