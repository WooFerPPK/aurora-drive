import { teardownPump } from './global-setup'

export default async function globalTeardown(): Promise<void> {
  await teardownPump()
}
