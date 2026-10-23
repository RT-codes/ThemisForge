// Themes: every colour and shape token the interface reads, as data. A theme is written to the page as CSS variables
// (see applyTheme in appearance.ts), so components never name a colour: they use the Tailwind utilities that sit on
// these variables (bg-card, text-tone-green, ...), and a new theme is one more object here.
//
// Fonts and text scale are a separate axis (the typography presets in appearance.ts), so any theme can be combined
// with any typography.
//
// To add a theme: write one more Theme object below (every token in COLOR_TOKENS is required, and the type checker and
// the test in appearance.test.ts say which is missing) and add it to `themes`. The picker in Settings lists it from
// there. Colours go through Tailwind's `@theme inline` block in app.css; a new token needs a `--color-*` line there too.

export type ThemeMode = 'light' | 'dark'

/** The shadcn tokens every component is built on. The names are the CSS variables without their leading `--`. */
const SURFACE_TOKENS = [
	'background', 'foreground', 'card', 'card-foreground', 'popover', 'popover-foreground',
	'primary', 'primary-foreground', 'secondary', 'secondary-foreground', 'muted', 'muted-foreground',
	'accent', 'accent-foreground', 'destructive', 'border', 'input', 'ring',
	'chart-1', 'chart-2', 'chart-3', 'chart-4', 'chart-5',
	'sidebar', 'sidebar-foreground', 'sidebar-primary', 'sidebar-primary-foreground',
	'sidebar-accent', 'sidebar-accent-foreground', 'sidebar-border', 'sidebar-ring',
] as const

/** `glow` is the brand accent: the glow of cards, the minimap edge and other flourishes. It is separate from `primary`
 *  because primary is near black on the light theme while the brand stays orange. `code` is the surface of code blocks
 *  (in the documentation), which sits a step away from the page on either mode. */
const EXTRA_TOKENS = ['glow', 'code'] as const

/** Colours that carry meaning in the interface (done is green, running is violet, attention is yellow, ...). Each is
 *  one colour per theme, used as text, as a dot, or as a wash and border by mixing it with transparency
 *  (`bg-tone-green/15`), so it must be strong enough to read as text on the theme's own surfaces. */
export const TONES = ['green', 'yellow', 'amber', 'violet', 'sky', 'rose', 'teal'] as const
export type Tone = (typeof TONES)[number]
const TONE_TOKENS = TONES.map((tone) => `tone-${tone}` as const)

export const COLOR_TOKENS = [...SURFACE_TOKENS, ...EXTRA_TOKENS, ...TONE_TOKENS] as const
export type ColorToken = (typeof COLOR_TOKENS)[number]

export interface Theme {
	id: string
	name: string
	description: string
	/** whether the theme sits on a dark or a light surface: decides the `dark` class, the browser's own widgets
	 *  (scrollbars, date pickers) and the colour mode of embedded libraries */
	mode: ThemeMode
	colors: Record<ColorToken, string>
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
	radius: '0.625rem',
	shadowFloat: '0 0 28px 2px rgb(0 0 0 / 0.14)',
}

export const themes: readonly Theme[] = [themisDefault, themisLight]
export const DEFAULT_THEME_ID = themisDefault.id

export function findTheme(id: string | null | undefined): Theme | undefined {
	return themes.find((theme) => theme.id === id)
}

/** The CSS variables a theme sets on the page, by property name. This is the single place that maps a theme onto the
 *  stylesheet: app.css reads these names and nothing else describes a theme's values. */
export function themeVariables(theme: Theme): Record<string, string> {
	const variables: Record<string, string> = { '--radius': theme.radius, '--shadow-float': theme.shadowFloat }
	for (const token of COLOR_TOKENS) variables[`--${token}`] = theme.colors[token]
	return variables
}
