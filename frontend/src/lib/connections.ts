// The list of services a person can connect, as the Settings page shows it: searchable and grouped by kind.
import type { ConnectionProvider } from './api'

export interface CatalogEntry {
  id: string
  name: string
  description: string
  icon: string // a Lucide icon name
  category: string
}

export const CATEGORIES = [
  { id: 'ai', label: 'AI models' },
  { id: 'service', label: 'Services' },
]

// Codex has its own screen for now (it signs in through a container). It is listed beside the providers so the
// person sees one list; opening it shows that screen.
export const CODEX: CatalogEntry = {
  id: 'codex',
  name: 'Codex',
  description: "Sign in with ChatGPT so tasks use your plan's Codex usage.",
  icon: 'sparkles',
  category: 'ai',
}

export const catalog = (providers: ConnectionProvider[]): CatalogEntry[] => [
  CODEX,
  ...providers.map(({ id, name, description, icon, category }) => ({ id, name, description, icon, category })),
]

export function filterCatalog(entries: CatalogEntry[], query: string): CatalogEntry[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return entries
  return entries.filter((e) => {
    const label = CATEGORIES.find((c) => c.id === e.category)?.label ?? e.category
    const text = `${e.name} ${e.description} ${label}`.toLowerCase()
    return words.every((w) => text.includes(w))
  })
}

export function groupByCategory(entries: CatalogEntry[]): { id: string; label: string; entries: CatalogEntry[] }[] {
  const known = CATEGORIES.map((c) => ({ ...c, entries: entries.filter((e) => e.category === c.id) }))
  const rest = entries.filter((e) => !CATEGORIES.some((c) => c.id === e.category))
  return [...known, { id: 'other', label: 'Other', entries: rest }].filter((g) => g.entries.length)
}

// One short line under each way of connecting, so the choice explains itself.
export const METHOD_HINT = {
  token: 'You control exactly what it can access and for how long. Recommended.',
  oauth: 'Fastest, but the access it is given is broader than a token you scope yourself.',
} as const

export const METHOD_LABEL = { token: 'Token', oauth: 'Sign in' } as const
