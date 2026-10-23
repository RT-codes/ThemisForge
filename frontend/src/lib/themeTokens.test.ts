import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'

// Components colour themselves with theme tokens (bg-card, text-tone-green, ...), so a theme can recolour them. A raw
// Tailwind palette class (text-emerald-400) or a hand-written colour would stay the same on every theme.
const PALETTE = /\b(?:[a-z-]+:)*(?:text|bg|border|ring|from|to|via|outline|fill|stroke|divide|shadow|decoration|accent|caret)-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|slate|gray|zinc|neutral|stone)-\d{2,3}\b/

function sources(dir: string): string[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const path = join(dir, entry.name)
		if (entry.isDirectory()) return entry.name === 'ui' ? [] : sources(path) // ui/ is generated shadcn code
		return /\.(svelte|ts)$/.test(entry.name) && !entry.name.endsWith('.test.ts') ? [path] : []
	})
}

test('no component names a raw palette colour', () => {
	const offenders = sources(new URL('.', import.meta.url).pathname).filter((file) => PALETTE.test(readFileSync(file, 'utf8')))
	assert.deepEqual(offenders, [])
})
