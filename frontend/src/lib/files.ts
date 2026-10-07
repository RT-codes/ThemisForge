import type { FileEntry } from './api'

// Pure helpers for the Files page. Paths are slash separated and relative to a folder's root; "" is the root.

export const joinPath = (folder: string, name: string) => (folder ? `${folder}/${name}` : name)

export const parentPath = (path: string) => path.split('/').slice(0, -1).join('/')

/** "reports/2024" -> [{name: 'reports', path: 'reports'}, {name: '2024', path: 'reports/2024'}] */
export function crumbs(path: string): { name: string; path: string }[] {
  const parts = path.split('/').filter(Boolean)
  return parts.map((name, i) => ({ name, path: parts.slice(0, i + 1).join('/') }))
}

/** what a shared folder may be called: the server's rule (volumes.py NAME), checked as the person types */
export const isValidFolderName = (name: string) => /^[a-z0-9][a-z0-9-]{0,39}$/.test(name.trim().toLowerCase())

/** a single file or folder name: no slashes, and not one of the names that mean something to a path */
export const isValidName = (name: string) => {
  const n = name.trim()
  return n !== '' && n !== '.' && n !== '..' && !n.includes('/') && !n.includes('\0')
}

// the same list the server shows inline (INLINE_IMAGES in routers/volumes.py)
const IMAGES = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'avif', 'bmp', 'ico', 'svg'])
const TEXT = new Set([
  'txt', 'md', 'markdown', 'json', 'jsonl', 'csv', 'tsv', 'log', 'yaml', 'yml', 'toml', 'ini', 'xml', 'html', 'css',
  'js', 'ts', 'py', 'sh', 'sql', 'rs', 'go', 'svelte', 'diff', 'patch', 'cfg', 'conf', 'env', 'properties', 'rb',
  'java', 'c', 'h', 'cpp', 'hpp', 'php', 'tsx', 'jsx', 'mjs', 'cjs', 'vue', 'scss', 'less', 'lock',
])
// well known text files that have no extension (or only a dot in front)
const TEXT_NAMES = new Set(['makefile', 'dockerfile', 'license', 'readme', 'changelog', '.gitignore', '.dockerignore', '.env', '.editorconfig'])
const MAX_TEXT_PREVIEW = 1024 * 1024 // bytes: bigger files are downloaded, not shown

/** what a file is by its name: an image, text, or anything else */
export function fileKind(name: string): 'image' | 'text' | 'other' {
  const dot = name.lastIndexOf('.')
  const ext = dot > 0 ? name.slice(dot + 1).toLowerCase() : ''
  if (IMAGES.has(ext)) return 'image'
  return TEXT.has(ext) || TEXT_NAMES.has(name.toLowerCase()) ? 'text' : 'other'
}

export const isMarkdown = (name: string) => /\.(md|markdown)$/i.test(name)

/** Where a picture named in a markdown file (`![](img/a.png)`) lives, as a path inside the same folder tree. A relative
 * path is read from the folder the markdown file is in; a web address, an absolute path or a path that climbs out of the
 * folder is refused (null), because a file written by an agent must not make this page load things from elsewhere. */
