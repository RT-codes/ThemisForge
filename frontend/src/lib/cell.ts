// Small helpers for showing a cell's size. The scheduler decides the real layering (backend/app/profiles.py);
// this only lets a form say, before anything runs, what an empty override would end up using.

export type CellSize = { cpus: number; memory_mb: number; timeout_seconds: number; image: string }
export type CellOverride = { cpus?: number | null; memory_mb?: number | null; timeout_seconds?: number | null; image?: string | null }

/** the defaults with each layer on top of it, in order; fields a layer does not set are left alone */
export function effectiveCell(defaults: CellSize, ...layers: (CellOverride | null | undefined)[]): CellSize {
  const out = { ...defaults }
  for (const layer of layers)
    for (const key of Object.keys(out) as (keyof CellSize)[]) {
      const value = layer?.[key]
      if (value !== undefined && value !== null && value !== '') (out as Record<string, unknown>)[key] = value
    }
  return out
}

const timeLimit = (seconds: number) =>
  seconds % 3600 === 0 ? `${seconds / 3600} h` : seconds % 60 === 0 ? `${seconds / 60} min` : `${seconds} s`

/** "1 CPU · 1024 MB · 1 h": the part of a cell a person cares about at a glance */
export const describeCell = (c: Pick<CellSize, 'cpus' | 'memory_mb' | 'timeout_seconds'>) =>
  `${c.cpus} ${c.cpus === 1 ? 'CPU' : 'CPUs'} · ${c.memory_mb} MB · ${timeLimit(c.timeout_seconds)}`
