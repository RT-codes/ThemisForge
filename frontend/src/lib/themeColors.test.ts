import assert from 'node:assert/strict'
import { test } from 'node:test'
import { colorDistance, parseColor } from './colors.ts'
import { COLOR_TOKENS, DERIVED_TOKENS, deriveColors, EDITOR_SECTIONS, isMainToken, MAIN_TOKENS, pinnedColors, resolveColors } from './themeColors.ts'
import {
	builtinThemes, cleanPalette, duplicateTheme, editTheme, findTheme, MAX_PALETTE, newPaletteColor, parseCustomThemes, type Theme,
} from './themes.ts'

const themisDefault = findTheme('themis-default') as Theme
const themisLight = findTheme('themis-light') as Theme

test('main and derived colours together are every token, each once', () => {
	assert.equal(new Set(COLOR_TOKENS).size, COLOR_TOKENS.length)
	assert.equal(MAIN_TOKENS.length + DERIVED_TOKENS.length, COLOR_TOKENS.length)
	assert.ok(MAIN_TOKENS.every(isMainToken) && DERIVED_TOKENS.every((token) => !isMainToken(token)))
})

test('the editor shows every main colour, and every derived one but the unused charts, exactly once', () => {
	const shown = EDITOR_SECTIONS.flatMap((section) => [...section.main, ...section.followers.flatMap((group) => group.entries)]).map((entry) => entry.token)
	assert.equal(new Set(shown).size, shown.length)
	assert.deepEqual([...shown].sort(), COLOR_TOKENS.filter((token) => !token.startsWith('chart-')).sort())
	for (const section of EDITOR_SECTIONS) for (const entry of section.main) assert.ok(isMainToken(entry.token), entry.token)
	for (const section of EDITOR_SECTIONS) for (const group of section.followers) for (const entry of group.entries) assert.ok(!isMainToken(entry.token), entry.token)
})

test('the main colours of each built-in theme give back the rest of it, to within what the eye can tell apart', () => {
	for (const theme of builtinThemes) {
		const derived = deriveColors(theme.mode, theme.colors)!
		for (const token of DERIVED_TOKENS.filter((token) => !token.startsWith('chart-'))) {
			const distance = colorDistance(parseColor(theme.colors[token])!, parseColor(derived[token])!)
			assert.ok(distance < 0.012, `${theme.id} ${token} is ${distance.toFixed(3)} off`)
		}
		assert.deepEqual(pinnedColors(theme.mode, theme.colors), [], theme.id)
	}
})

test('unreadable main colours derive nothing and leave the theme as it is', () => {
	const broken = { ...themisDefault.colors, background: 'not a colour' }
	assert.equal(deriveColors('dark', broken), null)
	assert.deepEqual(resolveColors('dark', broken, []), broken)
	assert.equal(pinnedColors('dark', broken).length, DERIVED_TOKENS.length) // nothing can be said to follow
})

test('a copy of a theme looks exactly like it and follows its mains', () => {
	const copy = duplicateTheme(themisDefault, 'Mine')
	assert.deepEqual(copy.colors, themisDefault.colors)
	assert.deepEqual(copy.pinned, [])
	assert.notEqual(copy.colors, themisDefault.colors) // its own object: editing the copy never touches the built-in
	const darkerPage = editTheme(copy, { colors: { background: 'oklch(0.1 0.03 260)' } })
	assert.notEqual(darkerPage.colors.card, copy.colors.card) // the cards follow the page
	assert.equal(darkerPage.colors.primary, copy.colors.primary) // what is not built from the page stays
	assert.equal(themisDefault.colors.background, 'oklch(0.145 0.008 50)')
})

test('a new primary colour carries its focus ring and sidebar button with it', () => {
	const copy = duplicateTheme(themisDefault, 'Mine')
	const next = editTheme(copy, { colors: { primary: 'oklch(0.7 0.2 150)' } })
	assert.equal(next.colors['sidebar-primary'], 'oklch(0.7 0.2 150)')
	assert.ok(next.colors.ring.startsWith('oklch(0.7 0.2 150 / 60%'))
})

