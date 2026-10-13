// Helpers for the tool (MCP) form: a command is typed as one line and variables as one KEY=value per line.

import type { ToolSignIn } from './api'

/** "npx -y @scope/server" from a stored command and its arguments (quoting any argument that has a space) */
export const commandLine = (command: string, args: string[]) =>
  [command, ...args.map((a) => (/[\s"]/.test(a) ? `"${a.replace(/(["\\])/g, '\\$1')}"` : a))].join(' ')

export function parseEnv(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const i = line.indexOf('=')
    if (i > 0 && line.trim()) out[line.slice(0, i).trim()] = line.slice(i + 1).trim()
  }
  return out
}

export const formatEnv = (env: Record<string, string>) =>
  Object.entries(env)
    .map(([k, v]) => `${k}=${v}`)
    .join('\n')

export const isVariableName = (name: string) => /^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(name)

/** what the registry browser needs to know about one thing to fill in (see RegistryInput in api.ts) */
interface InputLike {
  id: string
  label: string
  required: boolean
  default: string
}

/** the answers a form starts with: every input's default, where it has one */
export function startingValues(inputs: (InputLike & { default: string })[]): Record<string, string> {
  return Object.fromEntries(inputs.filter((i) => i.default).map((i) => [i.id, i.default]))
}

/** the labels of required inputs that have no answer and no default, in order */
export function missingInputs(inputs: InputLike[], values: Record<string, string>): string[] {
  return inputs.filter((i) => i.required && !(values[i.id] ?? '').trim() && !i.default).map((i) => i.label)
}

/** the inputs a person has to fill in, and the ones that can stay as they are */
export function splitInputs<T extends InputLike>(inputs: T[]): { needed: T[]; optional: T[] } {
  return { needed: inputs.filter((i) => i.required), optional: inputs.filter((i) => !i.required) }
}

/** a download count for a card: 1.2K, 30M */
export function formatCount(n: number): string {
  if (n < 1000) return String(n)
  const units: [number, string][] = [
    [1e9, 'B'],
    [1e6, 'M'],
    [1e3, 'K'],
  ]
  for (const [size, unit] of units) {
    if (n >= size) {
      const v = n / size
      return `${v >= 10 || Number.isInteger(v) ? Math.round(v) : v.toFixed(1)}${unit}`
    }
  }
  return String(n)
}

/** up to two letters to draw in place of a tool's icon: the first letters of its first two words */
export function initials(title: string): string {
  const words = title.split(/[^A-Za-z0-9]+/).filter(Boolean)
  const letters = words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? '?').slice(0, 2)
  return letters.toUpperCase()
}

/** a hue (0 to 359) that is the same for the same name, so a tool keeps its colour between visits */
export function hueOf(name: string): number {
  let h = 0
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360
  return h
}

// ----- tools that sign in (see backend/app/mcp_auth) -----

/** How a tool that signs in is shown: a label, a tone for its badge and the button's words. Null for a tool that does
 * not sign in, so nothing is drawn for it. */
export function signInSummary(sign: ToolSignIn | null): { label: string; tone: 'ok' | 'warn'; action: string } | null {
  if (!sign) return null
  if (sign.state === 'signed_in') {
    return { label: sign.account ? `Signed in as ${sign.account}` : 'Signed in', tone: 'ok', action: 'Sign in again' }
  }
  if (sign.state === 'needs_sign_in') return { label: 'Needs a new sign in', tone: 'warn', action: 'Sign in again' }
  return { label: 'Not signed in', tone: 'warn', action: 'Sign in' }
}

/** What the service's redirect left in the page's address (`?mcp_sign_in=ok&message=Acme`), or null when the page was
 * not opened that way. */
export function signInOutcome(search: string): { ok: boolean; message: string } | null {
  const params = new URLSearchParams(search)
  const outcome = params.get('mcp_sign_in')
  if (outcome !== 'ok' && outcome !== 'error') return null
  return { ok: outcome === 'ok', message: params.get('message') ?? '' }
}

/** the address without the sign in outcome, so a reload or a shared link does not repeat the notice */
export function withoutSignInOutcome(search: string): string {
  const params = new URLSearchParams(search)
  params.delete('mcp_sign_in')
  params.delete('message')
  const rest = params.toString()
  return rest ? `?${rest}` : ''
}
