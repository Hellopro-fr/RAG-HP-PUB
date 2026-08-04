import { describe, it, expect } from 'vitest';
import { existsSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { HUB_PAGES, getHubPage, listHubPages, guideIdPageHub } from '@/data/hub';
import { hubCanonicalPath } from '@/types/hub';
import { resolveHubIcon } from '@/lib/hub/icons';
import { parseHubSlug } from '@/app/hub/[hubSlug]/page';
import type { HubIconName, HubImage, HubPage } from '@/types/hub';

/**
 * Ces tests valident les INVARIANTS du contenu HUB, pas une page en particulier.
 * Ils bouclent sur `listHubPages()` : toute nouvelle page ajoutée au registry est
 * donc contrôlée automatiquement, sans écrire un seul test de plus.
 *
 * C'est le filet qui compte pour ce template : le typecheck garantit la FORME des
 * données, pas leur COHÉRENCE (une ancre de sommaire qui ne pointe sur rien, un
 * href cassé, un id dupliqué passent tous le compilateur).
 */

const pages = listHubPages();

/** Tous les noms d'icônes présents dans une page, tous champs confondus. */
function collectIconNames(page: HubPage): HubIconName[] {
  const names: (HubIconName | undefined)[] = [
    ...page.hero.features.map((f) => f.icon),
    ...page.nav.map((n) => n.icon),
    // `tagIcon` avait été oublié ici : un nom invalide passait le test.
    ...page.thematiques.map((t) => t.tagIcon),
    ...page.valueProps.items.map((i) => i.icon),
    ...page.thematiques.flatMap((t) => t.cards.map((c) => c.icon)),
    ...page.howItWorks.steps.map((s) => s.icon),
    ...page.finalCta.items.map((i) => i.icon),
    ...page.assistant.steps.flatMap((s) => s.illustrations ?? []),
  ];
  return names.filter((n): n is HubIconName => Boolean(n));
}

/**
 * Toutes les images RÉELLEMENT déclarées par une page.
 *
 * Tous les champs `image` sont optionnels : un visuel non livré est absent des
 * données plutôt que remplacé par un chemin inventé. Cette fonction ne collecte
 * donc que les emplacements pourvus — les seuls à contrôler.
 */
function collectImages(page: HubPage): HubImage[] {
  const candidates: (HubImage | undefined)[] = [
    page.hero.background,
    page.accompagnementBanner.image,
    page.guideCta.image,
    page.accompagnement.image,
    page.finalCta.image,
    page.leadPopup.image,
    page.leadPopup.bannerImage,
    page.guideDialog.download.image,
    page.assistant.success.image,
    ...page.thematiques.flatMap((t) => [t.overlay?.image, ...t.cards.map((c) => c.image)]),
    ...page.ressources.items.map((r) => r.image),
    ...page.grandesEtapes.items.map((e) => e.image),
  ];
  return candidates.filter((i): i is HubImage => i !== undefined);
}

/** Toutes les URL d'article déclarées par une page. */
function collectHrefs(page: HubPage): string[] {
  return [
    ...page.thematiques.flatMap((t) => [
      t.overlay?.href,
      ...t.cards.map((c) => c.href),
    ]),
    ...page.ressources.items.map((r) => r.href),
  ].filter((h): h is string => Boolean(h));
}

/** Racine de /public, depuis __tests__/data/hub/. */
const PUBLIC_DIR = resolve(__dirname, '../../../public');

describe('registry HUB', () => {
  it('contient au moins une page', () => {
    expect(pages.length).toBeGreaterThan(0);
  });

  it('la clé du registry est égale à l’id de la page', () => {
    for (const [key, page] of Object.entries(HUB_PAGES)) {
      expect(page.id).toBe(Number(key));
    }
  });

  it('l’id_page_hub du guide (dérivé) est un entier positif distinct de l’id projet', () => {
    // Spec guide §5 : c'est le seul moyen de séparer les leads guide/projet.
    for (const page of pages) {
      const guideId = guideIdPageHub(page.id);
      expect(Number.isInteger(guideId) && guideId > 0, `id_page_hub guide invalide (${guideId})`).toBe(true);
      expect(guideId, `id guide ${guideId} ne doit pas égaler l'id projet ${page.id}`).not.toBe(page.id);
    }
  });

  it('getHubPage résout les ids connus et rejette les inconnus', () => {
    for (const page of pages) {
      expect(getHubPage(page.id)).toBe(page);
    }
    expect(getHubPage(999999)).toBeNull();
    expect(getHubPage(0)).toBeNull();
    expect(getHubPage(-1)).toBeNull();
  });

  it('les ids et les slugs sont uniques', () => {
    expect(new Set(pages.map((p) => p.id)).size).toBe(pages.length);
    expect(new Set(pages.map((p) => p.slug)).size).toBe(pages.length);
  });
});

describe.each(pages.map((page) => [page.slug, page] as const))('page HUB « %s »', (_slug, page) => {
  /* ------------------------------------------------------------------ URL --- */

  it('a un slug en kebab-case, sans id ni suffixe -projet', () => {
    expect(page.slug).toMatch(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);
    expect(page.slug).not.toMatch(/-\d+$/);
    expect(page.slug).not.toMatch(/-projet$/);
  });

  it('fait un aller-retour URL → données sans perte', () => {
    // C'est le contrat qui lie hubCanonicalPath (génération de l'URL), le rewrite
    // next.config.js (retrait de -projet.html) et parseHubSlug (relecture).
    const canonical = hubCanonicalPath(page);
    expect(canonical).toBe(`/${page.slug}-${page.id}-projet.html`);

    // Ce que le rewrite transmet au segment [hubSlug] :
    const hubSlug = canonical.replace(/^\//, '').replace(/-projet\.html$/, '');
    expect(parseHubSlug(hubSlug)).toEqual({ slug: page.slug, id: page.id });
  });

  /* --------------------------------------------------------------- Ancres --- */

  it('n’a pas d’id de bloc thématique dupliqué', () => {
    const ids = page.thematiques.map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('chaque entrée « bloc-* » du sommaire cible un bloc thématique existant', () => {
    const thematiqueIds = new Set(page.thematiques.map((t) => t.id));
    for (const item of page.nav.filter((n) => n.id.startsWith('bloc-'))) {
      expect(thematiqueIds, `sommaire → ${item.id}`).toContain(item.id);
    }
  });

  it('chaque href de « grandes étapes » cible une ancre déclarée', () => {
    const anchors = new Set([
      ...page.thematiques.map((t) => t.id),
      ...page.nav.map((n) => n.id),
    ]);
    for (const step of page.grandesEtapes.items) {
      if (!step.href) continue;
      expect(step.href.startsWith('#'), `href brut: ${step.href}`).toBe(true);
      expect(anchors, `grandes étapes → ${step.href}`).toContain(step.href.slice(1));
    }
  });

  it('le déclencheur du lead popup cible une section existante', () => {
    const anchors = new Set([
      ...page.thematiques.map((t) => t.id),
      ...page.nav.map((n) => n.id),
    ]);
    expect(anchors).toContain(page.leadPopup.triggerSectionId);
  });

  it('n’a pas d’id de sommaire dupliqué', () => {
    const ids = page.nav.map((n) => n.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  /* -------------------------------------------------------------- Icônes --- */

  it('n’utilise que des icônes résolvables', () => {
    const names = collectIconNames(page);
    expect(names.length).toBeGreaterThan(0);
    for (const name of names) {
      expect(resolveHubIcon(name), `icône « ${name} »`).not.toBeNull();
    }
  });

  it('fournit une illustration par option quand des illustrations sont définies', () => {
    for (const step of page.assistant.steps) {
      if (!step.illustrations) continue;
      expect(step.illustrations.length, `étape « ${step.id} »`).toBe(step.options.length);
    }
  });

  /* -------------------------------------------------------------- Images --- */

  it('déclare toutes ses images sous /images/hub/<slug>/ avec un alt non vide', () => {
    const images = collectImages(page);
    expect(images.length).toBeGreaterThan(0);
    for (const image of images) {
      expect(image.src, `src: ${image.src}`).toMatch(new RegExp(`^/images/hub/${page.slug}/`));
      expect(image.alt.trim(), `alt vide pour ${image.src}`).not.toBe('');
    }
  });

  /**
   * Toutes les images sont rendues avec `fill` dans une boîte de taille imposée :
   * déclarer des dimensions n'aurait aucun effet et laisserait croire qu'un ratio
   * est respecté. Le type l'interdit ; ce test protège d'un contournement par `as`.
   */
  it('ne déclare aucune dimension d’image', () => {
    for (const image of collectImages(page)) {
      expect(image, `dimensions inutiles sur ${image.src}`).not.toHaveProperty('width');
      expect(image, `dimensions inutiles sur ${image.src}`).not.toHaveProperty('height');
    }
  });

  /**
   * Le garde-fou qui compte : une image déclarée mais absente du disque produit
   * un visuel cassé en production, invisible au typecheck comme au build (les
   * `src` sont des chaînes, pas des imports). Ce test transforme cet oubli en
   * échec de CI.
   *
   * Corollaire : ne JAMAIS déclarer un chemin pour un visuel non livré. Un
   * emplacement en attente doit rester sans champ `image`.
   */
  it('ne déclare que des images réellement présentes dans /public', () => {
    for (const image of collectImages(page)) {
      const diskPath = resolve(PUBLIC_DIR, image.src.replace(/^\//, ''));
      expect(existsSync(diskPath), `fichier manquant : public${image.src}`).toBe(true);
    }
  });

  /**
   * Le sens INVERSE du test précédent, qui manquait : un fichier livré mais
   * jamais référencé alourdit le dépôt et l'image Docker sans que rien ne le
   * signale. C'est ce qui a laissé 5 vignettes orphelines dans `articles/`.
   */
  it('ne laisse aucune image orpheline dans son dossier', () => {
    const dir = resolve(PUBLIC_DIR, 'images/hub', page.slug);
    if (!existsSync(dir)) return;

    const declared = new Set(collectImages(page).map((i) => i.src));
    const onDisk: string[] = [];
    const walk = (absolute: string, relative: string) => {
      for (const entry of readdirSync(absolute, { withFileTypes: true })) {
        const child = `${relative}/${entry.name}`;
        if (entry.isDirectory()) walk(resolve(absolute, entry.name), child);
        else onDisk.push(child);
      }
    };
    walk(dir, `/images/hub/${page.slug}`);

    const orphans = onDisk.filter((src) => !declared.has(src));
    expect(orphans, `images non référencées : ${orphans.join(', ')}`).toEqual([]);
  });

  /**
   * Les cartes d'un bloc `overlay-*` sont rendues sans image, celles d'un bloc
   * `grid`/`carousel` sans icône (cf. HubInfoCard). Renseigner le champ inutile
   * est silencieux à l'écran — d'où ce contrôle.
   */
  it('n’alimente que les champs de carte utiles au layout du bloc', () => {
    for (const thematique of page.thematiques) {
      const isOverlay = thematique.layout.startsWith('overlay-');
      for (const card of thematique.cards) {
        if (isOverlay) {
          expect(card.image, `image ignorée sur « ${card.title} » (${thematique.layout})`).toBeUndefined();
        } else {
          expect(card.icon, `icône ignorée sur « ${card.title} » (${thematique.layout})`).toBeUndefined();
        }
      }
    }
  });

  /**
   * Les liens vers les pages conseils sont la valeur de maillage interne du HUB.
   * Une URL mal formée est un lien mort invisible au typecheck.
   */
  it('déclare des URL d’article au format conseils HelloPro', () => {
    const hrefs = collectHrefs(page);
    expect(hrefs.length).toBeGreaterThan(0);
    for (const href of hrefs) {
      expect(href, href).toMatch(
        /^https:\/\/conseils\.hellopro\.fr\/[a-z0-9-]+-\d+\.html$/
      );
    }
  });

  it('déclare des extensions d’image servables', () => {
    for (const image of collectImages(page)) {
      expect(image.src, image.src).toMatch(/\.(jpe?g|png|webp|avif|svg)$/i);
    }
  });

  /* ------------------------------------------------------ Fil d'ariane --- */

  it('a un fil d’ariane exploitable par GtmFooterScripts et le JSON-LD', () => {
    // GtmFooterScripts fait slice(1, -1) : il faut donc au moins un maillon de
    // catégorie entre « Accueil » et le titre de la page.
    expect(page.breadcrumb.length).toBeGreaterThanOrEqual(3);
    expect(page.breadcrumb[0].href).toBeTruthy();
    // Le dernier maillon est la page courante : pas de href (le JSON-LD lui
    // injecte l'URL canonique).
    expect(page.breadcrumb[page.breadcrumb.length - 1].href).toBeUndefined();
    for (const item of page.breadcrumb) {
      expect(item.label.trim()).not.toBe('');
    }
  });

  /* ------------------------------------------------------------- Contenu --- */

  it('a des métadonnées et un h1 non vides', () => {
    expect(page.meta.title.trim()).not.toBe('');
    expect(page.meta.description.trim()).not.toBe('');
    expect(page.hero.titleParts.length).toBeGreaterThan(0);
    expect(page.hero.titleParts.map((p) => p.text).join('').trim()).not.toBe('');
  });

  it('a une FAQ sans question ni réponse vide', () => {
    expect(page.faq.items.length).toBeGreaterThan(0);
    for (const item of page.faq.items) {
      expect(item.q.trim()).not.toBe('');
      expect(item.a.trim()).not.toBe('');
    }
  });

  it('n’a pas de bloc thématique sans carte', () => {
    for (const thematique of page.thematiques) {
      expect(thematique.cards.length, `bloc « ${thematique.id} »`).toBeGreaterThan(0);
    }
  });

  it('n’expose jamais description et descriptionHtml sur la même carte', () => {
    // Les deux champs sont rendus différemment (texte brut vs HTML sanitisé) :
    // les cumuler produirait un doublon silencieux.
    for (const thematique of page.thematiques) {
      for (const card of thematique.cards) {
        expect(
          Boolean(card.description) && Boolean(card.descriptionHtml),
          `carte « ${card.title} »`
        ).toBe(false);
      }
    }
  });

  it('déclare un overlay pour les layouts overlay-*, et aucun sinon', () => {
    for (const thematique of page.thematiques) {
      const needsOverlay = thematique.layout.startsWith('overlay-');
      expect(Boolean(thematique.overlay), `bloc « ${thematique.id} »`).toBe(needsOverlay);
    }
  });
});
