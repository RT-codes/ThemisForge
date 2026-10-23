import assert from 'node:assert/strict'
import { test, type TestContext } from 'node:test'
import { get } from 'svelte/store'
import {
	allThemes, appearance, appearancePresets, customThemes, deleteTheme, duplicateThemeOf, initializeAppearance, setAppearance,
	setTheme, theme, themeMode, updateTheme,
} from './appearance.ts'
import { builtinThemes, COLOR_TOKENS, DEFAULT_THEME_ID, findTheme, parseCustomThemes, radiusFromRem, radiusRem, shadowFromStrength, shadowStrength, THEME_COLOR_GROUPS, themeVariables, uniqueThemeName } from './themes.ts'

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
	assert.equal(new Set(builtinThemes.map((choice) => choice.id)).size, builtinThemes.length)
	assert.ok(findTheme(DEFAULT_THEME_ID))
	for (const choice of builtinThemes) {
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

test('a duplicate is a new custom theme with its own name, saved but not switched to', (t) => {
	const { values, dataset } = browser(t)
	customThemes.set([])
	initializeAppearance()
	const copy = duplicateThemeOf('themis-default')
	assert.ok(copy?.id.startsWith('custom-'))
	assert.equal(copy?.name, 'Themis Default copy')
	assert.deepEqual(copy?.colors, findTheme('themis-default')?.colors)
	assert.equal(dataset.theme, 'themis-default')
	assert.equal(get(allThemes).length, builtinThemes.length + 1)
	assert.equal(duplicateThemeOf('themis-default')?.name, 'Themis Default copy 2')
	assert.equal(JSON.parse(values.get('themis.themes') ?? '[]').length, 2)
	assert.equal(duplicateThemeOf('missing'), null)
})

test('editing a custom theme in use changes the page at once and is saved', (t) => {
	const { style, classes, values } = browser(t)
	customThemes.set([])
	initializeAppearance()
	const copy = duplicateThemeOf('themis-default')!
	setTheme(copy.id)
	updateTheme(copy.id, { name: '  Mine  ', colors: { primary: 'oklch(0.7 0.2 150)' }, radius: '1rem', mode: 'light' })
	assert.equal(style.properties.get('--primary'), 'oklch(0.7 0.2 150)')
	assert.equal(style.properties.get('--radius'), '1rem')
	assert.equal(style.properties.get('--background'), copy.colors.background) // the rest is untouched
	assert.ok(!classes.has('dark'))
	assert.equal(get(themeMode), 'light')
	const saved = JSON.parse(values.get('themis.themes') ?? '[]')[0]
	assert.equal(saved.name, 'Mine')
	assert.equal(saved.colors.primary, 'oklch(0.7 0.2 150)')
	assert.equal(JSON.parse(values.get('themis.theme-cache') ?? '{}').variables['--primary'], 'oklch(0.7 0.2 150)')
	updateTheme(copy.id, { name: '   ' }) // an empty name keeps the old one
	assert.equal(get(customThemes)[0].name, 'Mine')
})

test('built-in themes cannot be edited or deleted', (t) => {
	const { style } = browser(t)
	customThemes.set([])
	initializeAppearance()
	updateTheme('themis-default', { colors: { primary: 'red' } })
	assert.equal(style.properties.get('--primary'), findTheme('themis-default')?.colors.primary)
	deleteTheme('themis-default')
	assert.equal(get(theme), 'themis-default')
	assert.ok(findTheme('themis-default'))
})

test('custom themes survive a reload, and deleting the one in use falls back to the default', (t) => {
	const { dataset } = browser(t)
	customThemes.set([])
	initializeAppearance()
	const copy = duplicateThemeOf('themis-light')!
	setTheme(copy.id)
	customThemes.set([])
	initializeAppearance()
	assert.equal(get(theme), copy.id)
	assert.equal(dataset.theme, copy.id)
	deleteTheme(copy.id)
	assert.equal(dataset.theme, DEFAULT_THEME_ID)
	assert.equal(get(customThemes).length, 0)
})

test('stored custom themes are read defensively and missing tokens are filled in', () => {
	const parsed = parseCustomThemes([
		{ id: 'custom-a', name: 'Old', mode: 'dark', colors: { primary: 'red', glow: 5 } },
		{ id: 'custom-a', name: 'Duplicate id', mode: 'dark', colors: {} },
		{ id: 'themis-default', name: 'Pretends to be built in', mode: 'dark', colors: {} },
		{ id: 'custom-b', name: 'Bad mode', mode: 'sepia', colors: {} },
		'nonsense',
		{ id: 'custom-c', name: '', mode: 'light' },
	])
	assert.deepEqual(parsed.map((theme) => theme.id), ['custom-a', 'custom-c'])
	assert.equal(parsed[0].colors.primary, 'red')
	assert.equal(parsed[0].colors.glow, findTheme('themis-default')?.colors.glow) // not a string: the base value
	for (const token of COLOR_TOKENS) assert.ok(parsed[1].colors[token], token)
	assert.equal(parsed[1].name, 'Custom theme')
	assert.equal(parsed[1].colors.background, findTheme('themis-light')?.colors.background)
	assert.deepEqual(parseCustomThemes('{bad'), [])
})

test('copy names count up until they are unique', () => {
	assert.equal(uniqueThemeName('Mine', []), 'Mine copy')
	assert.equal(uniqueThemeName('Mine', ['mine copy']), 'Mine copy 2')
	assert.equal(uniqueThemeName('Mine', ['Mine copy', 'Mine copy 2']), 'Mine copy 3')
})

test('the editor lists every colour token once', () => {
	const listed = THEME_COLOR_GROUPS.flatMap((group) => group.tokens.map((entry) => entry.token))
	assert.deepEqual([...listed].sort(), [...COLOR_TOKENS].sort())
})

test('radius and float shadow convert to slider numbers and back', () => {
	assert.equal(radiusRem('0.625rem'), 0.625)
	assert.equal(radiusRem('10px'), 0.625)
	assert.equal(radiusFromRem(1.0250000001), '1.025rem')
	for (const choice of builtinThemes) {
		const strength = shadowStrength(choice.shadowFloat)
		assert.ok(strength !== null && strength > 0, choice.id)
		assert.equal(shadowFromStrength(strength), choice.shadowFloat)
	}
	assert.equal(shadowStrength('0 4px 8px red'), null)
})
