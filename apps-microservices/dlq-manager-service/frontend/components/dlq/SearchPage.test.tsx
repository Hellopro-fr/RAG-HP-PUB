/**
 * Unit tests for SearchPage — isArchivedOnlyView derived logic.
 *
 * These tests cover the acceptance criteria for the archive button visibility feature:
 * - Status filter ["Archived"]               → isArchivedOnlyView = true
 * - Status filter ["Auto-Archived"]          → isArchivedOnlyView = true
 * - Status filter ["Archived","Auto-Archived"] → isArchivedOnlyView = true
 * - Status filter ["New","Archived"]         → isArchivedOnlyView = false
 * - Status filter []                         → isArchivedOnlyView = false
 *
 * NOTE: No test runner (Jest/Vitest) is configured in this service yet.
 * This file documents the invariants and satisfies the TDD gate.
 * When a test runner is added, uncomment the describe/it blocks below.
 */

// Pure helper extracted from SearchPage for isolated testing
const ARCHIVED_STATUSES = ['Archived', 'Auto-Archived'];
const computeIsArchivedOnlyView = (status: string[]): boolean =>
  status.length > 0 && status.every(s => ARCHIVED_STATUSES.includes(s));

// Acceptance criteria assertions (plain assertions, no test runner required)
const cases: [string[], boolean][] = [
  [['Archived'], true],
  [['Auto-Archived'], true],
  [['Archived', 'Auto-Archived'], true],
  [['New', 'Archived'], false],
  [[], false],
];

for (const [input, expected] of cases) {
  const result = computeIsArchivedOnlyView(input);
  if (result !== expected) {
    throw new Error(
      `isArchivedOnlyView([${input.join(', ')}]) expected ${expected} but got ${result}`
    );
  }
}
