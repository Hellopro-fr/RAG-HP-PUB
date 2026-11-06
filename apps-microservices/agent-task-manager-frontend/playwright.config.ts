import { defineConfig, devices } from '@playwright/test';

// The e2e suite runs against the full compose stack (Caddy on :8620 by default):
//   cd ../agent-task-manager-backend && docker compose up -d --build && cd - && npx playwright test
export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8620',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
