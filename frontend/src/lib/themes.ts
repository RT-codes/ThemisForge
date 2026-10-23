// Themes: every colour and shape token the interface reads, as data. A theme is written to the page as CSS variables
// (see applyTheme in appearance.ts), so components never name a colour: they use the Tailwind utilities that sit on
// these variables (bg-card, text-tone-green, ...), and a new theme is one more object here.
//
// Fonts and text scale are a separate axis (the typography presets in appearance.ts), so any theme can be combined
// with any typography.
//
// To add a built-in theme: write one more Theme object below (every token in COLOR_TOKENS is required, and the type checker
// and the test in appearance.test.ts say which is missing) and add it to `builtinThemes`. The picker in Settings lists it
// from there. Colours go through Tailwind's `@theme inline` block in app.css; a new token needs a `--color-*` line there too
// and a place in themeColors.ts (as a main colour, or as a derived one with a rule).

import { isColor } from './colors.ts'
import { COLOR_TOKENS, DERIVED_TOKENS, pinnedColors, resolveColors, type ColorToken, type DerivedToken, type ThemeMode } from './themeColors.ts'

export { COLOR_TOKENS, TONES, type ColorToken, type ThemeMode, type Tone } from './themeColors.ts'

export interface Theme {
	id: string
	name: string
	description: string
	/** whether the theme sits on a dark or a light surface: decides the `dark` class, the browser's own widgets
	 *  (scrollbars, date pickers) and the colour mode of embedded libraries */
	mode: ThemeMode
	/** every colour, as it is painted. For a custom theme the derived ones follow from the main colours (themeColors.ts)
	 *  unless they are pinned. */
	colors: Record<ColorToken, string>
	/** the derived colours that were set by hand and so do not follow the main colours (custom themes only) */
	pinned: DerivedToken[]
	/** colours a person saved to reuse (custom themes only) */
	palette: PaletteColor[]
	/** the base corner radius; every other radius is a multiple of it */
	radius: string
	/** the shadow under what floats above the page (panels, dialogs, menus) */
	shadowFloat: string
}

/** The Themis look: warm near-black surfaces with the brand orange as the primary colour. */
const themisDefault: Theme = {
	id: 'themis-default',
	name: 'Themis Default',
	description: 'Warm dark surfaces with the brand orange.',
	mode: 'dark',
	colors: {
		'background': 'oklch(0.145 0.008 50)',
		'foreground': 'oklch(0.97 0.005 80)',
		'card': 'oklch(0.19 0.01 50)',
		'card-foreground': 'oklch(0.97 0.005 80)',
		'popover': 'oklch(0.19 0.01 50)',
		'popover-foreground': 'oklch(0.97 0.005 80)',
		'primary': 'oklch(0.76 0.17 58)',
		'primary-foreground': 'oklch(0.2 0.02 50)',
		'secondary': 'oklch(0.25 0.012 50)',
		'secondary-foreground': 'oklch(0.97 0.005 80)',
		'muted': 'oklch(0.25 0.012 50)',
		'muted-foreground': 'oklch(0.7 0.015 70)',
		'accent': 'oklch(0.27 0.025 55)',
		'accent-foreground': 'oklch(0.97 0.005 80)',
		'destructive': 'oklch(0.704 0.191 22.216)',
		'border': 'oklch(1 0 0 / 9%)',
		'input': 'oklch(1 0 0 / 13%)',
		'ring': 'oklch(0.76 0.17 58 / 60%)',
		'chart-1': 'oklch(0.76 0.17 58)',
		'chart-2': 'oklch(0.65 0.19 40)',
		'chart-3': 'oklch(0.55 0.15 30)',
		'chart-4': 'oklch(0.45 0.1 25)',
		'chart-5': 'oklch(0.35 0.07 20)',
		'sidebar': 'oklch(0.175 0.01 50)',
		'sidebar-foreground': 'oklch(0.97 0.005 80)',
		'sidebar-primary': 'oklch(0.76 0.17 58)',
		'sidebar-primary-foreground': 'oklch(0.2 0.02 50)',
		'sidebar-accent': 'oklch(0.25 0.02 55)',
		'sidebar-accent-foreground': 'oklch(0.97 0.005 80)',
		'sidebar-border': 'oklch(1 0 0 / 8%)',
		'sidebar-ring': 'oklch(0.76 0.17 58 / 60%)',
		'glow': 'oklch(0.76 0.17 58)',
		'code': 'oklch(0.12 0.006 50)',
		'tone-green': 'oklch(0.765 0.177 163.223)',
		'tone-yellow': 'oklch(0.905 0.182 98.111)',
		'tone-amber': 'oklch(0.828 0.189 84.429)',
		'tone-violet': 'oklch(0.702 0.183 293.541)',
		'tone-sky': 'oklch(0.746 0.16 232.661)',
		'tone-rose': 'oklch(0.712 0.194 13.428)',
		'tone-teal': 'oklch(0.777 0.152 181.912)',
	},
	pinned: [],
	palette: [],
	radius: '0.625rem',
	shadowFloat: '0 0 28px 2px rgb(0 0 0 / 0.45)',
}

