import assert from 'node:assert/strict'
import { test, type TestContext } from 'node:test'
import { get } from 'svelte/store'
import { appearance, appearancePresets, initializeAppearance, setAppearance, setTheme, theme } from './appearance.ts'
import { COLOR_TOKENS, DEFAULT_THEME_ID, findTheme, themeVariables, themes } from './themes.ts'

function browser(t: TestContext, saved: string | null = null) {
	const values = new Map<string, string>()
	if (saved !== null) values.set('themis.appearance', saved)
	const dataset: Record<string, string> = {}
	const style = { colorScheme: '', properties: new Map<string, string>(), setProperty(name: string, value: string) { this.properties.set(name, value) } }
	const classes = new Set<string>()
	const classList = { toggle: (name: string, on: boolean) => (on ? classes.add(name) : classes.delete(name)) }
	const storage = {
		getItem: (key: string) => values.get(key) ?? null,
		setItem: (key: string, value: string) => { values.set(key, value) },
	}
	for (const [key, value] of Object.entries({ document: { documentElement: { dataset, style, classList } }, localStorage: storage })) {
		const original = Object.getOwnPropertyDescriptor(globalThis, key)
		Object.defineProperty(globalThis, key, { configurable: true, value })
		t.after(() => {
			if (original) Object.defineProperty(globalThis, key, original)
			else Reflect.deleteProperty(globalThis, key)
		})
	}
	return { dataset, storage, values, style, classes }
}

test('restores each supported preset before mounting the app', (t) => {
	const { dataset, values } = browser(t)
	for (const preset of appearancePresets) {
		values.set('themis.appearance', preset.id)
		initializeAppearance()
		assert.equal(dataset.appearance, preset.id)
		assert.equal(get(appearance), preset.id)
	}
})

test('missing or invalid stored preferences fall back to Compact', (t) => {
	const { dataset, values } = browser(t)
	for (const saved of [null, '', 'unknown', '{bad json}']) {
		if (saved === null) values.delete('themis.appearance')
		else values.set('themis.appearance', saved)
		initializeAppearance()
		assert.equal(dataset.appearance, 'compact')
		assert.equal(get(appearance), 'compact')
	}
})

test('selection updates the root and store, persists, and survives reload', (t) => {
	const { dataset, values } = browser(t)
	initializeAppearance()
	for (const preset of appearancePresets) {
		setAppearance(preset.id)
		assert.equal(dataset.appearance, preset.id)
		assert.equal(get(appearance), preset.id)
		assert.equal(values.get('themis.appearance'), preset.id)
		appearance.set('compact')
		initializeAppearance()
		assert.equal(get(appearance), preset.id)
	}
})

test('blocked browser storage does not prevent initialization or changing appearance', (t) => {
	const { dataset, storage } = browser(t)
	t.mock.method(storage, 'getItem', () => { throw new Error('Storage blocked') })
	t.mock.method(storage, 'setItem', () => { throw new Error('Storage blocked') })
	initializeAppearance()
	assert.equal(dataset.appearance, 'compact')
	setAppearance('technical')
	assert.equal(dataset.appearance, 'technical')
	assert.equal(get(appearance), 'technical')
})

test('every theme sets every token, with a mode and a unique id', () => {
	assert.equal(new Set(themes.map((choice) => choice.id)).size, themes.length)
	assert.ok(findTheme(DEFAULT_THEME_ID))
	for (const choice of themes) {
		assert.ok(choice.mode === 'dark' || choice.mode === 'light', choice.id)
		for (const token of COLOR_TOKENS) assert.ok(choice.colors[token], `${choice.id} lacks ${token}`)
		const variables = themeVariables(choice)
		assert.equal(Object.keys(variables).length, COLOR_TOKENS.length + 2)
		assert.equal(variables['--primary'], choice.colors.primary)
	}
})

test('a first visit applies the default dark theme', (t) => {
	const { dataset, style, classes } = browser(t)
	initializeAppearance()
	assert.equal(get(theme), DEFAULT_THEME_ID)
	assert.equal(dataset.theme, DEFAULT_THEME_ID)
	assert.ok(classes.has('dark'))
	assert.equal(style.colorScheme, 'dark')
	assert.equal(style.properties.get('--background'), findTheme(DEFAULT_THEME_ID)?.colors.background)
})

test('choosing a theme switches variables, mode and persists across reloads', (t) => {
	const { dataset, style, classes, values } = browser(t)
	initializeAppearance()
	setTheme('themis-light')
	assert.equal(dataset.theme, 'themis-light')
	assert.ok(!classes.has('dark'))
	assert.equal(style.colorScheme, 'light')
	assert.equal(style.properties.get('--background'), findTheme('themis-light')?.colors.background)
	assert.equal(values.get('themis.theme'), 'themis-light')
	// the cache the inline script in index.html reads
	const cache = JSON.parse(values.get('themis.theme-cache') ?? '{}')
	assert.equal(cache.mode, 'light')
	assert.equal(cache.variables['--primary'], findTheme('themis-light')?.colors.primary)
	theme.set(DEFAULT_THEME_ID)
	initializeAppearance()
	assert.equal(get(theme), 'themis-light')
	setTheme(DEFAULT_THEME_ID)
	assert.ok(classes.has('dark'))
})

test('an unknown stored theme falls back to the default, and the typography stays independent', (t) => {
	const { dataset, values } = browser(t)
	values.set('themis.theme', 'removed-theme')
	values.set('themis.appearance', 'technical')
	initializeAppearance()
	assert.equal(dataset.theme, DEFAULT_THEME_ID)
	assert.equal(dataset.appearance, 'technical')
	setTheme('themis-light')
	assert.equal(dataset.appearance, 'technical')
	setTheme('nonsense')
	assert.equal(dataset.theme, DEFAULT_THEME_ID)
})
