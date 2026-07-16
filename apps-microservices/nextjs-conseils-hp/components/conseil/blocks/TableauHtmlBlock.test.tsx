import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { TableauHtmlBlock } from './TableauHtmlBlock';

const DATA = { headers: ['Type', 'Prix'], rows: [['Standard', '200 €'], ['Premium', '500 €']] };

describe('TableauHtmlBlock', () => {
  it('rend le tableau', () => {
    const { container } = render(<TableauHtmlBlock data={DATA} />);
    expect(container.querySelector('table')).toBeTruthy();
  });

  it('rend les en-têtes depuis headers', () => {
    const { container } = render(<TableauHtmlBlock data={DATA} />);
    expect(container.querySelectorAll('th')).toHaveLength(2);
    expect(container.querySelector('th')?.textContent).toBe('Type');
  });

  it('rend les lignes depuis rows', () => {
    const { container } = render(<TableauHtmlBlock data={DATA} />);
    expect(container.querySelectorAll('tr')).toHaveLength(3); // 1 header + 2 data
    expect(container.querySelector('td')?.textContent).toBe('Standard');
  });

  it('retourne null si headers et rows sont vides', () => {
    const { container } = render(<TableauHtmlBlock data={{ headers: [], rows: [] }} />);
    expect(container.firstChild).toBeNull();
  });
});
