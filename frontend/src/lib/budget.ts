// The resource budget: how many cells of one size fit in it. Mirrors backend/app/budget.py, which has the
// authoritative copy (the scheduler uses it); this one only lets Settings show the answer while a value is typed.

export interface Budget {
  cpus: number
  memory_mb: number
}

const EPS = 1e-9 // so three 0.1 CPU cells fit in 0.3 CPUs

export function cellsThatFit(budget: Budget, cell: Budget): number {
  if (!(cell.cpus > 0) || !(cell.memory_mb > 0)) return 0
  const byCpu = Math.floor(budget.cpus / cell.cpus + EPS)
  const byMemory = Math.floor(budget.memory_mb / cell.memory_mb)
  return Math.max(0, Math.min(byCpu, byMemory))
}
