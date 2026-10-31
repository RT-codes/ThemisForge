import assert from 'node:assert/strict'
import { test } from 'node:test'
import { PALETTE, chipStyle, colorDistance, formatOklch, hexToOklch, isColor, isHex, mixColors, normalizeHex, oklchToHex, parseColor, parseOklch, swatchHex } from './colors.ts'

test('the palette is made of valid, distinct colours', () => {
  assert.ok(PALETTE.every((c) => isHex(c.hex)))
  assert.equal(new Set(PALETTE.map((c) => c.hex)).size, PALETTE.length)
})

test('colours can be typed in several ways', () => {
  assert.equal(normalizeHex('#3B82F6'), '#3b82f6')
  assert.equal(normalizeHex(' 3b82f6 '), '#3b82f6')
  assert.equal(normalizeHex('#38f'), '#3388ff')
  for (const bad of ['', 'red', '#12345', '#12345g', 'rgb(1,2,3)']) assert.equal(normalizeHex(bad), null, bad)
})

test('a chip is only coloured by a real colour', () => {
  assert.match(chipStyle('#ef4444')!, /color-mix\(in oklab, #ef4444 20%/)
  assert.equal(chipStyle(undefined), undefined)
  assert.equal(chipStyle('red'), undefined)
})

test('oklch colours are read and written, with or without alpha', () => {
  assert.deepEqual(parseOklch('oklch(0.76 0.17 58)'), { l: 0.76, c: 0.17, h: 58, alpha: 1 })
  assert.deepEqual(parseOklch(' oklch(76% 0.17 58 / 60%) '), { l: 0.76, c: 0.17, h: 58, alpha: 0.6 })
  assert.deepEqual(parseOklch('oklch(1 0 0 / 0.09)'), { l: 1, c: 0, h: 0, alpha: 0.09 })
  for (const bad of ['#fff', 'red', 'oklch(0.7 0.1)', 'oklch(a b c)', '']) assert.equal(parseOklch(bad), null)
  assert.equal(formatOklch({ l: 0.76, c: 0.17, h: 58, alpha: 1 }), 'oklch(0.76 0.17 58)')
  assert.equal(formatOklch({ l: 1, c: 0, h: 0, alpha: 0.09 }), 'oklch(1 0 0 / 9%)')
  assert.equal(formatOklch({ l: 0.5, c: 0.1, h: -30, alpha: 1 }), 'oklch(0.5 0.1 330)')
})

test('hex and oklch convert both ways', () => {
  assert.equal(oklchToHex({ l: 1, c: 0, h: 0, alpha: 1 }), '#ffffff')
  assert.equal(oklchToHex({ l: 0, c: 0, h: 0, alpha: 1 }), '#000000')
  for (const hex of ['#3b82f6', '#f97316', '#10b981', '#777777', '#000000', '#ffffff']) {
    const back = oklchToHex(hexToOklch(hex)!)
    assert.equal(back, hex)
  }
  assert.equal(hexToOklch('#38f')?.alpha, 1)
  assert.equal(hexToOklch('#fff', 0.5)?.alpha, 0.5)
  assert.equal(hexToOklch('nope'), null)
  assert.ok(Math.abs(hexToOklch('#ffffff')!.l - 1) < 1e-3)
})

test('the picker colour of a theme value', () => {
  assert.equal(swatchHex('oklch(1 0 0)'), '#ffffff')
  assert.equal(swatchHex('oklch(1 0 0 / 9%)'), '#ffffff')
  assert.equal(swatchHex('#abc'), '#aabbcc')
  assert.equal(swatchHex('rebeccapurple'), '#000000') // a name is not a theme colour
  assert.equal(swatchHex('rgb(255 0 0)'), '#ff0000')
})

test('a theme colour is oklch, hex or rgb; names and other functions are not', () => {
  assert.ok(isColor('oklch(0.5 0.1 200)'))
  assert.ok(isColor('#abc'))
  assert.ok(isColor('rgb(10, 20, 30)'))
  assert.ok(isColor('rgba(10, 20, 30, 0.5)'))
  assert.equal(parseColor('rgb(0 0 255 / 40%)')?.alpha, 0.4)
  assert.equal(parseColor('rgb(300 0 0)')?.l, parseColor('rgb(255 0 0)')?.l) // out of range is clipped
  for (const bad of ['', 'red', 'hsl(10 50% 50%)', 'var(--x)', 'oklch(']) assert.ok(!isColor(bad), bad)
})

test('colours mix in Oklab and measure their distance', () => {
  const black = parseColor('#000')!
  const white = parseColor('#fff')!
  assert.ok(Math.abs(mixColors(black, white, 0.5).l - 0.5) < 1e-3)
  assert.deepEqual(mixColors(black, white, 0).l, black.l)
  assert.equal(mixColors(black, white, 1).l, white.l)
  assert.ok(mixColors(black, white, -0.1).l < 0) // past the end goes on
  assert.equal(mixColors({ ...black, alpha: 0 }, white, 0.25).alpha, 0.25)
  const red = parseColor('#f00')!
  const blue = parseColor('#00f')!
  const mid = mixColors(red, blue, 0.5)
  assert.ok(mid.c > 0.1) // red and blue stay colourful in the middle
  assert.equal(colorDistance(red, red), 0)
  assert.ok(colorDistance(black, white) > 0.9)
  assert.ok(colorDistance(red, { ...red, alpha: 0.5 }) > 0)
})
