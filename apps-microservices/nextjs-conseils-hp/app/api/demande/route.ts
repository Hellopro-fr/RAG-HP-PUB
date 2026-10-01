import { NextResponse } from 'next/server';
import { z } from 'zod';

/**
 * Route Handler BFF — enregistrement des leads du formulaire HUB (`AssistantForm`).
 *
 * Le navigateur POST vers `/api/demande` (same-origin) ; cette route relaie vers
 * l'API Hellopro `page_conseil.php` avec le Bearer token, qui reste côté serveur
 * (jamais exposé au navigateur — cf. spec §2). Un seul endpoint, appelé une ou
 * deux fois selon le parcours (spec §5) :
 *   - APPEL 1 (sans `coordonnees`) → 201 (e-mail reconnu) ou 200 (coordonnées requises)
 *   - APPEL 2 (avec `coordonnees`) → 201
 *
 * Aucun e-mail n'est envoyé par le traitement : collecte et stockage uniquement.
 */

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const HP_BASE = process.env.HELLOPRO_API_URL ?? 'https://api.hellopro.fr';
const HP_DEMANDE_URL = `${HP_BASE}/api/hp/view/page_conseil.php`;
const API_TOKEN = process.env.CONSEILS_API_TOKEN ?? '';

/**
 * Schéma du payload commun aux DEUX formulaires HUB (projet + guide) : un seul
 * endpoint côté Hellopro les sert (spec guide §1). Zod retire silencieusement
 * toute clé inconnue. Les limites de longueur sont imposées ici car le serveur
 * ne tronque plus (un dépassement = erreur MySQL + fiche orpheline).
 *
 * Différences entre formulaires, absorbées par des champs optionnels :
 *  - `reponses` : présent (≥1) pour le projet, ABSENT pour le guide (pas de
 *    questionnaire → aucune ligne `hub_demande_reponse`).
 *  - `coordonnees.adresse` : fourni par le projet, OMIS par le guide (→ NULL).
 *
 * `referer` est TRONQUÉ (transform) plutôt que rejeté : une URL avec UTM dépasse
 * facilement 500 caractères et ne doit pas bloquer un lead légitime.
 */
const PayloadSchema = z.object({
  email: z.string().email().max(255),
  id_page_hub: z.number().int().positive().max(4_294_967_295).optional(),
  referer: z
    .string()
    .transform((s) => s.slice(0, 500))
    .optional(),
  reponses: z
    .array(
      z.object({
        question: z.string().min(1),
        reponses: z.array(z.string()).min(1),
      })
    )
    .min(1) // si présent : au moins une question répondue (projet)
    .optional(), // absent pour le formulaire guide
  coordonnees: z
    .object({
      nom_prenom: z.string().min(1).max(255), // non vide : pilote l'aiguillage (§8)
      telephone: z.string().max(30),
      code_postal: z.string().max(20),
      adresse: z.string().max(255).optional(), // facultatif (projet) / omis (guide)
      // Nouveaux champs (formulaire projet) : colonnes serveur à créer. En
      // attendant, le serveur ignore ces clés — on les déclare pour que Zod ne
      // les supprime pas au passage.
      civilite: z.string().max(30).optional(),
      pays: z.string().max(100).optional(),
    })
    .optional(),
});

type Payload = z.infer<typeof PayloadSchema>;

/**
 * Réponse simulée en l'absence de token (dev/local), pour dérouler le parcours
 * sans backend — même approche que `fetchConseilPage` qui sert les mocks.
 * Coordonnées présentes → 201 (enregistré) ; sinon → 200 (coordonnées requises).
 */
function devFallback(payload: Payload): NextResponse {
  if (payload.coordonnees) {
    return NextResponse.json(
      { statut: 'enregistre', id_demande: 0, contact_connu: 0 },
      { status: 201 }
    );
  }
  return NextResponse.json({ statut: 'coordonnees_requises' }, { status: 200 });
}

export async function POST(request: Request): Promise<NextResponse> {
  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return NextResponse.json({ erreur: 'validation' }, { status: 400 });
  }

  // Validation de dernier rempart côté serveur (§9) : ne jamais faire confiance
  // au navigateur, et surtout ne pas relayer un payload hors-limites à MySQL (§10).
  const parsed = PayloadSchema.safeParse(raw);
  if (!parsed.success) {
    return NextResponse.json({ erreur: 'validation' }, { status: 400 });
  }
  const payload = parsed.data;

  if (!API_TOKEN) {
    return devFallback(payload);
  }

  try {
    const res = await fetch(HP_DEMANDE_URL, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      cache: 'no-store',
    });

    const text = await res.text();

    // L'API PHP peut préfixer du texte de debug avant le JSON (cf. fetchConseilPage),
    // et renvoie du HTML (pas du JSON) en cas d'erreur SQL sans transaction (§12).
    // Un parsing impossible = erreur serveur, jamais une exception non gérée.
    const jsonMatch = text.match(/\{[\s\S]*\}$/);
    if (!jsonMatch) {
      console.error('[demande] réponse non parsable', res.status, text.slice(0, 500));
      return NextResponse.json({ erreur: 'technique' }, { status: 502 });
    }

    const corps = JSON.parse(jsonMatch[0]);

    // On propage status + corps tels quels pour que le front applique le §7
    // (400 générique, 401/403 config, 500 réessai) au lieu de tout aplatir.
    return NextResponse.json(corps, { status: res.status });
  } catch (err) {
    console.error('[demande] échec appel API', err);
    return NextResponse.json({ erreur: 'technique' }, { status: 502 });
  }
}