/** The same structure on light surfaces. Primary is near black here and the brand orange lives on in `glow`. */
const themisLight: Theme = {
	id: 'themis-light',
	name: 'Themis Light',
	description: 'Clean light surfaces with a near-black primary.',
	mode: 'light',
	colors: {
		'background': 'oklch(1 0 0)',
		'foreground': 'oklch(0.145 0 0)',
		'card': 'oklch(1 0 0)',
		'card-foreground': 'oklch(0.145 0 0)',
		'popover': 'oklch(1 0 0)',
		'popover-foreground': 'oklch(0.145 0 0)',
		'primary': 'oklch(0.205 0 0)',
		'primary-foreground': 'oklch(0.985 0 0)',
		'secondary': 'oklch(0.97 0 0)',
		'secondary-foreground': 'oklch(0.205 0 0)',
		'muted': 'oklch(0.97 0 0)',
		'muted-foreground': 'oklch(0.556 0 0)',
		'accent': 'oklch(0.97 0 0)',
		'accent-foreground': 'oklch(0.205 0 0)',
		'destructive': 'oklch(0.577 0.245 27.325)',
		'border': 'oklch(0.922 0 0)',
		'input': 'oklch(0.922 0 0)',
		'ring': 'oklch(0.708 0 0)',
		'chart-1': 'oklch(0.87 0 0)',
		'chart-2': 'oklch(0.556 0 0)',
		'chart-3': 'oklch(0.439 0 0)',
		'chart-4': 'oklch(0.371 0 0)',
		'chart-5': 'oklch(0.269 0 0)',
		'sidebar': 'oklch(0.985 0 0)',
		'sidebar-foreground': 'oklch(0.145 0 0)',
		'sidebar-primary': 'oklch(0.205 0 0)',
		'sidebar-primary-foreground': 'oklch(0.985 0 0)',
		'sidebar-accent': 'oklch(0.97 0 0)',
		'sidebar-accent-foreground': 'oklch(0.205 0 0)',
		'sidebar-border': 'oklch(0.922 0 0)',
		'sidebar-ring': 'oklch(0.708 0 0)',
		'glow': 'oklch(0.76 0.17 58)',
		'code': 'oklch(0.975 0 0)',
		'tone-green': 'oklch(0.596 0.145 163.225)',
		'tone-yellow': 'oklch(0.554 0.135 66.442)',
		'tone-amber': 'oklch(0.666 0.179 58.318)',
		'tone-violet': 'oklch(0.541 0.281 293.009)',
		'tone-sky': 'oklch(0.588 0.158 241.966)',
		'tone-rose': 'oklch(0.586 0.253 17.585)',
		'tone-teal': 'oklch(0.6 0.118 184.704)',
	},
	pinned: [],
	palette: [],
	radius: '0.625rem',
	shadowFloat: '0 0 28px 2px rgb(0 0 0 / 0.14)',
}

