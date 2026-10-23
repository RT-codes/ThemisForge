// How a theme's colours relate to each other. A theme only needs a handful of MAIN colours (the page, the text, the
// primary colour, the brand glow and the meaning colours); every other token is DERIVED from them (cards a step lighter
// than the page, borders a faint line of the text colour, ...) unless a person has set it by hand, which pins it. The
// editor edits mains and shows the derived colours folded away; changing a main colour (or the theme's light or dark
// surface) re-derives whatever is not pinned. All of it is pure, so it can be tested without a browser.

import { colorDistance, formatOklch, mixColors, parseColor, type Oklch } from './colors.ts'

export type ThemeMode = 'light' | 'dark'

/** Colours that carry meaning in the interface (done is green, running is violet, attention is yellow, ...). Each is
 *  one colour per theme, used as text, as a dot, or as a wash and border by mixing it with transparency
 *  (`bg-tone-green/15`), so it must be strong enough to read as text on the theme's own surfaces. */
export const TONES = ['green', 'yellow', 'amber', 'violet', 'sky', 'rose', 'teal'] as const
export type Tone = (typeof TONES)[number]
const TONE_TOKENS = TONES.map((tone) => `tone-${tone}` as const)

/** The colours a person chooses. `glow` is the brand accent (the glow of cards, the minimap edge): it is separate from
 *  `primary` because primary is near black on the light theme while the brand stays orange. */
export const MAIN_TOKENS = ['background', 'foreground', 'primary', 'primary-foreground', 'glow', 'destructive', ...TONE_TOKENS] as const
export type MainToken = (typeof MAIN_TOKENS)[number]

/** Everything else the stylesheet reads; each follows from the main colours. */
export const DERIVED_TOKENS = [
	'card', 'card-foreground', 'popover', 'popover-foreground', 'secondary', 'secondary-foreground', 'muted', 'muted-foreground',
	'accent', 'accent-foreground', 'border', 'input', 'ring', 'code',
	'sidebar', 'sidebar-foreground', 'sidebar-primary', 'sidebar-primary-foreground', 'sidebar-accent', 'sidebar-accent-foreground',
	'sidebar-border', 'sidebar-ring',
	'chart-1', 'chart-2', 'chart-3', 'chart-4', 'chart-5',
] as const
export type DerivedToken = (typeof DERIVED_TOKENS)[number]

export const COLOR_TOKENS = [...MAIN_TOKENS, ...DERIVED_TOKENS] as const
export type ColorToken = (typeof COLOR_TOKENS)[number]

export const isMainToken = (token: ColorToken): token is MainToken => (MAIN_TOKENS as readonly string[]).includes(token)

/** What `splitColors` and the editor treat as the same colour: closer than a person can tell apart */
const SAME = 0.012

/** The derived colours for the given main colours. The numbers are the steps of the Themis themes, so a theme made of
 *  Themis Default's mains comes out as Themis Default: on dark surfaces layers get lighter and lines are a faint wash of
 *  the text colour; on light surfaces layers get a touch darker and lines are a solid grey. Returns null when a main
 *  colour is not a colour the editor can read. */
