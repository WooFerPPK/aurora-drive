import { spawn, type ChildProcess } from 'node:child_process'
import { resolve } from 'node:path'

const REPO_ROOT = resolve(__dirname, '..', '..', '..')
const BACKEND_DIR = resolve(REPO_ROOT, 'apps', 'backend')
const PUMP_SCRIPT = resolve(__dirname, 'scripts', 'udp_pump.py')

let pumpProcess: ChildProcess | null = null

export default async function globalSetup(): Promise<void> {
  // Start the synthetic UDP pump. Backend webServer is already up
  // by the time this runs, so the listener is bound.
  pumpProcess = spawn('uv', ['run', 'python', PUMP_SCRIPT], {
    cwd: BACKEND_DIR,
    stdio: 'inherit',
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  })
  pumpProcess.on('exit', (code, signal) => {
    if (!signal) {
      console.error(`[e2e] udp_pump exited unexpectedly: code=${code}`)
    }
  })
}

export async function teardownPump(): Promise<void> {
  if (pumpProcess && pumpProcess.pid && pumpProcess.exitCode === null) {
    pumpProcess.kill('SIGTERM')
    await new Promise<void>((resolveWait) => {
      pumpProcess!.once('exit', () => resolveWait())
      setTimeout(() => {
        if (pumpProcess && pumpProcess.exitCode === null) pumpProcess.kill('SIGKILL')
        resolveWait()
      }, 2000)
    })
  }
  pumpProcess = null
}
