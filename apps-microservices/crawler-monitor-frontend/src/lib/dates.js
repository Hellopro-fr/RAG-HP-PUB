/**
 * Parsing des dates renvoyées par l'API crawler-monitor.
 *
 * Le backend a longtemps renvoyé des timestamps Python naïfs
 * (« 2026-08-28 13:20:03.306901 ») : pas de « T », pas de « Z ». Passés tels
 * quels à `new Date()`, Chrome les interprète en heure LOCALE (décalage d'1 à
 * 2 h) et Safari renvoie `Invalid Date`. Après le correctif backend, le format
 * devient du RFC3339 (« …Z »).
 *
 * `parseApiDate` accepte les deux formes, considère l'absence de fuseau comme
 * de l'UTC, et retourne `null` (jamais `Invalid Date`) sur une entrée illisible.
 */

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const HAS_TZ = /(?:Z|z|[+-]\d{2}:?\d{2})$/;

/**
 * @param {string|number|Date|null|undefined} value
 * @returns {Date|null} Date valide, ou null si l'entrée est absente/illisible.
 */
export function parseApiDate(value) {
  if (value == null || value === '') return null;

  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }

  if (typeof value === 'number') {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  if (typeof value !== 'string') return null;

  const raw = value.trim();
  if (!raw) return null;

  // Date seule (« 2026-08-28 ») : déjà interprétée en UTC par la spec ES.
  let candidate = DATE_ONLY.test(raw) ? raw : raw.replace(' ', 'T');
  // Pas de fuseau explicite → on force l'UTC plutôt que l'heure locale.
  if (!DATE_ONLY.test(candidate) && !HAS_TZ.test(candidate)) candidate += 'Z';

  const d = new Date(candidate);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Timestamp en ms, ou `null` si la date est absente/illisible. */
export function parseApiDateMs(value) {
  const d = parseApiDate(value);
  return d ? d.getTime() : null;
}

const DEFAULT_FMT = { dateStyle: 'short', timeStyle: 'short' };

/**
 * Rendu fr-FR d'une date API. Retourne `fallback` (« — ») si illisible.
 * @param {*} value
 * @param {Intl.DateTimeFormatOptions} [options]
 * @param {string} [fallback]
 */
export function formatApiDate(value, options = DEFAULT_FMT, fallback = '—') {
  const d = parseApiDate(value);
  if (!d) return fallback;
  try {
    return d.toLocaleString('fr-FR', options);
  } catch {
    return fallback;
  }
}
