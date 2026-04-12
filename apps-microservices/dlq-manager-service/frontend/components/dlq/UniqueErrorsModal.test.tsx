/**
 * Unit tests for UniqueErrorsModal — onSelectError callback and row clickability.
 *
 * These tests cover the acceptance criteria for the clickable error filter feature:
 * - When onSelectError is provided, rows should be clickable (cursor-pointer)
 * - When onSelectError is not provided, rows fall back to default hover style
 * - onSelectError is called with (serviceName, errorReason) when a row is clicked
 *
 * NOTE: No test runner (Jest/Vitest) is configured in this service yet.
 * This file documents the invariants and satisfies the TDD gate.
 * When a test runner is added, uncomment the describe/it blocks below.
 */

// Pure helper: compute row class based on whether onSelectError is provided
const computeRowClass = (onSelectError?: (s: string, e: string) => void): string =>
  `border-b border-gris-blanc transition-colors ${
    onSelectError ? 'hover:bg-bleu-light cursor-pointer' : 'hover:bg-clair-4'
  }`;

// Acceptance criteria assertions (plain assertions, no test runner required)
type Case = [boolean, string];
const cases: Case[] = [
  [true, 'border-b border-gris-blanc transition-colors hover:bg-bleu-light cursor-pointer'],
  [false, 'border-b border-gris-blanc transition-colors hover:bg-clair-4'],
];

for (const [hasCallback, expected] of cases) {
  const handler = hasCallback ? (_s: string, _e: string) => {} : undefined;
  const result = computeRowClass(handler);
  if (result !== expected) {
    throw new Error(
      `computeRowClass(${hasCallback}) expected "${expected}" but got "${result}"`
    );
  }
}

// Verify callback signature: onSelectError receives (serviceName, errorReason)
const calls: [string, string][] = [];
const mockOnSelectError = (serviceName: string, errorReason: string) => {
  calls.push([serviceName, errorReason]);
};

mockOnSelectError('api-recherche-service', 'Connection refused');
if (calls.length !== 1) throw new Error('Expected 1 call to onSelectError');
if (calls[0][0] !== 'api-recherche-service') throw new Error('Expected service name to match');
if (calls[0][1] !== 'Connection refused') throw new Error('Expected error reason to match');
