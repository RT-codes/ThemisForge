export type Kind = 'plain' | 'command' | 'output' | 'thinking' | 'note' | 'error'

// Light touch, no markdown: tell apart what an agent said, ran and thought. A blank line ends a block.
export function classify(lines: string[]): { text: string; kind: Kind }[] {
  let mode: Kind = 'plain'
  return lines.map((line) => {
    if (!line.trim()) {
      mode = 'plain'
      return { text: line, kind: 'plain' }
    }
    if (line.startsWith('$ ')) {
      mode = 'output'
      return { text: line, kind: 'command' }
    }
    if (line.startsWith('[thinking]')) {
      mode = 'thinking'
      return { text: line, kind: 'thinking' }
    }
    if (/^\[(exit [1-9]\d*\]|Cell error|Unexpected error|Cancelled\]|codex\] error)/.test(line)) return { text: line, kind: 'error' }
    if (/^\[[^\]]+\]/.test(line)) return { text: line, kind: 'note' }
    return { text: line, kind: mode }
  })
}
