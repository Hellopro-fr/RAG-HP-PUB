import { NextRequest, NextResponse } from 'next/server';

const HP_BASE = 'https://www.hellopro.fr';
const HP_ANNUAIRE = 'https://www.hellopro.fr'; // serveur_annuaire côté legacy

/**
 * Proxy vers ajax_recupere_lien.php
 *
 * POST /api/resolve-link
 * Body JSON (catégorie) : { id_rubrique: string; type: string }
 * Body JSON (produit)   : { id_rubrique: string; id_produit: string; nom_produit: string }
 *
 * Retourne : { url: string } — URL absolue vers laquelle naviguer
 *
 * Logique calquée sur la fonction JS legacy completer_moteur() :
 *   - Catégorie type "fa"     → URL retournée telle quelle
 *   - Catégorie autre type    → HP_ANNUAIRE + "/" + URL retournée
 *   - Produit (id_produit)    → HP_ANNUAIRE + "/" + URL retournée
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as {
      id_rubrique: string;
      type?: string;
      id_produit?: string;
      nom_produit?: string;
    };

    const { id_rubrique, type, id_produit, nom_produit } = body;

    if (!id_rubrique) {
      return NextResponse.json({ url: HP_BASE }, { status: 400 });
    }

    /* Construire le body form-urlencoded */
    let formData: string;
    const isProduct = Boolean(id_produit);

    if (isProduct) {
      formData = [
        `id_rubrique=${encodeURIComponent(id_rubrique)}`,
        `id_produit=${encodeURIComponent(id_produit!)}`,
        `nom_produit=${encodeURIComponent(nom_produit ?? '')}`,
      ].join('&');
    } else {
      formData = [
        `id_rubrique=${encodeURIComponent(id_rubrique)}`,
        `type=${encodeURIComponent(type ?? '')}`,
      ].join('&');
    }

    const res = await fetch(
      `${HP_BASE}/hellopro_fr/ajax/ajax_recupere_lien.php`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'User-Agent': 'Mozilla/5.0 (compatible; HelloPro-Conseils/1.0)',
        },
        body: formData,
      }
    );

    if (!res.ok) {
      return NextResponse.json({ url: HP_BASE }, { status: res.status });
    }

    const raw = (await res.text()).trim();

    /* Appliquer la même logique que le JS legacy */
    let url: string;
    if (isProduct) {
      // produit → serveur_annuaire + "/" + raw
      url = raw.startsWith('http') ? raw : `${HP_ANNUAIRE}/${raw}`;
    } else if (type === 'fa') {
      // catégorie type "fa" → URL directe
      url = raw.startsWith('http') ? raw : `${HP_ANNUAIRE}/${raw}`;
    } else {
      // autre type catégorie → serveur_annuaire + "/" + raw
      url = raw.startsWith('http') ? raw : `${HP_ANNUAIRE}/${raw}`;
    }

    return NextResponse.json({ url });
  } catch (err) {
    console.error('[/api/resolve-link] error:', err);
    return NextResponse.json({ url: HP_BASE }, { status: 500 });
  }
}
