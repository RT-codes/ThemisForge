import { derived, writable } from 'svelte/store'
import { DEFAULT_THEME_ID, findTheme, themeVariables, themes, type Theme } from './themes.ts'

// Appearance is two independent choices, both kept in this browser: the theme (colours and shape, see themes.ts) and
// the typography preset (fonts and text scale, below).

export const appearancePresets = [
	{
		id: 'compact',
		name: 'Compact',
		font: 'Inter',
		description: 'The familiar, compact type scale.',
		previewFont: "'Inter Variable', sans-serif",
		previewMono: 'ui-monospace, monospace',
	},
	{
		id: 'crisp',
		name: 'Crisp',
		font: 'Geist',
		description: 'A clean geometric look with slightly more room.',
		previewFont: "'Geist Variable', sans-serif",
		previewMono: 'ui-monospace, monospace',
	},
	{
		id: 'technical',
		name: 'Technical',
		font: 'IBM Plex',
		description: 'IBM Plex Sans, with Mono for code and data.',
		previewFont: "'IBM Plex Sans Variable', sans-serif",
		previewMono: "'IBM Plex Mono', ui-monospace, monospace",
	},
] as const
export type AppearancePreset = (typeof appearancePresets)[number]['id']

const STORAGE_KEY = 'themis.appearance'
export const appearance = writable<AppearancePreset>('compact')

function isAppearancePreset(value: string | null): value is AppearancePreset {
	return appearancePresets.some((preset) => preset.id === value)
}

function apply(preset: AppearancePreset) {
	document.documentElement.dataset.appearance = preset
	appearance.set(preset)
}

export function initializeAppearance() {
	let preset: AppearancePreset = 'compact'
	let themeId = DEFAULT_THEME_ID
	try {
		const saved = localStorage.getItem(STORAGE_KEY)
		if (isAppearancePreset(saved)) preset = saved
		// An unknown id (a removed theme) falls back to the default instead of leaving the page unstyled.
		themeId = findTheme(localStorage.getItem(THEME_KEY))?.id ?? DEFAULT_THEME_ID
	} catch {
		// Appearance still works for this session if browser storage is unavailable.
	}
	apply(preset)
	applyTheme(findTheme(themeId) ?? themes[0])
}

export function setAppearance(preset: AppearancePreset) {
	apply(preset)
	try {
		localStorage.setItem(STORAGE_KEY, preset)
	} catch {
		// Keep the current selection for this session if browser storage is unavailable.
	}
}

const THEME_KEY = 'themis.theme'
// The applied theme's variables, kept so the inline script in index.html can paint the right colours before this
// module has loaded (otherwise a light theme would flash dark on every page load).
const THEME_CACHE_KEY = 'themis.theme-cache'
export const theme = writable<string>(DEFAULT_THEME_ID)
/** light or dark, for what must be told the colour mode (the workflow canvas) */
export const themeMode = derived(theme, (id) => (findTheme(id) ?? themes[0]).mode)

function applyTheme(chosen: Theme) {
	const root = document.documentElement
	const variables = themeVariables(chosen)
	for (const [name, value] of Object.entries(variables)) root.style.setProperty(name, value)
	// The `dark` class switches Tailwind's dark: variants; color-scheme switches the browser's own widgets.
	root.classList.toggle('dark', chosen.mode === 'dark')
	root.style.colorScheme = chosen.mode
	root.dataset.theme = chosen.id
	theme.set(chosen.id)
	try {
		localStorage.setItem(THEME_CACHE_KEY, JSON.stringify({ mode: chosen.mode, variables }))
	} catch {
		// The theme still applies; only the flash-free first paint is lost.
	}
}

export function setTheme(id: string) {
	const chosen = findTheme(id) ?? themes[0]
	applyTheme(chosen)
	try {
		localStorage.setItem(THEME_KEY, chosen.id)
	} catch {
		// Keep the current selection for this session if browser storage is unavailable.
	}
}
