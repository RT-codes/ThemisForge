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

// ---------- theme colours: the theme editor works on CSS colours, mostly oklch() ----------

export interface Oklch {
  l: number // lightness, 0 to 1
  c: number // chroma, about 0 to 0.4
  h: number // hue in degrees
  alpha: number // 0 to 1
}

const NUMBER = '[+-]?(?:\\d+\\.?\\d*|\\.\\d+)'
const OKLCH = new RegExp(`^oklch\\(\\s*(${NUMBER})(%?)\\s+(${NUMBER})\\s+(${NUMBER})(?:deg)?\\s*(?:/\\s*(${NUMBER})(%?)\\s*)?\\)$`, 'i')

/** "oklch(0.76 0.17 58)", "oklch(76% 0.17 58 / 60%)"; anything else (hex, rgb(), a named colour) is not one (null) */
export function parseOklch(value: string): Oklch | null {
  const m = OKLCH.exec(value.trim())
  if (!m) return null
  const l = m[2] ? Number(m[1]) / 100 : Number(m[1])
  const alpha = m[5] === undefined ? 1 : m[6] ? Number(m[5]) / 100 : Number(m[5])
  return { l, c: Number(m[3]), h: Number(m[4]), alpha: Math.min(1, Math.max(0, alpha)) }
}

const round = (n: number, digits: number) => String(Number(n.toFixed(digits)))

export function formatOklch({ l, c, h, alpha }: Oklch): string {
  const base = `${round(l, 3)} ${round(c, 3)} ${round(((h % 360) + 360) % 360, 1)}`
  return alpha < 1 ? `oklch(${base} / ${round(alpha * 100, 0)}%)` : `oklch(${base})`
}

const toLinear = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)
const fromLinear = (v: number) => (v <= 0.0031308 ? v * 12.92 : 1.055 * v ** (1 / 2.4) - 0.055)
const clamp01 = (v: number) => Math.min(1, Math.max(0, v))

/** The sRGB hex of an oklch colour (alpha is dropped; a colour outside sRGB is clipped to it) */
export function oklchToHex({ l, c, h }: Oklch): string {
  const a = c * Math.cos((h * Math.PI) / 180)
  const b = c * Math.sin((h * Math.PI) / 180)
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3
  const rgb = [
    4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
    -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
    -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_,
  ]
  return `#${rgb.map((v) => Math.round(clamp01(fromLinear(clamp01(v))) * 255).toString(16).padStart(2, '0')).join('')}`
}

/** The oklch of a hex colour, with the given alpha ("#3b82f6" and "#38f" both work); null when it is not a hex colour */
export function hexToOklch(hex: string, alpha = 1): Oklch | null {
  const normal = normalizeHex(hex)
  if (!normal) return null
  const [r, g, b] = [1, 3, 5].map((i) => toLinear(parseInt(normal.slice(i, i + 2), 16) / 255))
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s
  const bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
  const chroma = Math.hypot(a, bb)
  return {
    l: 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    c: chroma,
    h: chroma < 1e-4 ? 0 : ((Math.atan2(bb, a) * 180) / Math.PI + 360) % 360, // a grey has no hue
    alpha,
  }
}

/** Whether a string is a colour a theme can use: oklch, hex, or anything else the browser itself accepts (rgb(), hsl(), names) */
export function isColor(value: string): boolean {
  const v = value.trim()
  if (!v) return false
  if (parseOklch(v) || normalizeHex(v)) return true
  return typeof CSS !== 'undefined' && CSS.supports('color', v)
}

/** The colour for the browser's own picker, which only speaks six-digit hex: oklch and hex are converted, the rest
 *  starts the picker at black. */
export function swatchHex(value: string): string {
  const oklch = parseOklch(value)
  if (oklch) return oklchToHex(oklch)
  return normalizeHex(value) ?? '#000000'
}
