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

/** Positions for `count` cards that all go to the end of a column, keeping their own order (a bulk move). */
export function appendPositions(siblings: number[], count: number): number[] {
  const first = dropPosition(siblings, siblings.length)
  return Array.from({ length: count }, (_, i) => first + i)
}

/**
 * The selection after a Ctrl+click on `clicked`. `open` is the task whose details are open in the panel (null when
 * none, or when it cannot be picked): it was chosen first, so it joins the selection with the card just clicked.
 */
export function togglePick(picked: number[], clicked: number, open: number | null): number[] {
  const ids = open !== null && open !== clicked && !picked.includes(open) ? [...picked, open] : picked
  return ids.includes(clicked) ? ids.filter((id) => id !== clicked) : [...ids, clicked]
}

/**
 * The cards from `anchor` to `clicked` in one column (a shift+click), both included, in column order. `order` is the
 * ids of that column as it is shown. Null when either card is not in it: a range never leaves a status, so a card of
 * another status (or one the filters hide) is not the other end of one.
 */
export function rangePick(order: number[], anchor: number, clicked: number): number[] | null {
  const a = order.indexOf(anchor)
  const b = order.indexOf(clicked)
  if (a < 0 || b < 0) return null
  return order.slice(Math.min(a, b), Math.max(a, b) + 1)
}
