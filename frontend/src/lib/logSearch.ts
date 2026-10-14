export type LogFragment = { text: string; match: number | null }

export function searchLog(lines: string[], query: string): { rows: LogFragment[][]; count: number } {
  // A literal pattern keeps filenames and command punctuation from becoming search syntax.
  const pattern = query ? new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'giu') : null
  let count = 0
  const rows = lines.map((line) => {
    if (!pattern) return [{ text: line, match: null }]
    const fragments: LogFragment[] = []
    let start = 0
    for (const match of line.matchAll(pattern)) {
      if (match.index > start) fragments.push({ text: line.slice(start, match.index), match: null })
      fragments.push({ text: match[0], match: count++ })
      start = match.index + match[0].length
    }
    if (start < line.length || !fragments.length) fragments.push({ text: line.slice(start), match: null })
    return fragments
  })
  return { rows, count }
}

export function nextLogMatch(current: number, count: number, direction: number): number {
  return count ? ((current + direction) % count + count) % count : 0
}
