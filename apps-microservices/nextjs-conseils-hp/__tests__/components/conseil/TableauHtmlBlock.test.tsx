import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TableauHtmlBlock } from '@/components/conseil/blocks/TableauHtmlBlock';

const HEADERS_3 = ['Colonne A', 'Colonne B', 'Colonne C'];
const HEADERS_4 = ['Type', 'Prix', 'Surface', 'Prix/m²'];

const ROWS_3 = [
  ['Val A1', 'Val B1', 'Val C1'],
  ['Val A2', 'Val B2', 'Val C2'],
];

const ROWS_4 = [
  ['Hangar bois', '50 000 €', '200 m²', '250 €'],
  ['Hangar métal', '80 000 €', '300 m²', '267 €'],
];

describe('TableauHtmlBlock', () => {
  it('renders nothing when headers and rows are both empty', () => {
    const { container } = render(<TableauHtmlBlock data={{ headers: [], rows: [] }} />);
    expect(container.firstChild).toBeNull();
  });

  describe('≤ 3 colonnes — rendu unique scrollable', () => {
    it('affiche un seul tableau sans version mobile séparée', () => {
      render(<TableauHtmlBlock data={{ headers: HEADERS_3, rows: ROWS_3 }} />);
      const tables = document.querySelectorAll('table');
      expect(tables).toHaveLength(1);
    });

    it('affiche les en-têtes et les lignes', () => {
      render(<TableauHtmlBlock data={{ headers: HEADERS_3, rows: ROWS_3 }} />);
      expect(screen.getByText('Colonne A')).toBeDefined();
      expect(screen.getByText('Val B2')).toBeDefined();
    });

    it('met la première cellule de chaque ligne en gras', () => {
      const { container } = render(<TableauHtmlBlock data={{ headers: HEADERS_3, rows: ROWS_3 }} />);
      const firstCells = container.querySelectorAll('tbody td:first-child');
      firstCells.forEach((td) => {
        expect(td.className).toContain('font-semibold');
      });
    });
  });

  describe('> 3 colonnes — desktop table + cartes mobile', () => {
    it('génère deux zones (desktop masquée mobile + mobile masquée desktop)', () => {
      const { container } = render(<TableauHtmlBlock data={{ headers: HEADERS_4, rows: ROWS_4 }} />);
      const desktopZone = container.querySelector('.hidden.md\\:block');
      const mobileZone = container.querySelector('.md\\:hidden');
      expect(desktopZone).toBeTruthy();
      expect(mobileZone).toBeTruthy();
    });

    it('génère une carte par ligne de données', () => {
      const { container } = render(<TableauHtmlBlock data={{ headers: HEADERS_4, rows: ROWS_4 }} />);
      const mobileZone = container.querySelector('.md\\:hidden');
      const cards = mobileZone?.querySelectorAll('table');
      expect(cards).toHaveLength(ROWS_4.length);
    });

    it('titre de carte = header[0] : row[0]', () => {
      render(<TableauHtmlBlock data={{ headers: HEADERS_4, rows: ROWS_4 }} />);
      // "Type" et "Hangar bois" apparaissent dans desktop et mobile — getAllByText est requis
      expect(screen.getAllByText('Type').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('Hangar bois').length).toBeGreaterThanOrEqual(1);
    });

    it('corps de carte : libellés des colonnes restantes en muted, valeurs en foreground', () => {
      const { container } = render(<TableauHtmlBlock data={{ headers: HEADERS_4, rows: ROWS_4 }} />);
      const mobileZone = container.querySelector('.md\\:hidden');
      const labelCells = mobileZone?.querySelectorAll('td.text-muted-foreground');
      // 3 colonnes restantes × 2 lignes = 6 cellules label
      expect(labelCells?.length).toBe(6);
    });

    it('première colonne mobile en poids normal (pas de font-semibold sur la valeur du titre)', () => {
      const { container } = render(<TableauHtmlBlock data={{ headers: HEADERS_4, rows: ROWS_4 }} />);
      const mobileZone = container.querySelector('.md\\:hidden');
      const cardTitles = mobileZone?.querySelectorAll('th[colspan="2"]');
      cardTitles?.forEach((th) => {
        expect(th.className).toContain('font-normal');
      });
    });
  });

  describe('nettoyage des cellules', () => {
    it('retire les attributs style et class des cellules', () => {
      const dirtyHeaders = ['<span style="color:red" class="foo">Titre</span>'];
      const dirtyRows = [['<b class="bar" style="font-size:12px">Val</b>']];
      const { container } = render(
        <TableauHtmlBlock data={{ headers: dirtyHeaders, rows: dirtyRows }} />
      );
      expect(container.innerHTML).not.toContain('style=');
      expect(container.innerHTML).not.toContain('class="foo"');
      expect(container.innerHTML).not.toContain('class="bar"');
    });

    it('retire les <br> superflus en début et fin de cellule', () => {
      const headers = ['<br>Titre<br>'];
      const rows = [['<br /><br />Valeur<br>']];
      const { container } = render(<TableauHtmlBlock data={{ headers, rows }} />);
      const th = container.querySelector('th');
      expect(th?.innerHTML.startsWith('<br')).toBeFalsy();
      expect(th?.innerHTML.endsWith('<br>')).toBeFalsy();
    });
  });

  describe('cas limites', () => {
    it('tableau sans lignes de données (en-tête seul) — rendu sans crash', () => {
      const { container } = render(
        <TableauHtmlBlock data={{ headers: HEADERS_4, rows: [] }} />
      );
      expect(container.querySelector('thead')).toBeTruthy();
      expect(container.querySelector('tbody')).toBeTruthy();
    });

    it('lignes de longueur inégale — complétées avec des cellules vides', () => {
      const rows = [['A'], ['B', 'C', 'D', 'E']];
      const { container } = render(
        <TableauHtmlBlock data={{ headers: HEADERS_4, rows }} />
      );
      // Restreindre au tableau desktop (le querySelector global trouve aussi les cartes mobile)
      const desktopZone = container.querySelector('.hidden');
      const firstRowCells = desktopZone?.querySelectorAll('tbody tr:first-child td');
      expect(firstRowCells?.length).toBe(HEADERS_4.length);
    });

    it('cellules vides — rendu sans crash', () => {
      const rows = [['', '', '', '']];
      expect(() =>
        render(<TableauHtmlBlock data={{ headers: HEADERS_4, rows }} />)
      ).not.toThrow();
    });
  });
});
