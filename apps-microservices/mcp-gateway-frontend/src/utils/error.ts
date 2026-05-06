// toErrorMessage: narrow an unknown caught value (TS strict mode forces
// `unknown` in catch clauses) into a human-readable string. Use anywhere
// a try/catch needs to surface a toast or inline message.
//
// Order:
//   1. Error instances → .message
//   2. ApiError body { error: string } → that string (gateway convention)
//   3. ApiError body { detail: string } → that string (FastAPI convention)
//   4. ApiError statusText fallback
//   5. Stringified primitive
import { ApiError } from '@/types/api'

export function toErrorMessage(err: unknown, fallback = 'Erreur'): string {
  if (err instanceof ApiError) {
    const body = err.body
    if (body && typeof body === 'object') {
      const rec = body as Record<string, unknown>
      if (typeof rec.error === 'string') return rec.error
      if (typeof rec.detail === 'string') return rec.detail
      if (typeof rec.message === 'string') return rec.message
    }
    return err.statusText || fallback
  }
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  return fallback
}
