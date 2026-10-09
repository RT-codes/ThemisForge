import type { Component } from 'svelte'
import { iconNameOf } from './iconSearch'

// Every Lucide icon, loaded one at a time: the page only fetches the icons it actually shows, and the picker the ones
// in view. The names come from the file names, so a new version of the library needs no list kept by hand.
const loaders = import.meta.glob<{ default: Component }>('/node_modules/@lucide/svelte/dist/icons/*.svelte')

const byName = new Map<string, () => Promise<{ default: Component }>>()
for (const [path, load] of Object.entries(loaders)) {
  const name = iconNameOf(path)
  if (name) byName.set(name, load)
}

/** all the icon names, alphabetical */
export const iconNames = [...byName.keys()].sort()

const loaded = new Map<string, Component | null>()

/** the icon if it was loaded before (so it can be drawn at once), undefined if not, null if there is no such icon */
export const cachedIcon = (name: string) => loaded.get(name)

/** the icon component for a name; null when there is no such icon (an old name, or a typo) */
export async function loadIcon(name: string): Promise<Component | null> {
  if (loaded.has(name)) return loaded.get(name) ?? null
  const load = byName.get(name)
  const component = load ? (await load()).default : null
  loaded.set(name, component)
  return component
}
