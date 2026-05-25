import { test, expect } from '@playwright/test'

// Smoke: the sessions list page renders and talks to the backend.
// If the UDP pump has driven the backend to create a session,
// also click Load on the first row and verify the detail endpoint
// returns 200. Otherwise just assert the list endpoint round-trips.
test('session detail loads', async ({ page }) => {
  const listResponse = page.waitForResponse(
    (r) => /\/api\/sessions(\?|$)/.test(r.url()) && r.request().method() === 'GET',
  )
  await page.goto('/sessions')

  const listed = await listResponse
  expect(listed.status()).toBe(200)

  await expect(page.getByText('Sessions', { exact: true }).first()).toBeVisible()

  const firstLoadButton = page.getByRole('button', { name: 'Load' }).first()
  const hasSession = await firstLoadButton.isVisible({ timeout: 15_000 }).catch(() => false)

  if (hasSession) {
    const detailResponse = page.waitForResponse(
      (r) => /\/api\/sessions\/[^/?]+(\?|$)/.test(r.url()) && r.request().method() === 'GET',
    )
    await firstLoadButton.click()
    const detail = await detailResponse
    expect(detail.status()).toBe(200)
  }
})
