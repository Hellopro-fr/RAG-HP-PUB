import { describe, expect, it } from 'vitest';

import { sourceText } from './access';

describe('sourceText (why an access is allowed or refused)', () => {
  it('explains an individual setting that overrides the teams', () => {
    expect(
      sourceText({ kind: 'individual', teams_outcome: 'allowed', teams: ['Catalogue'] }),
    ).toBe('Individuel, prioritaire (l’équipe donnerait : autorisé)');
    expect(sourceText({ kind: 'individual', teams_outcome: 'unset', teams: [] })).toBe(
      'Individuel, prioritaire',
    );
  });

  it('names the deciding teams', () => {
    expect(
      sourceText({ kind: 'teams', teams_outcome: 'allowed', teams: ['Catalogue', 'Data'] }),
    ).toBe('via Catalogue, Data');
    expect(sourceText({ kind: 'teams', teams_outcome: 'denied', teams: ['Prix'] })).toBe(
      'refusé par Prix',
    );
  });

  it('covers admin and default', () => {
    expect(sourceText({ kind: 'admin_level', teams: [] })).toBe('Niveau Admin');
    expect(sourceText({ kind: 'admin_only', teams: [] })).toBe('Réservé aux Admins');
    expect(sourceText({ kind: 'default', teams: [] })).toBe('Aucun réglage');
  });
});
