// Colours people pick for the options of a select property (Priority: High, Medium, Low...).

export const PALETTE = [
  { name: 'Red', hex: '#f87171' },
  { name: 'Orange', hex: '#fb923c' },
  { name: 'Amber', hex: '#fbbf24' },
  { name: 'Lime', hex: '#a3e635' },
  { name: 'Green', hex: '#34d399' },
  { name: 'Teal', hex: '#2dd4bf' },
  { name: 'Sky', hex: '#38bdf8' },
  { name: 'Blue', hex: '#60a5fa' },
  { name: 'Violet', hex: '#a78bfa' },
  { name: 'Pink', hex: '#f472b6' },
]

export const isHex = (value: string) => /^#[0-9a-f]{6}$/i.test(value)

/** "#3b82f6", "3B82F6" and "#38f" all mean a colour; anything else is not one (null) */
export function normalizeHex(input: string): string | null {
  const v = input.trim().replace(/^#/, '').toLowerCase()
  if (/^[0-9a-f]{3}$/.test(v)) return `#${v[0]}${v[0]}${v[1]}${v[1]}${v[2]}${v[2]}`
  return /^[0-9a-f]{6}$/.test(v) ? `#${v}` : null
}

/** the look of a chip in a colour: a tint behind, the colour itself lightened for the text, so even dark picks read */
export function chipStyle(hex: string | undefined): string | undefined {
  if (!hex || !isHex(hex)) return undefined
  return `background-color: color-mix(in oklab, ${hex} 20%, transparent); color: color-mix(in oklab, ${hex} 55%, white); border-color: color-mix(in oklab, ${hex} 35%, transparent);`
}