test('setting a derived colour pins it, and following again takes it back', () => {
	const copy = duplicateTheme(themisDefault, 'Mine')
	const pinned = editTheme(copy, { colors: { card: 'oklch(0.3 0.05 20)' } })
	assert.deepEqual(pinned.pinned, ['card'])
	const moved = editTheme(pinned, { colors: { background: 'oklch(0.2 0.02 100)' } })
	assert.equal(moved.colors.card, 'oklch(0.3 0.05 20)') // pinned: stays
	assert.notEqual(moved.colors.sidebar, pinned.colors.sidebar) // not pinned: follows
	const following = editTheme(moved, { follow: ['card'] })
	assert.deepEqual(following.pinned, [])
	assert.notEqual(following.colors.card, 'oklch(0.3 0.05 20)')
})

test('changing the surface re-derives the colours that follow', () => {
	const copy = duplicateTheme(themisDefault, 'Mine')
	const light = editTheme(copy, { mode: 'light' })
	assert.equal(light.mode, 'light')
	assert.notEqual(light.colors.border, copy.colors.border) // a wash on dark, a solid grey on light
	assert.equal(light.colors.background, copy.colors.background) // mains are the person's, untouched
})

test('a copy of the light theme follows too', () => {
	const copy = duplicateTheme(themisLight, 'Mine')
	assert.deepEqual(copy.pinned, [])
	const next = editTheme(copy, { colors: { background: 'oklch(0.97 0.01 90)' } })
	assert.notEqual(next.colors.sidebar, copy.colors.sidebar)
})

test('older saved themes, without pins, get theirs worked out from their colours', () => {
	const old = { id: 'custom-old', name: 'Old', mode: 'dark', colors: { ...themisDefault.colors, card: 'oklch(0.5 0.1 100)' } }
	const [theme] = parseCustomThemes([old])
	assert.deepEqual(theme.pinned, ['card'])
	assert.deepEqual(theme.palette, [])
	const [kept] = parseCustomThemes([{ ...old, pinned: ['card', 'nonsense', 'border'] }])
	assert.deepEqual(kept.pinned, ['card', 'border']) // known tokens only, in token order
})

test('a palette keeps real, named colours, up to twenty', () => {
	assert.deepEqual(cleanPalette('nope'), [])
	const entry = newPaletteColor('  oklch(0.5 0.1 200) ', '  Sea  ')
	assert.deepEqual({ name: entry.name, color: entry.color }, { name: 'Sea', color: 'oklch(0.5 0.1 200)' })
	assert.equal(newPaletteColor('#fff', '   ').name, 'Colour')
	const many = Array.from({ length: 30 }, (_, i) => ({ id: `id${i}`, name: `C${i}`, color: '#abc' }))
	assert.equal(cleanPalette(many).length, MAX_PALETTE)
	assert.deepEqual(cleanPalette([{ id: 'a', name: 'ok', color: '#abc' }, { id: 'a', name: 'twice', color: '#abc' }, { id: 'b', name: 'bad', color: 'nope' }, { id: 'c', color: 'rgb(1 2 3)' }, 5]).map((e) => e.id + e.name), ['aok', 'cColour'])
})

test('the palette is stored with its theme, and editing it is an edit like any other', () => {
	const copy = duplicateTheme(themisDefault, 'Mine')
	const withColour = editTheme(copy, { palette: [newPaletteColor('#f97316', 'Orange')] })
	assert.equal(withColour.palette.length, 1)
	assert.equal(duplicateTheme(withColour, 'Again').palette[0].color, '#f97316') // a copy takes the palette along
	assert.notEqual(duplicateTheme(withColour, 'Again').palette[0], withColour.palette[0])
	const [back] = parseCustomThemes(JSON.parse(JSON.stringify([withColour])))
	assert.deepEqual(back.palette, withColour.palette)
	assert.deepEqual(back.colors, withColour.colors)
})
