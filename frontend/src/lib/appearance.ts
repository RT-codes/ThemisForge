import { writable } from 'svelte/store'

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
	try {
		const saved = localStorage.getItem(STORAGE_KEY)
		if (isAppearancePreset(saved)) preset = saved
	} catch {
		// Appearance still works for this session if browser storage is unavailable.
	}
	apply(preset)
}

export function setAppearance(preset: AppearancePreset) {
	apply(preset)
	try {
		localStorage.setItem(STORAGE_KEY, preset)
	} catch {
		// Keep the current selection for this session if browser storage is unavailable.
	}
}
