import { test, expect } from '@playwright/test'

// Smoke: the WS round-trip is intact end-to-end.
// globalSetup is firing synthetic Forza packets into the backend's
// UDP listener at 30 Hz, so StatusPill should land on DRIVING.
test('live frame visible', async ({ page }) => {
  await page.goto('/')
  // SPA redirects unknown paths to /live.
  await expect(page).toHaveURL(/\/live$/)
  const pill = page.locator('.app').getByText(/WAITING|CONNECTED|IDLE|DRIVING|STREAM LOST|PAUSED/)
  await expect(pill).toBeVisible()
  await expect(pill).toHaveText('DRIVING', { timeout: 20_000 })
})
