// Finding a Lucide icon by typing: the names are words joined by hyphens ("folder-kanban", "shopping-cart").

/** The names that contain every word typed, best matches first: the exact name, then names that start with the first
 *  word, then the rest in alphabetical order. An empty search matches everything. */
export function matchIcons(names: string[], query: string): string[] {
  const words = query.toLowerCase().split(/[\s-]+/).filter(Boolean)
  const wanted = words.join('-')
  const rank = (name: string) => (name === wanted ? 0 : name.startsWith(words[0] ?? '') ? 1 : 2)
  return names
    .filter((name) => words.every((w) => name.includes(w)))
    .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
}

/** "folder-kanban" for a file such as /node_modules/@lucide/svelte/dist/icons/folder-kanban.svelte; null for anything else */
export function iconNameOf(path: string): string | null {
  const m = path.match(/\/([a-z0-9]+(?:-[a-z0-9]+)*)\.svelte$/)
  return m ? m[1] : null
}