/** The themes that ship with Themis. They cannot be edited or deleted; duplicate one to make it your own. */
export const builtinThemes: readonly Theme[] = [themisDefault, themisLight]
export const DEFAULT_THEME_ID = themisDefault.id

export const isBuiltinTheme = (id: string) => builtinThemes.some((theme) => theme.id === id)

export function findTheme(id: string | null | undefined, list: readonly Theme[] = builtinThemes): Theme | undefined {
	return list.find((theme) => theme.id === id)
}

// ---------- custom themes: the ones people make, kept in this browser (see appearance.ts) ----------

export const CUSTOM_ID_PREFIX = 'custom-'
export const MAX_THEME_NAME = 60

/** A theme's name as stored: trimmed and kept to a sensible length; empty is not a name. */
export const cleanThemeName = (name: string): string => name.trim().slice(0, MAX_THEME_NAME)

/** "Name copy", then "Name copy 2", ... the first that no theme in the list has yet */
export function uniqueThemeName(base: string, taken: readonly string[]): string {
	const names = new Set(taken.map((name) => name.toLowerCase()))
	const stem = cleanThemeName(`${base} copy`).slice(0, MAX_THEME_NAME - 5)
	let name = stem
	for (let n = 2; names.has(name.toLowerCase()); n++) name = `${stem} ${n}`
	return name
}

// ---------- the palette: colours saved with a theme to use again ----------

export interface PaletteColor {
	id: string
	name: string
	color: string
}

export const MAX_PALETTE = 20
export const MAX_PALETTE_NAME = 30

export const cleanPaletteName = (name: string): string => name.trim().slice(0, MAX_PALETTE_NAME)

export function newPaletteColor(color: string, name: string): PaletteColor {
	return { id: crypto.randomUUID().slice(0, 8), name: cleanPaletteName(name) || 'Colour', color: color.trim() }
}

/** A palette as it may be kept: real colours only, named, no repeated ids, at most MAX_PALETTE of them */
export function cleanPalette(list: unknown): PaletteColor[] {
	if (!Array.isArray(list)) return []
	const palette: PaletteColor[] = []
	for (const item of list) {
		if (!item || typeof item !== 'object') continue
		const { id, name, color } = item as Record<string, unknown>
		if (typeof id !== 'string' || !id || typeof color !== 'string' || !isColor(color) || palette.some((entry) => entry.id === id)) continue
		palette.push({ id, name: typeof name === 'string' && cleanPaletteName(name) ? cleanPaletteName(name) : 'Colour', color: color.trim() })
		if (palette.length === MAX_PALETTE) break
	}
	return palette
}

/** A new custom theme that starts as a copy of `source`: its own id and name, the same colours, shape and palette. What
 *  the formulas of themeColors.ts cannot reproduce stays pinned, so the copy looks exactly like its source and the rest of it
 *  follows when a main colour is changed. */
export function duplicateTheme(source: Theme, name: string): Theme {
	return {
		id: `${CUSTOM_ID_PREFIX}${crypto.randomUUID().slice(0, 8)}`,
		name: cleanThemeName(name) || 'Custom theme',
		description: 'A custom theme.',
		mode: source.mode,
		colors: { ...source.colors },
		pinned: pinnedColors(source.mode, source.colors),
		palette: source.palette.map((entry) => ({ ...entry })),
		radius: source.radius,
		shadowFloat: source.shadowFloat,
	}
}

/** What the editor may change about a custom theme. Colours are given by token and merged into the theme's own: setting a
 *  derived colour pins it, `follow` lets pinned colours follow the main colours again. */
export type ThemeEdit = Partial<Pick<Theme, 'name' | 'mode' | 'radius' | 'shadowFloat' | 'palette'>> & {
	colors?: Partial<Record<ColorToken, string>>
	follow?: DerivedToken[]
}

/** The theme after an edit, with the colours that follow re-derived (so changing the page colour, the primary colour or the
 *  light/dark surface moves everything that is built from it) */
