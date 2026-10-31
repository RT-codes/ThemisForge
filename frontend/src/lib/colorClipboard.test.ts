import assert from 'node:assert/strict'
import { test, type TestContext } from 'node:test'
import { get } from 'svelte/store'
import { copiedColour, copyColour, pasteColour } from './colorClipboard.ts'

function clipboard(t: TestContext, system: { text: string; fail?: boolean }) {
	const original = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
	Object.defineProperty(globalThis, 'navigator', {
		configurable: true,
		value: {
			clipboard: {
				writeText: async (text: string) => { if (system.fail) throw new Error('denied'); system.text = text },
				readText: async () => { if (system.fail) throw new Error('denied'); return system.text },
			},
		},
	})
	t.after(() => {
		if (original) Object.defineProperty(globalThis, 'navigator', original)
		else Reflect.deleteProperty(globalThis, 'navigator')
	})
	copiedColour.set(null)
}

test('a copy goes to the system clipboard and is remembered', async (t) => {
	const system = { text: '' }
	clipboard(t, system)
	await copyColour('oklch(0.5 0.1 200)')
	assert.equal(system.text, 'oklch(0.5 0.1 200)')
	assert.equal(get(copiedColour), 'oklch(0.5 0.1 200)')
})

test('paste takes a colour from the system clipboard, else the one copied here, else nothing', async (t) => {
	const system = { text: ' #abc ' }
	clipboard(t, system)
	assert.equal(await pasteColour(), '#abc')
	system.text = 'some words'
	assert.equal(await pasteColour(), null)
	copiedColour.set('oklch(0.1 0.1 10)')
	assert.equal(await pasteColour(), 'oklch(0.1 0.1 10)')
	copiedColour.set('nonsense')
	assert.equal(await pasteColour(), null)
})

test('without clipboard access copy and paste still work inside Themis', async (t) => {
	clipboard(t, { text: '', fail: true })
	await copyColour('#123456')
	assert.equal(await pasteColour(), '#123456')
})
