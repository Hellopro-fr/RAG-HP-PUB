// Délai de reconnexion WebSocket : backoff exponentiel borné.
// attempt 0 → 1s, 1 → 2s, 2 → 4s, ... plafonné à 30s.
export const WS_BACKOFF_BASE_MS = 1000;
export const WS_BACKOFF_MAX_MS = 30_000;

export function wsBackoffDelay(attempt) {
  const n = Math.max(0, Math.floor(attempt ?? 0));
  return Math.min(WS_BACKOFF_BASE_MS * 2 ** n, WS_BACKOFF_MAX_MS);
}