export function deriveColors(mode: ThemeMode, main: Record<MainToken, string>): Record<DerivedToken, string> | null {
	const page = parseColor(main.background)
	const text = parseColor(main.foreground)
	const primary = parseColor(main.primary)
	const onPrimary = parseColor(main['primary-foreground'])
	const glow = parseColor(main.glow)
	if (!page || !text || !primary || !onPrimary || !glow) return null
	const dark = mode === 'dark'
	// a step from the page towards the text colour
	const step = (darkStep: number, lightStep: number) => mixColors(page, text, dark ? darkStep : lightStep)
	const alpha = (c: Oklch, a: number): Oklch => ({ ...c, alpha: a })
	// a line: a faint wash of white on dark surfaces (it works on any layer), a solid step towards the text on light ones
	const line = (strength: number) => (dark ? { l: 1, c: 0, h: 0, alpha: strength } : step(0, strength))

	const card = step(0.055, 0)
	const muted = step(0.127, 0.035)
	const quietText = mixColors(text, page, dark ? 0.327 : 0.48)
	const onSurface = mixColors(text, page, dark ? 0 : 0.07) // the text on a muted or hovered surface
	// a hover picks up a hint of the brand on dark surfaces; on light ones it stays a plain grey, where the tint would show
	const hover = dark ? mixColors(muted, glow, 0.05) : muted
	const sidebarHover = dark ? mixColors(muted, { ...glow, l: muted.l }, 0.045) : muted
	const ring = dark ? alpha(primary, 0.6) : mixColors(primary, page, 0.62)
	// charts step from the primary colour towards the page
	const chart = (n: number) => mixColors(primary, page, 0.17 * n)

	const colors: Record<DerivedToken, Oklch> = {
		card,
		'card-foreground': text,
		popover: card,
		'popover-foreground': text,
		secondary: muted,
		'secondary-foreground': onSurface,
		muted,
		'muted-foreground': quietText,
		accent: hover,
		'accent-foreground': onSurface,
		border: line(dark ? 0.09 : 0.091),
		input: line(dark ? 0.13 : 0.091),
		ring,
		code: step(dark ? -0.03 : 0.029, 0.029),
		sidebar: step(0.035, 0.0175),
		'sidebar-foreground': text,
		'sidebar-primary': primary,
		'sidebar-primary-foreground': onPrimary,
		'sidebar-accent': sidebarHover,
		'sidebar-accent-foreground': onSurface,
		'sidebar-border': line(dark ? 0.08 : 0.091),
		'sidebar-ring': ring,
		'chart-1': chart(0),
		'chart-2': chart(1),
		'chart-3': chart(2),
		'chart-4': chart(3),
		'chart-5': chart(4),
	}
	return Object.fromEntries(DERIVED_TOKENS.map((token) => [token, formatOklch(colors[token])])) as Record<DerivedToken, string>
}

/** Full colours with the derived ones refreshed: every derived token that is not pinned takes the value that follows from
 *  the mains, and pinned ones keep theirs. A theme with unreadable mains is returned as it is. */
export function resolveColors(mode: ThemeMode, colors: Record<ColorToken, string>, pinned: readonly DerivedToken[]): Record<ColorToken, string> {
	const derived = deriveColors(mode, colors)
	if (!derived) return colors
	const next = { ...colors }
	for (const token of DERIVED_TOKENS) if (!pinned.includes(token)) next[token] = derived[token]
	return next
}

/** Which derived colours of a finished set of colours are hand-made: the ones that differ visibly from what the mains
 *  give. This is how a copy of a built-in theme (or an older saved one) starts out: what the formulas reproduce follows
 *  the mains, and the few colours they cannot reproduce stay as they are until the person lets them follow. */
export function pinnedColors(mode: ThemeMode, colors: Record<ColorToken, string>): DerivedToken[] {
	const derived = deriveColors(mode, colors)
	if (!derived) return [...DERIVED_TOKENS]
	return DERIVED_TOKENS.filter((token) => {
		if (token.startsWith('chart-')) return false // no screen uses the chart colours, so they just follow
		const actual = parseColor(colors[token])
		const expected = parseColor(derived[token])
		return !actual || !expected || colorDistance(actual, expected) > SAME
	})
}

// ---------- what the editor shows ----------

export interface ColorEntry {
	token: ColorToken
	label: string
	/** where the colour shows up, in a few words */
	hint: string
}

export interface EditorSection {
	title: string
	description: string
	/** the colours to choose */
	main: ColorEntry[]
	/** the colours that follow from them, in folded groups */
	followers: { title: string; entries: ColorEntry[] }[]
}

