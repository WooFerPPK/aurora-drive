import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Select from '@/shared/components/primitives/Select'

describe('Select', () => {
  const options = [
    { value: 10, label: '10 Hz' },
    { value: 30, label: '30 Hz' },
    { value: 60, label: '60 Hz' },
  ] as const

  function setup() {
    const onChange = vi.fn<(v: number) => void>()
    render(
      <Select<number>
        value={10}
        onChange={onChange}
        options={options.map((o) => ({ value: o.value, label: o.label }))}
        ariaLabel="rate"
      />,
    )
    const trigger = screen.getByRole('button', { name: 'rate' })
    return { onChange, trigger }
  }

  it('opens on ArrowDown and closes on Escape', () => {
    const { trigger } = setup()
    expect(trigger).toHaveAttribute('aria-expanded', 'false')

    fireEvent.keyDown(trigger, { key: 'ArrowDown' })
    expect(trigger).toHaveAttribute('aria-expanded', 'true')

    fireEvent.keyDown(trigger, { key: 'Escape' })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
  })

  it('opens on Space', () => {
    const { trigger } = setup()
    fireEvent.keyDown(trigger, { key: ' ' })
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
  })

  it('selects the highlighted option on Enter with the correctly-typed value', () => {
    const { onChange, trigger } = setup()
    fireEvent.keyDown(trigger, { key: 'ArrowDown' })   // open (highlight stays on selected: 10)
    fireEvent.keyDown(trigger, { key: 'ArrowDown' })   // highlight → 30
    fireEvent.keyDown(trigger, { key: 'Enter' })       // pick

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith(30)
  })

  it('jumps to last option on End', () => {
    const { onChange, trigger } = setup()
    fireEvent.keyDown(trigger, { key: 'ArrowDown' })   // open
    fireEvent.keyDown(trigger, { key: 'End' })
    fireEvent.keyDown(trigger, { key: 'Enter' })

    expect(onChange).toHaveBeenLastCalledWith(60)
  })

  it('jumps to first option on Home', () => {
    const { onChange, trigger } = setup()
    fireEvent.keyDown(trigger, { key: 'ArrowDown' })   // open
    fireEvent.keyDown(trigger, { key: 'End' })          // highlight last (60)
    fireEvent.keyDown(trigger, { key: 'Home' })         // back to first (10)
    fireEvent.keyDown(trigger, { key: 'Enter' })

    expect(onChange).toHaveBeenLastCalledWith(10)
  })
})
