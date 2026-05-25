import { useDashUI } from '@/features/dashboard/context/DashUIContext'
import { cx } from '@/shared/lib/format'
import { TOOLBAR_BTN, TOOLBAR_BTN_EDIT_ON } from '@/shared/components/layout/toolbarStyles'

export default function EditToggle() {
  const { toolbarApi, editMode, toggleEditMode } = useDashUI()
  if (!toolbarApi) return null

  return (
    <button
      type="button"
      className={cx(TOOLBAR_BTN, editMode && TOOLBAR_BTN_EDIT_ON)}
      onClick={toggleEditMode}
      aria-pressed={editMode}
      title={editMode ? 'Lock widgets' : 'Edit widgets'}
    >
      {editMode ? '✓ DONE' : '✎ EDIT'}
    </button>
  )
}
