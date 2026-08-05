import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

/**
 * Garde-fou de l'échelle typographique du HUB.
 *
 * Le problème que ce test empêche de revenir : les tailles de texte étaient
 * dispersées dans 12 composants, et chaque nouveau bloc en réintroduisait une.
 * Sur la page 1000 on comptait 3 échelles de titre de section et 4 de titre de
 * carte pour 6 niveaux réels — en scrollant, l'œil lisait un changement de police
 * à chaque bloc.
 *
 * On ne teste pas « la page est jolie », c'est invérifiable ici. On teste la seule
 * propriété mécanique qui produit le défaut : une classe de TAILLE écrite en dur
 * sur un titre, au lieu d'une constante de `typography.ts`. Un `text-2xl` littéral
 * sur un `h2` fait échouer ce test — la constante correspondante, non.
 *
 * Portée volontairement limitée aux TITRES (`h1`..`h4`) : ce sont eux qui donnent
 * le rythme vertical de la page, et c'est sur eux que l'écart était visible. Les
 * micro-libellés (`text-[9px]` de la pastille ronde de LeadPopup, par exemple)
 * restent libres — les tokeniser tous produirait un fichier de constantes à
 * usage unique, sans rien empêcher.
 */

// `__dirname` et non `process.cwd()` : même convention que registry.test.ts, et
// insensible au répertoire depuis lequel vitest est lancé.
const HUB_DIR = resolve(__dirname, '../../../components/hub');

/**
 * Fichiers hors périmètre, chacun pour une raison :
 *  - `typography.ts` : c'est LA source des valeurs, elle les contient par nature ;
 *  - `AssistantForm.tsx` : questionnaire du hero, laissé tel quel sur demande
 *    explicite. Si un jour il rejoint l'échelle, retirer cette ligne — le test
 *    dira aussitôt ce qu'il reste à convertir.
 */
const EXEMPT = new Set(['typography.ts', 'AssistantForm.tsx']);

/** `text-lg`, `text-2xl`, `text-[17px]`… — toute classe de taille de police. */
const FONT_SIZE_CLASS =
  /(?:^|[\s:'"`])(?:(?:sm|md|lg|xl|2xl):)?text-(?:xs|sm|base|lg|[2-9]?xl|\[[^\]]*(?:px|rem|em)\])(?=$|[\s'"`])/;

/** Ouverture de balise titre avec son attribut `className`, sur une ou plusieurs lignes. */
const HEADING_TAG = /<(h[1-4])\b[^>]*className=(?:"([^"]*)"|\{`([^`]*)`\})/gs;

function hubFiles(): string[] {
  return readdirSync(HUB_DIR)
    .filter((name) => name.endsWith('.tsx') || name.endsWith('.ts'))
    .filter((name) => !EXEMPT.has(name));
}

describe('échelle typographique HUB', () => {
  it('trouve bien les composants à contrôler (le test ne passe pas à vide)', () => {
    // Sans cette assertion, un chemin cassé ferait passer tous les tests suivants
    // sur une liste vide — vert, et sans rien vérifier.
    expect(hubFiles().length).toBeGreaterThan(8);
  });

  it('aucun titre ne déclare sa taille en dur — tous passent par typography.ts', () => {
    const offenders: string[] = [];

    for (const file of hubFiles()) {
      const source = readFileSync(join(HUB_DIR, file), 'utf8');
      for (const match of source.matchAll(HEADING_TAG)) {
        const [, tag, quoted, templated] = match;
        const classes = quoted ?? templated ?? '';
        if (FONT_SIZE_CLASS.test(classes)) {
          offenders.push(`${file} <${tag}> : ${classes.trim()}`);
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  it('chaque composant qui rend un titre importe l’échelle', () => {
    const offenders: string[] = [];

    for (const file of hubFiles()) {
      const source = readFileSync(join(HUB_DIR, file), 'utf8');
      if (!/<h[1-4]\b/.test(source)) continue;
      if (!/from '\.\/typography'/.test(source)) offenders.push(file);
    }

    expect(offenders).toEqual([]);
  });

  it('la valeur arbitraire text-[17px] a bien disparu du template', () => {
    // Elle était unique dans tout le service : un pixel de plus que `text-base`,
    // invisible seule, nette à côté d'une carte voisine en `text-lg`.
    // `typography.ts` est exclu par `hubFiles()` — il la CITE dans le commentaire
    // qui explique pourquoi elle a été retirée, ce qui est le comportement voulu.
    for (const file of hubFiles()) {
      expect(readFileSync(join(HUB_DIR, file), 'utf8')).not.toContain('text-[17px]');
    }
  });
});