export function resolveRelative(dir: string, src: string): string | null {
  const href = src.trim()
  if (!href || href.startsWith('/') || /^[a-z][a-z0-9+.-]*:/i.test(href)) return null
  let parts = dir.split('/').filter(Boolean)
  for (const part of href.split(/[?#]/)[0].split('/')) {
    if (part === '' || part === '.') continue
    if (part === '..') {
      if (!parts.length) return null
      parts = parts.slice(0, -1)
    } else parts = [...parts, decodeURIComponent(part)]
  }
  return parts.length ? parts.join('/') : null
}

/** how a file can be shown in the page: as an image, as text, or not at all (download only) */
export function previewKind(name: string, size: number): 'image' | 'text' | null {
  const kind = fileKind(name)
  if (kind === 'image' || (kind === 'text' && size <= MAX_TEXT_PREVIEW)) return kind
  return null
}

export type FileSort = 'name' | 'newest' | 'oldest' | 'largest' | 'smallest'
export type FileType = 'all' | 'text' | 'image' | 'other'
export type FileView = { search: string; sort: FileSort; type: FileType }

export const FILE_SORTS: { id: FileSort; label: string }[] = [
  { id: 'name', label: 'Name A to Z' },
  { id: 'newest', label: 'Newest first' },
  { id: 'oldest', label: 'Oldest first' },
  { id: 'largest', label: 'Largest first' },
  { id: 'smallest', label: 'Smallest first' },
]

export const FILE_TYPES: { id: FileType; label: string }[] = [
  { id: 'all', label: 'All files' },
  { id: 'text', label: 'Text and documents' },
  { id: 'image', label: 'Images' },
  { id: 'other', label: 'Other' },
]

export const emptyFileView = (): FileView => ({ search: '', sort: 'name', type: 'all' })
export const isDefaultFileView = (v: FileView) => v.search.trim() === '' && v.sort === 'name' && v.type === 'all'

type Listed = { name: string; is_dir: boolean; size: number; modified: string }

/** One level of the tree as the page shows it: folders first and always by name, whatever the search says (so you can
 * still open them), then the files that match the search and type, in the chosen order. */
export function arrange<T extends Listed>(entries: T[], view: FileView): T[] {
  const needle = view.search.trim().toLowerCase()
  const byName = (a: T, b: T) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' })
  const matches = (e: T) => !needle || e.name.toLowerCase().includes(needle)
  const folders = entries.filter((e) => e.is_dir).sort(byName)
  const order: Record<FileSort, (a: T, b: T) => number> = {
    name: byName,
    newest: (a, b) => b.modified.localeCompare(a.modified) || byName(a, b), // ISO timestamps sort as text
    oldest: (a, b) => a.modified.localeCompare(b.modified) || byName(a, b),
    largest: (a, b) => b.size - a.size || byName(a, b),
    smallest: (a, b) => a.size - b.size || byName(a, b),
  }
  const files = entries
    .filter((e) => !e.is_dir && matches(e) && (view.type === 'all' || fileKind(e.name) === view.type))
    .sort(order[view.sort])
  return [...folders, ...files]
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let i = 0
  while (value >= 1024 && i < units.length - 1) (value /= 1024), i++
  return `${value >= 10 ? Math.round(value) : value.toFixed(1)} ${units[i]}`
}

// ----- zooming a picture: scale 1 is "fit to the view", and the picture can be dragged once it is larger -----

export const ZOOM_MAX = 10

export type Zoom = { scale: number; x: number; y: number } // x and y: how far the picture is moved from the centre, in px
type Size = { w: number; h: number }

const clamp = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n))
export const clampScale = (scale: number) => clamp(scale, 1, ZOOM_MAX)

// the slider is logarithmic, so each step zooms by the same factor, like the wheel does
export const scaleToSlider = (scale: number) => Math.round((Math.log(scale) / Math.log(ZOOM_MAX)) * 100)
export const sliderToScale = (value: number) => ZOOM_MAX ** (value / 100)

/** keeps the picture from being dragged out of sight: it can only move as far as it overhangs the view (`box` and
 * `image` are layout sizes, so they do not change with the zoom), and a picture smaller than the view stays centred */
export function clampPan(x: number, y: number, scale: number, box: Size, image: Size): { x: number; y: number } {
  const room = (inner: number, outer: number) => Math.max(0, (inner * scale - outer) / 2)
  return { x: clamp(x, -room(image.w, box.w), room(image.w, box.w)), y: clamp(y, -room(image.h, box.h), room(image.h, box.h)) }
}

/** zooms to `scale` so that the point under the cursor (`at`, measured from the centre of the view) stays put */
export function zoomAt(zoom: Zoom, scale: number, at: { x: number; y: number }, box: Size, image: Size): Zoom {
  const next = clampScale(scale)
  const k = next / zoom.scale
  return { scale: next, ...clampPan(at.x - (at.x - zoom.x) * k, at.y - (at.y - zoom.y) * k, next, box, image) }
}

// ----- editing a text file: one draft at a time, kept by the page so it survives enlarging and closing the modal -----

export type Draft = { path: string; entry: FileEntry; original: string; text: string }
export const isDirty = (draft: Draft | null) => draft !== null && draft.text !== draft.original
