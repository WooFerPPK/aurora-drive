import { test, expect } from '@playwright/test'

// Smoke: toggle a model, save, reload, assert the new state persisted.
// We use "Tire wear model" (under the Models section) since it's a
// plain boolean and not load-bearing for other tests. Restore the
// original state at the end so re-runs are idempotent.
const TOGGLE_LABEL = 'Tire wear model'

test('settings round-trip', async ({ page }) => {
  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: 'Models' })).toBeVisible()

  // The native <input type="checkbox"> is visually-hidden by design
  // (width: 0; height: 0). The visible control is the wrapping
  // <label>, and clicking it natively toggles the associated input.
  const toggleLabel = page.locator('label.settings-toggle', { hasText: TOGGLE_LABEL })
  await expect(toggleLabel).toBeVisible()
  const checkbox = page.getByLabel(TOGGLE_LABEL)
  const initial = await checkbox.isChecked()
  const target = !initial

  await toggleLabel.click()
  await expect(checkbox).toBeChecked({ checked: target })

  // The Save button cycles label Save changes -> Saving… -> Saved
  // on the same element. Scope to the savebar to avoid matching
  // "Saved cars" in the sidebar nav. The savebar status text
  // ("All changes saved") is the cleanest post-save signal.
  const savebar = page.locator('.settings-savebar-actions')
  await savebar.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText('All changes saved')).toBeVisible()

  await page.reload()
  await expect(page.getByLabel(TOGGLE_LABEL)).toBeChecked({ checked: target })

  // Restore the original state so the test is idempotent across runs.
  await page.locator('label.settings-toggle', { hasText: TOGGLE_LABEL }).click()
  await expect(page.getByLabel(TOGGLE_LABEL)).toBeChecked({ checked: initial })
  await page.locator('.settings-savebar-actions').getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText('All changes saved')).toBeVisible()
})