export function editTheme(theme: Theme, edit: ThemeEdit): Theme {
	const mode = edit.mode ?? theme.mode
	const pinned = new Set(theme.pinned)
	for (const token of Object.keys(edit.colors ?? {}) as ColorToken[]) if ((DERIVED_TOKENS as readonly string[]).includes(token)) pinned.add(token as DerivedToken)
	for (const token of edit.follow ?? []) pinned.delete(token)
	const pins = [...pinned]
	return {
		...theme,
		name: edit.name === undefined ? theme.name : cleanThemeName(edit.name) || theme.name,
		mode,
		colors: resolveColors(mode, { ...theme.colors, ...edit.colors }, pins),
		pinned: pins,
		palette: edit.palette === undefined ? theme.palette : cleanPalette(edit.palette),
		radius: edit.radius ?? theme.radius,
		shadowFloat: edit.shadowFloat ?? theme.shadowFloat,
	}
}

/** Custom themes read back from browser storage. Whatever is not usable is dropped or filled in rather than trusted:
 *  a token the stored theme lacks (one added to Themis since it was saved) takes the built-in theme's value of the same
 *  mode, so an older saved theme keeps working after an update. A theme saved before colours could follow (no `pinned`)
 *  gets its pins worked out from its colours. */
export function parseCustomThemes(raw: unknown): Theme[] {
	if (!Array.isArray(raw)) return []
	const themes: Theme[] = []
	for (const item of raw) {
		if (!item || typeof item !== 'object') continue
		const { id, name, mode, colors, pinned, palette, radius, shadowFloat } = item as Record<string, unknown>
		if (typeof id !== 'string' || !id.startsWith(CUSTOM_ID_PREFIX) || themes.some((theme) => theme.id === id)) continue
		if (mode !== 'light' && mode !== 'dark') continue
		const base = builtinThemes.find((theme) => theme.mode === mode) ?? themisDefault
		const stored = colors && typeof colors === 'object' ? (colors as Record<string, unknown>) : {}
		const filled = { ...base.colors }
		for (const token of COLOR_TOKENS) if (typeof stored[token] === 'string' && stored[token]) filled[token] = stored[token] as string
		themes.push({
			id,
			name: typeof name === 'string' && cleanThemeName(name) ? cleanThemeName(name) : 'Custom theme',
			description: 'A custom theme.',
			mode,
			colors: filled,
			pinned: Array.isArray(pinned) ? DERIVED_TOKENS.filter((token) => pinned.includes(token)) : pinnedColors(mode, filled),
			palette: cleanPalette(palette),
			radius: typeof radius === 'string' && radius ? radius : base.radius,
			shadowFloat: typeof shadowFloat === 'string' && shadowFloat ? shadowFloat : base.shadowFloat,
		})
	}
	return themes
}

/** the corner radius in rem, for a slider; a radius written in other units reads as the default 0.625 */
export const radiusRem = (radius: string): number => (radius.trim().endsWith('rem') && Number.isFinite(parseFloat(radius)) ? parseFloat(radius) : 0.625)
export const radiusFromRem = (rem: number): string => `${Number(rem.toFixed(3))}rem`

const FLOAT_SHADOW = /^0 0 28px 2px rgb\(0 0 0 \/ ([0-9.]+)\)$/
/** how dark the float shadow is (0 to 1), or null for a shadow the slider does not describe (the editor then leaves it be) */
export function shadowStrength(shadow: string): number | null {
	const match = FLOAT_SHADOW.exec(shadow.trim())
	return match ? Number(match[1]) : null
}
export const shadowFromStrength = (strength: number): string => `0 0 28px 2px rgb(0 0 0 / ${Number(strength.toFixed(2))})`

/** The CSS variables a theme sets on the page, by property name. This is the single place that maps a theme onto the
 *  stylesheet: app.css reads these names and nothing else describes a theme's values. */
export function themeVariables(theme: Theme): Record<string, string> {
	const variables: Record<string, string> = { '--radius': theme.radius, '--shadow-float': theme.shadowFloat }
	for (const token of COLOR_TOKENS) variables[`--${token}`] = theme.colors[token]
	return variables
}
