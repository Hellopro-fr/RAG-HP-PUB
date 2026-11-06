// AC-1.7 (browser half) WHEN a state change commits THE SYSTEM SHALL show it on every open board
// within 1 s. Two independent browser contexts watch the same board; an agent claims a task
// through the API; both boards must move the card to "En cours" within 1 s of the commit.
import { expect, test } from '@playwright/test';

import { adminContext, agentCall, fixture } from './helpers';

test('a committed state change appears on two open boards within 1 s', async ({ browser }) => {
  const setup = await adminContext(browser);
  const f = await fixture(setup.request, ['Tâche observée']);
  const task = f.tasks[0]!;

  const boards = [];
  for (let i = 0; i < 2; i++) {
    const ctx = await adminContext(browser);
    const page = await ctx.newPage();
    await page.goto(`/projects/${f.project}`);
    await expect(page.getByTestId('stream-status')).toHaveAttribute('data-status', 'live');
    await expect(page.locator(`[data-testid="column-ready"] [data-task-id="${task}"]`)).toBeVisible();
    boards.push(page);
  }

  await agentCall(setup.request, f.agent.token, `/api/projects/${f.project}/claim`, { role: 'implementer' });
  const committedAt = Date.now();
  for (const page of boards) {
    const remaining = Math.max(1, 1000 - (Date.now() - committedAt));
    await expect(page.locator(`[data-testid="column-working"] [data-task-id="${task}"]`)).toBeVisible({
      timeout: remaining,
    });
  }
  const elapsed = Date.now() - committedAt;
  expect(elapsed, `both boards updated in ${elapsed} ms`).toBeLessThan(1000);
  // The holder and its lease countdown are shown on the card.
  await expect(boards[0]!.locator(`[data-task-id="${task}"] [data-testid="task-holder"]`)).toContainText(f.agent.name);
});

test('a board reconnects and catches up on missed events', async ({ browser }) => {
  const setup = await adminContext(browser);
  const f = await fixture(setup.request, ['Avant', 'Pendant la coupure']);
  const ctx = await adminContext(browser);
  const page = await ctx.newPage();
  await page.goto(`/projects/${f.project}`);
  await expect(page.getByTestId('stream-status')).toHaveAttribute('data-status', 'live');
  // Go offline, let an event happen, come back: the board must show it.
  await ctx.setOffline(true);
  await agentCall(setup.request, f.agent.token, `/api/projects/${f.project}/claim`, { role: 'implementer' });
  await ctx.setOffline(false);
  await expect(page.locator('[data-testid="column-working"] [data-testid="task-card"]')).toHaveCount(1, {
    timeout: 15_000,
  });
});
