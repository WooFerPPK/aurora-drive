// Extends Vitest's `expect` with @testing-library/jest-dom matchers
// (toHaveAttribute, toBeInTheDocument, etc) and the corresponding
// TypeScript declaration augmentation. Loaded once per test run via
// vitest.config.ts → test.setupFiles.
import '@testing-library/jest-dom/vitest'
