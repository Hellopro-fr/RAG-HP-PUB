import { describe, it, expect, vi, afterEach } from 'vitest';

/**
 * Tests de la route `/api/demande` (enregistrement des leads HUB).
 * Le token est lu au chargement du module → on `resetModules()` + `import()`
 * dynamique après avoir positionné l'env, pour tester les deux branches.
 */

const validPayload = {
  email: 'jean@exemple.fr',
  id_page_hub: 1000,
  referer: 'https://conseils.hellopro.fr/x-1000-projet.html',
  reponses: [{ question: 'Question 1', reponses: ['Choix A'] }],
};

function makeRequest(body: unknown): Request {
  return new Request('http://localhost/api/demande', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
}

async function loadRoute(token: string) {
  vi.resetModules();
  vi.stubEnv('CONSEILS_API_TOKEN', token);
  return import('@/app/api/demande/route');
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('POST /api/demande', () => {
  it('renvoie 400 si le corps n’est pas du JSON', async () => {
    const { POST } = await loadRoute('');
    const res = await POST(makeRequest('pas du json'));
    expect(res.status).toBe(400);
  });

  it('renvoie 400 si l’e-mail est absent', async () => {
    const { POST } = await loadRoute('');
    const { email, ...sansEmail } = validPayload;
    void email;
    const res = await POST(makeRequest(sansEmail));
    expect(res.status).toBe(400);
  });

  it('renvoie 400 si aucune réponse (reponses vide)', async () => {
    const { POST } = await loadRoute('');
    const res = await POST(makeRequest({ ...validPayload, reponses: [] }));
    expect(res.status).toBe(400);
  });

  it('sans token : APPEL 1 (sans coordonnees) → 200 coordonnees_requises', async () => {
    const { POST } = await loadRoute('');
    const res = await POST(makeRequest(validPayload));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ statut: 'coordonnees_requises' });
  });

  it('sans token : APPEL 2 (avec coordonnees) → 201 enregistre', async () => {
    const { POST } = await loadRoute('');
    const res = await POST(
      makeRequest({
        ...validPayload,
        coordonnees: {
          nom_prenom: 'Jean Dupont',
          telephone: '+33 6 12 34 56 78',
          code_postal: '44000',
          adresse: '12 rue des Lilas, Nantes',
        },
      })
    );
    expect(res.status).toBe(201);
    expect((await res.json()).statut).toBe('enregistre');
  });

  it('formulaire guide : APPEL 1 sans reponses → 200 coordonnees_requises', async () => {
    const { POST } = await loadRoute('');
    const res = await POST(
      makeRequest({ email: 'jean@exemple.fr', id_page_hub: 2000, referer: 'https://x.fr/guide' })
    );
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ statut: 'coordonnees_requises' });
  });

  it('formulaire guide : APPEL 2 coordonnees sans adresse → 201 enregistre', async () => {
    const { POST } = await loadRoute('');
    const res = await POST(
      makeRequest({
        email: 'jean@exemple.fr',
        id_page_hub: 2000,
        referer: 'https://x.fr/guide',
        coordonnees: {
          nom_prenom: 'Jean Dupont',
          telephone: '+33 6 12 34 56 78',
          code_postal: '44000',
        },
      })
    );
    expect(res.status).toBe(201);
    expect((await res.json()).statut).toBe('enregistre');
  });

  it('avec token : réponse non-JSON (erreur SQL/HTML) → 502 technique', async () => {
    const { POST } = await loadRoute('test-token');
    globalThis.fetch = vi.fn(async () => ({
      status: 200,
      ok: true,
      text: async () => '<html>Fatal error MySQL</html>',
    })) as unknown as typeof fetch;
    const res = await POST(makeRequest(validPayload));
    expect(res.status).toBe(502);
    expect((await res.json()).erreur).toBe('technique');
  });

  it('avec token : propage le status et le corps de l’API', async () => {
    const fetchMock = vi.fn(async () => ({
      status: 201,
      ok: true,
      text: async () => '{ "statut": "enregistre", "id_demande": 42, "contact_connu": 0 }',
    })) as unknown as typeof fetch;
    globalThis.fetch = fetchMock;
    const { POST } = await loadRoute('test-token');
    const res = await POST(makeRequest(validPayload));
    expect(res.status).toBe(201);
    expect((await res.json()).id_demande).toBe(42);
  });

  it('avec token : tronque le referer à 500 caractères avant envoi (§10)', async () => {
    const calls: RequestInit[] = [];
    globalThis.fetch = vi.fn(async (_url: string, init: RequestInit) => {
      calls.push(init);
      return {
        status: 200,
        ok: true,
        text: async () => '{ "statut": "coordonnees_requises" }',
      };
    }) as unknown as typeof fetch;
    const { POST } = await loadRoute('test-token');
    const longReferer = 'https://x.fr/?q=' + 'a'.repeat(1000);
    await POST(makeRequest({ ...validPayload, referer: longReferer }));
    const sent = JSON.parse(calls[0].body as string);
    expect(sent.referer.length).toBe(500);
  });
});
