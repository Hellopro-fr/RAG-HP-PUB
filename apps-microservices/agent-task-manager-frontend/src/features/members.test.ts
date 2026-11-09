import { describe, expect, it } from 'vitest';

import type { PersonAccess } from '@/lib/api/client';

import { personSources } from './members';
import { matchesFilter } from './projects';
import { matchesUserFilter } from './users';

const person = (p: Partial<PersonAccess>): PersonAccess => ({
  subject: 'ana@example.com',
  name: 'Ana',
  individual_role: null,
  invitation_pending: false,
  via_teams: [],
  effective_role: null,
  source: null,
  agents: [],
  ...p,
});

describe('personSources (members page)', () => {
  it('marks the accepted individual role as winning over the teams', () => {
    expect(
      personSources(
        person({
          individual_role: 'viewer',
          via_teams: [{ name: 'Data', role: 'editor' }],
          effective_role: 'viewer',
          source: 'individual',
        }),
      ),
    ).toBe('Individuel : Lecteur (prioritaire) · via Data : Éditeur (remplacé)');
  });

  it('shows a pending invitation without overriding the team', () => {
    expect(
      personSources(
        person({
          individual_role: 'owner',
          invitation_pending: true,
          via_teams: [{ name: 'Data', role: 'editor' }],
          source: 'team',
        }),
      ),
    ).toBe('Individuel : Propriétaire · Invitation en attente · via Data : Éditeur');
  });

  it('explains admin and public access', () => {
    expect(personSources(person({ source: 'admin' }))).toBe('Niveau Admin');
    expect(personSources(person({ source: 'public' }))).toBe('Projet public (lecture)');
  });
});

describe('filters', () => {
  it('projects: mine = editor or owner, public = visibility', () => {
    expect(matchesFilter({ visibility: 'public', my_role: 'viewer' }, 'member')).toBe(false);
    expect(matchesFilter({ visibility: 'private', my_role: 'editor' }, 'member')).toBe(true);
    expect(matchesFilter({ visibility: 'public', my_role: 'viewer' }, 'public')).toBe(true);
    expect(matchesFilter({ visibility: 'private', my_role: 'owner' }, 'all')).toBe(true);
  });

  it('users: admins, invited, disabled', () => {
    expect(matchesUserFilter({ level: 'admin', status: 'active' }, 'admin')).toBe(true);
    expect(matchesUserFilter({ level: 'classic', status: 'pending' }, 'pending')).toBe(true);
    expect(matchesUserFilter({ level: 'classic', status: 'active' }, 'disabled')).toBe(false);
  });
});
