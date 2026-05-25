import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

interface ErrorBoundaryProps {
  children?: ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error: Error): ErrorBoundaryState { return { error } }
  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.warn('[ErrorBoundary]', error, info?.componentStack)
  }
  reset = (): void => this.setState({ error: null })
  override render(): ReactNode {
    if (!this.state.error) return this.props.children
    return (
      <div className="p-[30px]">
        <div className="max-w-[540px] mx-auto bg-[rgba(255,94,167,0.08)] border border-[rgba(255,94,167,0.4)] rounded-xl p-5 text-cream font-ui">
          <div className="font-display text-[18px] mb-2 text-pink">Something cracked.</div>
          <div className="font-mono text-[12px] text-ink-dim whitespace-pre-wrap mb-3">{String(this.state.error?.message || this.state.error)}</div>
          <button className="btn" onClick={this.reset}>Reset</button>
        </div>
      </div>
    )
  }
}
