export type SelectionVersion = 'originale' | 'B';

export function parseSelectionVersion(raw: string | null | undefined): SelectionVersion {
  return raw === 'B' ? 'B' : 'originale';
}
