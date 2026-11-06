// Phase 1 deliverables: board, task detail, questions inbox, agents page render live data, and a
// human can answer a blocking question inline.
import { expect, test } from '@playwright/test';

import { adminContext, agentCall, fixture } from './helpers';

test('board, task detail, questions inbox and agents page', async ({ browser }) => {
  const ctx = await adminContext(browser);
  const f = await fixture(ctx.request, ['Parser', 'Écrire']);
  const claim = await agentCall<{ task_id: string; lease_token: string }>(
    ctx.request,
    f.agent.token,
    `/api/projects/${f.project}/claim`,
    { role: 'implementer' },
  );
  await agentCall(ctx.request, f.agent.token, `/api/tasks/${claim.task_id}/report`, {
    lease_token: claim.lease_token,
    kind: 'progress',
    body: 'Analyse terminée',
  });
  const page = await ctx.newPage();

  // Board: one column per state, the claimed task with its holder.
  await page.goto(`/projects/${f.project}`);
  await expect(page.getByTestId('column-ready')).toBeVisible();
  await expect(page.getByTestId('column-cancelled')).toBeVisible();
  await expect(page.locator(`[data-testid="column-working"] [data-task-id="${claim.task_id}"]`)).toContainText(
    f.agent.name,
  );
  await expect(page.getByTestId('lease-countdown').first()).toContainText('bail');

  // Agents page: presence with the current task.
  await page.goto('/agents');
  const row = page.locator(`[data-testid="agent-row"][data-actor="${f.agent.name}"]`);
  await expect(row).toContainText('Parser');

  // The agent asks a blocking question.
  const ask = await agentCall<{ question_id: string }>(ctx.request, f.agent.token, `/api/tasks/${claim.task_id}/ask`, {
    lease_token: claim.lease_token,
    question: 'Quel séparateur utiliser ?',
    blocking: true,
    handoff_note: 'Parsing fait, reste l’écriture',
  });
  expect(ask.question_id).toBeTruthy();

  // Task detail: spec criterion, timeline with the report and the question, attempts.
  await page.goto(`/tasks/${claim.task_id}`);
  await expect(page.getByTestId('task-state')).toHaveText('En attente de réponse');
  await expect(page.getByTestId('criteria')).toContainText('Le critère e2e');
  await expect(page.getByTestId('timeline')).toContainText('Analyse terminée');
  await expect(page.getByTestId('timeline')).toContainText('Quel séparateur utiliser ?');

  // Questions inbox: answer inline; the question leaves the inbox and the task becomes ready.
  await page.goto('/questions');
  const card = page.getByTestId('question').filter({ hasText: 'Quel séparateur utiliser ?' });
  await expect(card).toContainText('Bloquante');
  await card.getByLabel('Répondre').fill('Point-virgule');
  await card.getByRole('button', { name: 'Répondre' }).click();
  await expect(card).toHaveCount(0);
  await page.goto(`/tasks/${claim.task_id}`);
  await expect(page.getByTestId('task-state')).toHaveText('Prête');
});