export const EDITOR_SECTIONS: EditorSection[] = [
	{
		title: 'Page and text',
		description: 'The two colours everything else is built from. Cards, menus, borders and quiet text are shades of these.',
		main: [
			{ token: 'background', label: 'Page', hint: 'Behind everything' },
			{ token: 'foreground', label: 'Text', hint: 'Headings and body text' },
		],
		followers: [
			{
				title: 'Cards and menus',
				entries: [
					{ token: 'card', label: 'Cards', hint: 'Panels and boxes' },
					{ token: 'card-foreground', label: 'Card text', hint: 'Text on cards' },
					{ token: 'popover', label: 'Menus and dialogs', hint: 'What floats above the page' },
					{ token: 'popover-foreground', label: 'Menu text', hint: 'Text in menus and dialogs' },
					{ token: 'code', label: 'Code blocks', hint: 'Logs and code in the docs' },
				],
			},
			{
				title: 'Sidebar',
				entries: [
					{ token: 'sidebar', label: 'Sidebar', hint: 'The navigation on the left' },
					{ token: 'sidebar-foreground', label: 'Sidebar text', hint: 'Its links and labels' },
					{ token: 'sidebar-border', label: 'Sidebar lines', hint: 'Its dividers and tree lines' },
				],
			},
			{
				title: 'Quiet surfaces',
				entries: [
					{ token: 'muted', label: 'Muted', hint: 'Tabs, badges and subdued backgrounds' },
					{ token: 'muted-foreground', label: 'Muted text', hint: 'Descriptions and hints' },
					{ token: 'secondary', label: 'Secondary', hint: 'Secondary buttons' },
					{ token: 'secondary-foreground', label: 'Secondary text', hint: 'Text on secondary buttons' },
				],
			},
			{
				title: 'Lines',
				entries: [
					{ token: 'border', label: 'Borders', hint: 'Dividers and the edges of cards' },
					{ token: 'input', label: 'Field borders', hint: 'The edges of inputs and buttons' },
				],
			},
			{
				title: 'Hover and selection',
				entries: [
					{ token: 'accent', label: 'Hover', hint: 'A row or button under the pointer' },
					{ token: 'accent-foreground', label: 'Hover text', hint: 'Text on a hovered row' },
					{ token: 'sidebar-accent', label: 'Sidebar hover', hint: 'A sidebar link under the pointer, or the current one' },
					{ token: 'sidebar-accent-foreground', label: 'Sidebar hover text', hint: 'Its text' },
				],
			},
		],
	},
	{
		title: 'Primary and brand',
		description: 'The colour of the main actions, and the brand glow that lights up cards and pages.',
		main: [
			{ token: 'primary', label: 'Primary', hint: 'Main buttons, links and active items' },
			{ token: 'primary-foreground', label: 'Text on primary', hint: 'Text and icons on a primary button' },
			{ token: 'glow', label: 'Brand glow', hint: 'The soft light on cards and pages' },
		],
		followers: [
			{
				title: 'Focus and sidebar',
				entries: [
					{ token: 'ring', label: 'Focus ring', hint: 'The outline of the field you are in' },
					{ token: 'sidebar-ring', label: 'Sidebar focus ring', hint: 'The same, in the sidebar' },
					{ token: 'sidebar-primary', label: 'Sidebar primary', hint: 'The sidebar button and its icons' },
					{ token: 'sidebar-primary-foreground', label: 'Text on sidebar primary', hint: 'Text on that button' },
				],
			},
		],
	},
	{
		title: 'Meaning colours',
		description: 'Colours that say what something is. Each also becomes a soft wash behind its text, so keep it readable on the page.',
		main: [
			{ token: 'destructive', label: 'Errors and failures', hint: 'Failed tasks, delete buttons' },
			{ token: 'tone-green', label: 'Done and good', hint: 'Finished tasks, connected' },
			{ token: 'tone-yellow', label: 'Warnings', hint: 'Notices that need a look' },
			{ token: 'tone-amber', label: 'Attention and time', hint: 'Approvals, schedules' },
			{ token: 'tone-violet', label: 'Review and running', hint: 'Tasks to review' },
			{ token: 'tone-sky', label: 'Ready and structure', hint: 'Ready tasks, structure' },
			{ token: 'tone-rose', label: 'Upcoming', hint: 'What is coming next' },
			{ token: 'tone-teal', label: 'Folders', hint: 'Shared folders in workflows' },
		],
		followers: [],
	},
]
