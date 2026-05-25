import { defineConfig, devices } from '@playwright/test'
import { resolve } from 'node:path'

const REPO_ROOT = resolve(__dirname, '..', '..', '..')
const BACKEND_DIR = resolve(REPO_ROOT, 'apps', 'backend')
const CLIENT_DIR = resolve(REPO_ROOT, 'apps', 'web', 'client')

const IS_CI = !!process.env['CI']

export default defineConfig({
  testDir: './specs',
  fullyParallel: false,
  workers: 1,
  retries: IS_CI ? 2 : 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: IS_CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  globalSetup: './global-setup.ts',
  globalTeardown: './global-teardown.ts',
  webServer: [
    {
      name: 'backend',
      // The Makefile's dev.backend recipe sources .env first; we mirror it
      // in shell so FH6_DB_DSN etc. flow through.
      command: 'bash -c "set -a && [ -f .env ] && . ./.env; set +a; uv run python -m fh6.main"',
      cwd: BACKEND_DIR,
      url: 'http://127.0.0.1:8000/healthz',
      reuseExistingServer: !IS_CI,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      name: 'web',
      command: 'pnpm exec vite --host 127.0.0.1 --port 5173 --strictPort',
      cwd: CLIENT_DIR,
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !IS_CI,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
  ],
})
