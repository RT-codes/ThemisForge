/**
 * Where a dragged card lands inside a column.
 *
 * `siblings` are the positions of the column's other cards in display order (the dragged card
 * excluded) and `index` is the slot the pointer is over (0 = top, siblings.length = bottom).
 * The result sorts between its new neighbours, so only the moved task is updated.
 */
export function dropPosition(siblings: number[], index: number): number {
  const before = siblings[index - 1]
  const after = siblings[index]
  if (before === undefined && after === undefined) return 1
  if (before === undefined) return after - 1
  if (after === undefined) return before + 1
  return (before + after) / 2
}
