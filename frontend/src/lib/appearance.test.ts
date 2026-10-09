import assert from 'node:assert/strict'
import { test, type TestContext } from 'node:test'
import { get } from 'svelte/store'
import { appearance, appearancePresets, initializeAppearance, setAppearance } from './appearance.ts'

function browser(t: TestContext, saved: string | null = null) {
	const values = new Map<string, string>()
	if (saved !== null) values.set('themis.appearance', saved)
	const dataset: Record<string, string> = {}
	const storage = {
		getItem: (key: string) => values.get(key) ?? null,
		setItem: (key: string, value: string) => { values.set(key, value) },
	}
	for (const [key, value] of Object.entries({ document: { documentElement: { dataset } }, localStorage: storage })) {
		const original = Object.getOwnPropertyDescriptor(globalThis, key)
		Object.defineProperty(globalThis, key, { configurable: true, value })
		t.after(() => {
			if (original) Object.defineProperty(globalThis, key, original)
			else Reflect.deleteProperty(globalThis, key)
		})
	}
	return { dataset, storage, values }
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
