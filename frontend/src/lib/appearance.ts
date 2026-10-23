import { derived, get, writable } from 'svelte/store'
import {
	builtinThemes, DEFAULT_THEME_ID, duplicateTheme, editTheme, findTheme, isBuiltinTheme, parseCustomThemes, themeVariables,
	uniqueThemeName, type Theme, type ThemeEdit,
} from './themes.ts'

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
		const stored = localStorage.getItem(CUSTOM_THEMES_KEY)
		customThemes.set(stored ? parseCustomThemes(JSON.parse(stored)) : [])
		themeId = localStorage.getItem(THEME_KEY) ?? DEFAULT_THEME_ID
	} catch {
		// Appearance still works for this session if browser storage is unavailable (or holds something unreadable).
		customThemes.set([])
	}
	apply(preset)
	// An unknown id (a removed theme) falls back to the default instead of leaving the page unstyled.
	applyTheme(lookup(themeId) ?? builtinThemes[0])
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
const CUSTOM_THEMES_KEY = 'themis.themes'
// The applied theme's variables, kept so the inline script in index.html can paint the right colours before this
// module has loaded (otherwise a light theme would flash dark on every page load).
const THEME_CACHE_KEY = 'themis.theme-cache'

/** The id of the theme in use */
export const theme = writable<string>(DEFAULT_THEME_ID)
/** The themes people made, kept in this browser. The built-in ones are in themes.ts and never change. */
export const customThemes = writable<Theme[]>([])
/** Every theme there is, the built-in ones first */
export const allThemes = derived(customThemes, (custom) => [...builtinThemes, ...custom])
/** light or dark, for what must be told the colour mode (the workflow canvas) */
export const themeMode = derived([theme, allThemes], ([id, list]) => (findTheme(id, list) ?? builtinThemes[0]).mode)

const lookup = (id: string) => findTheme(id, get(allThemes))

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
	const chosen = lookup(id) ?? builtinThemes[0]
	applyTheme(chosen)
	try {
		localStorage.setItem(THEME_KEY, chosen.id)
	} catch {
		// Keep the current selection for this session if browser storage is unavailable.
	}
}

/** True when the last attempt to keep the custom themes in this browser failed (storage blocked or full): the editor says so,
 *  because the themes then only last until the page is closed. */
export const themesSaveFailed = writable(false)

function saveCustomThemes(list: Theme[]) {
	customThemes.set(list)
	try {
		localStorage.setItem(CUSTOM_THEMES_KEY, JSON.stringify(list))
		themesSaveFailed.set(false)
	} catch {
		themesSaveFailed.set(true) // the themes stay for this session
	}
}

/** A new custom theme that starts as a copy of any theme, built-in or not. It is saved but not switched to. */
export function duplicateThemeOf(id: string): Theme | null {
	const source = lookup(id)
	if (!source) return null
	const copy = duplicateTheme(source, uniqueThemeName(source.name, get(allThemes).map((t) => t.name)))
	saveCustomThemes([...get(customThemes), copy])
	return copy
}

/** Edit a custom theme (the built-in ones are never edited). When it is the theme in use the page follows at once, which
 *  is what makes editing live. */
export function updateTheme(id: string, edit: ThemeEdit) {
	if (isBuiltinTheme(id)) return
	const current = get(customThemes).find((t) => t.id === id)
	if (!current) return
	const next = editTheme(current, edit)
	saveCustomThemes(get(customThemes).map((t) => (t.id === id ? next : t)))
	if (get(theme) === id) applyTheme(next)
}

/** Delete a custom theme; if it is the one in use the default takes its place. */
export function deleteTheme(id: string) {
	if (isBuiltinTheme(id)) return
	saveCustomThemes(get(customThemes).filter((t) => t.id !== id))
	if (get(theme) === id) setTheme(DEFAULT_THEME_ID)
}
