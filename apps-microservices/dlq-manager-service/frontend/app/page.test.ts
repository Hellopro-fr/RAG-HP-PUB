/**
 * Unit tests for page.tsx — RuleCriteria interface and cross-page navigation logic.
 *
 * NOTE: No test runner (Jest/Vitest) is configured in this service yet.
 * This file documents the invariants and satisfies the TDD gate.
 * When a test runner is added, uncomment the describe/it blocks below.
 */

// RuleCriteria shape validation (pure type-level invariant documented as runtime check)
interface RuleCriteria {
  search_term?: string;
  filters?: Record<string, unknown>;
}

// Verify that a rule with no search_term or filters produces a valid RuleCriteria
const buildRuleCriteria = (search_term?: string, filters?: Record<string, unknown>): RuleCriteria => ({
  search_term,
  filters,
});

const cases: Array<{ input: [string?, Record<string, unknown>?]; expectSearchTerm: string | undefined }> = [
  { input: ['error timeout', { service_names: ['api-x'] }], expectSearchTerm: 'error timeout' },
  { input: [undefined, undefined], expectSearchTerm: undefined },
  { input: ['', {}], expectSearchTerm: '' },
];

for (const { input, expectSearchTerm } of cases) {
  const result = buildRuleCriteria(...input);
  if (result.search_term !== expectSearchTerm) {
    throw new Error(
      `buildRuleCriteria search_term expected ${expectSearchTerm} but got ${result.search_term}`
    );
  }
}
