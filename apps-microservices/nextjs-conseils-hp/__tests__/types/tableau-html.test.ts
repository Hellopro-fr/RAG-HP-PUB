import { describe, it, expect } from 'vitest';
import type { TableauHtmlBlockData } from '@/types/blocks/tableau-html';

describe('TableauHtmlBlockData', () => {
  it('accepte un tableau avec en-têtes et lignes', () => {
    const data: TableauHtmlBlockData = {
      headers: ['Type', 'Prix'],
      rows: [['Standard', '200 €'], ['Premium', '500 €']],
    };
    expect(data.headers).toHaveLength(2);
    expect(data.rows).toHaveLength(2);
  });

  it('accepte un tableau vide', () => {
    const data: TableauHtmlBlockData = { headers: [], rows: [] };
    expect(data.rows).toHaveLength(0);
  });
});
