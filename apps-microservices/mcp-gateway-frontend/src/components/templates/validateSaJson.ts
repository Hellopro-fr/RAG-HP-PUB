// Shared client-side validation for Google service-account JSON files.
// Mirrors the backend validation.MaxSAJSONSize limit; checks the minimal
// structural invariants (type === "service_account" and client_email present)
// so obvious user mistakes are caught before the upload hits the server.

const MAX_SA_JSON_SIZE = 16 * 1024 // matches mcp-gateway-service validation.MaxSAJSONSize

export interface SaJsonValidation {
  ok: boolean
  clientEmail?: string
  error?: string
}

export async function validateSaJson(file: File): Promise<SaJsonValidation> {
  if (file.size > MAX_SA_JSON_SIZE) {
    return { ok: false, error: 'Fichier trop volumineux (max 16 Ko)' }
  }
  const text = await file.text()
  try {
    const j = JSON.parse(text) as { type?: string; client_email?: string }
    if (j.type !== 'service_account') {
      return {
        ok: false,
        error: `type est "${j.type ?? ''}", attendu "service_account"`
      }
    }
    if (!j.client_email) {
      return { ok: false, error: 'client_email manquant' }
    }
    return { ok: true, clientEmail: j.client_email }
  } catch {
    return { ok: false, error: 'JSON invalide' }
  }
}
