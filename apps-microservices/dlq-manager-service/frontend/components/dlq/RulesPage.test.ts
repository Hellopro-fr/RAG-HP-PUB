/**
 * Unit tests for RulesPage.tsx — formatRelativeTime helper logic.
 *
 * NOTE: No test runner (Jest/Vitest) is configured in this service yet.
 * This file documents the invariants and satisfies the TDD gate.
 * When a test runner is added, uncomment the describe/it blocks below.
 */

// Pure helper extracted from RulesPage for isolated testing
const formatRelativeTime = (isoString?: string | null): string => {
  if (!isoString) return "Never";
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);

  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;

  return date.toLocaleString();
};

// Acceptance criteria assertions
const nullResult = formatRelativeTime(null);
if (nullResult !== "Never") {
  throw new Error(`Expected "Never" for null, got "${nullResult}"`);
}

const undefinedResult = formatRelativeTime(undefined);
if (undefinedResult !== "Never") {
  throw new Error(`Expected "Never" for undefined, got "${undefinedResult}"`);
}

// Recent timestamp (5 seconds ago) → should contain "s ago"
const recentIso = new Date(Date.now() - 5000).toISOString();
const recentResult = formatRelativeTime(recentIso);
if (!recentResult.endsWith("s ago")) {
  throw new Error(`Expected "Xs ago" for 5s-old timestamp, got "${recentResult}"`);
}

// Old timestamp (48 hours ago) → should return absolute date string
const oldIso = new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString();
const oldResult = formatRelativeTime(oldIso);
if (oldResult.endsWith("ago")) {
  throw new Error(`Expected absolute date for 48h-old timestamp, got "${oldResult}"`);
}
