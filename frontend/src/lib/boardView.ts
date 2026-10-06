// What the board shows: a search, filters and an order. One setting applies to the whole board, and every status
// column can add its own on top (its own order, and filters that narrow it further).

import type { Harness, PropertyDef, ScheduleKind, Task } from './api'

export type SortKey = 'manual' | 'newest' | 'oldest' | 'title' | 'next_run'

export const SORTS: { id: SortKey; label: string }[] = [
  { id: 'manual', label: 'Your order' },
  { id: 'newest', label: 'Newest first' },
  { id: 'oldest', label: 'Oldest first' },
  { id: 'title', label: 'Title A to Z' },
  { id: 'next_run', label: 'Next run soonest' },
]

export const SCHEDULE_CHOICES: { id: ScheduleKind; label: string }[] = [
  { id: 'none', label: 'No schedule' },
  { id: 'once', label: 'One-off' },
  { id: 'cron', label: 'Repeating' },
]

export const HARNESS_CHOICES: { id: Harness; label: string }[] = [
  { id: '', label: 'Placeholder program' },
  { id: 'codex', label: 'Codex agent' },
  { id: 'workflow', label: 'Workflow' },
]

/** the value that stands for "this task has no value for the property" */
export const NO_VALUE = ''

/** an empty list means "anything": nothing is being filtered on that */
export type Filters = {
  schedule: ScheduleKind[]
  harness: Harness[]
  props: Record<string, string[]>
}
export type BoardView = { search: string; sort: SortKey; filters: Filters }
export type ColumnView = { sort: SortKey | null; filters: Filters } // sort null: follow the board

export const emptyFilters = (): Filters => ({ schedule: [], harness: [], props: {} })
export const emptyView = (): BoardView => ({ search: '', sort: 'manual', filters: emptyFilters() })
export const emptyColumn = (): ColumnView => ({ sort: null, filters: emptyFilters() })

/** how many things are being filtered on (a property with two options chosen is still one) */
export function filterCount(f: Filters): number {
  return (f.schedule.length ? 1 : 0) + (f.harness.length ? 1 : 0) + Object.values(f.props).filter((o) => o.length).length
}

export const isDefaultView = (v: BoardView) => v.search.trim() === '' && v.sort === 'manual' && filterCount(v.filters) === 0
export const isDefaultColumn = (c: ColumnView) => c.sort === null && filterCount(c.filters) === 0

/** add the value to the list, or take it out if it is there already */
export function toggled<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
}

function matches(task: Task, f: Filters): boolean {
  if (f.schedule.length && !f.schedule.includes(task.schedule_kind)) return false
  if (f.harness.length && !f.harness.includes(task.harness)) return false
  for (const [key, wanted] of Object.entries(f.props)) {
    if (!wanted.length) continue
    const value = task.properties[key]
    if (!wanted.includes(value === undefined ? NO_VALUE : String(value))) return false
  }
  return true
}

export function sortTasks(tasks: Task[], sort: SortKey): Task[] {
  const byPosition = (a: Task, b: Task) => a.position - b.position
  const copy = [...tasks]
  switch (sort) {
    case 'newest':
      return copy.sort((a, b) => b.created_at.localeCompare(a.created_at) || byPosition(a, b))
    case 'oldest':
      return copy.sort((a, b) => a.created_at.localeCompare(b.created_at) || byPosition(a, b))
    case 'title':
      return copy.sort((a, b) => a.title.localeCompare(b.title, undefined, { sensitivity: 'base' }) || byPosition(a, b))
    case 'next_run':
      return copy.sort((a, b) => {
        if (a.next_run_at && b.next_run_at) return a.next_run_at.localeCompare(b.next_run_at) || byPosition(a, b)
        if (a.next_run_at) return -1 // tasks that will run come before tasks that will not
        if (b.next_run_at) return 1
        return byPosition(a, b)
      })
    default:
      return copy.sort(byPosition)
  }
}

export type ColumnResult = {
  shown: Task[]
  /** something hides tasks from this column */
  filtered: boolean
  /** the cards are in the order the person arranged them, so dropping a card between two others means something */
  reorderable: boolean
}

/** the tasks of one status column, after the board's search and filters, the column's own filters, and the order */
export function applyView(tasks: Task[], board: BoardView, column: ColumnView = emptyColumn()): ColumnResult {
  const needle = board.search.trim().toLowerCase()
  const shown = tasks.filter(
    (t) =>
      (needle === '' || `${t.title}\n${t.description}`.toLowerCase().includes(needle)) &&
      matches(t, board.filters) &&
      matches(t, column.filters)
  )
  const sort = column.sort ?? board.sort
  const filtered = shown.length !== tasks.length
  const narrowed = needle !== '' || filterCount(board.filters) > 0 || filterCount(column.filters) > 0
  return { shown: sortTasks(shown, sort), filtered, reorderable: sort === 'manual' && !narrowed }
}

/** the options of every select property: what the filter menu offers */
export const selectProperties = (defs: PropertyDef[]) => defs.filter((d) => d.type === 'select' && d.options.length)

// ----- remembering it (per project, in this browser) -----

const SORT_IDS = new Set<string>(SORTS.map((s) => s.id))
const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [])

function parseFilters(v: unknown): Filters {
  const o = (v && typeof v === 'object' ? v : {}) as Record<string, unknown>
  const props: Record<string, string[]> = {}
  for (const [key, list] of Object.entries((o.props && typeof o.props === 'object' ? o.props : {}) as Record<string, unknown>)) {
    const chosen = strings(list)
    if (chosen.length) props[key] = chosen
  }
  return {
    schedule: strings(o.schedule).filter((s): s is ScheduleKind => ['none', 'once', 'cron'].includes(s)),
    harness: strings(o.harness).filter((s): s is Harness => ['', 'codex', 'workflow'].includes(s)),
    props,
  }
}

/** whatever was stored, made safe to use: a stale or edited value falls back to the default instead of breaking the board */
export function parseStored(text: string | null): { board: BoardView; columns: Record<string, ColumnView>; hidden: string[] } {
  const board = emptyView()
  const columns: Record<string, ColumnView> = {}
  let hidden: string[] = []
  try {
    const data = JSON.parse(text ?? '{}')
    hidden = strings(data.hidden)
    if (typeof data.board?.search === 'string') board.search = data.board.search
    if (SORT_IDS.has(data.board?.sort)) board.sort = data.board.sort
    board.filters = parseFilters(data.board?.filters)
    for (const [status, c] of Object.entries((data.columns ?? {}) as Record<string, { sort?: unknown; filters?: unknown }>)) {
      columns[status] = { sort: typeof c?.sort === 'string' && SORT_IDS.has(c.sort) ? (c.sort as SortKey) : null, filters: parseFilters(c?.filters) }
    }
  } catch {
    // unreadable: start fresh
  }
  return { board, columns, hidden }
}
