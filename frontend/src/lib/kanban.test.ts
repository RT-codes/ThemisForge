import assert from 'node:assert/strict'
import { test } from 'node:test'
import { dropPosition } from './kanban.ts'

test('an empty column starts at 1', () => assert.equal(dropPosition([], 0), 1))
test('top of a column goes before the first card', () => assert.equal(dropPosition([3, 4], 0), 2))
test('bottom of a column goes after the last card', () => assert.equal(dropPosition([3, 4], 2), 5))
test('between two cards is their midpoint', () => assert.equal(dropPosition([1, 2, 4], 2), 3))
test('the order is kept after repeated inserts at the same spot', () => {
  let cards = [1, 2]
  for (let i = 0; i < 20; i++) {
    const p = dropPosition(cards, 1)
    assert.ok(p > cards[0] && p < cards[1])
    cards = [cards[0], p, ...cards.slice(1)]
  }
})
