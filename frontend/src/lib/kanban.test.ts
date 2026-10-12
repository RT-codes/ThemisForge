import assert from 'node:assert/strict'
import { test } from 'node:test'
import { appendPositions, dropPosition, rangePick, togglePick } from './kanban.ts'

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

test('cards sent to the end of a column keep their order after the last one', () => {
  assert.deepEqual(appendPositions([3, 4], 3), [5, 6, 7])
  assert.deepEqual(appendPositions([], 2), [1, 2])
})

test('ctrl+clicking cards adds them one by one and a second click takes one out', () => {
  assert.deepEqual(togglePick([], 1, null), [1])
  assert.deepEqual(togglePick([1], 2, null), [1, 2])
  assert.deepEqual(togglePick([1, 2], 1, null), [2])
})

test('the card open in the panel joins the selection with the one clicked', () => {
  assert.deepEqual(togglePick([], 2, 1), [1, 2])
  assert.deepEqual(togglePick([3], 2, 1), [3, 1, 2])
  assert.deepEqual(togglePick([1], 2, 1), [1, 2]) // already in: not twice
})

test('ctrl+clicking the card that is open selects just it', () => {
  assert.deepEqual(togglePick([], 1, 1), [1])
})

test('a range is everything from one card to the other, whichever is first', () => {
  const column = [10, 11, 12, 13, 14]
  assert.deepEqual(rangePick(column, 11, 13), [11, 12, 13])
  assert.deepEqual(rangePick(column, 13, 11), [11, 12, 13])
  assert.deepEqual(rangePick(column, 12, 12), [12])
})

test('a range never reaches a card that is not in the column', () => {
  assert.equal(rangePick([10, 11, 12], 11, 99), null) // clicked card is in another status
  assert.equal(rangePick([10, 11, 12], 99, 11), null) // the anchor is in another status, or filtered out
})
