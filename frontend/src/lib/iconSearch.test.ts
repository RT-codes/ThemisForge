import assert from 'node:assert/strict'
import { test } from 'node:test'
import { iconNameOf, matchIcons } from './iconSearch.ts'

const names = ['folder', 'folder-kanban', 'folder-open', 'file-text', 'shopping-cart', 'cart-plus', 'bot']

test('every word typed must be in the name, in any order', () => {
  assert.deepEqual(matchIcons(names, 'folder'), ['folder', 'folder-kanban', 'folder-open'])
  assert.deepEqual(matchIcons(names, 'kanban folder'), ['folder-kanban'])
  assert.deepEqual(matchIcons(names, 'cart'), ['cart-plus', 'shopping-cart'])
  assert.deepEqual(matchIcons(names, 'nothing like it'), [])
})

test('the exact name comes first, then names that start with the word, then the rest', () => {
  assert.deepEqual(matchIcons(['a-bot', 'robot', 'bot', 'bottle'], 'bot'), ['bot', 'bottle', 'a-bot', 'robot'])
  assert.deepEqual(matchIcons(['x-ray', 'x', 'xbox'], 'x'), ['x', 'x-ray', 'xbox'])
})

test('capitals, spaces and hyphens do not matter, and an empty search lists everything', () => {
  assert.deepEqual(matchIcons(names, '  Folder-KANBAN '), ['folder-kanban'])
  assert.equal(matchIcons(names, '').length, names.length)
})

test('the name of an icon is read from its file', () => {
  assert.equal(iconNameOf('/node_modules/@lucide/svelte/dist/icons/folder-kanban.svelte'), 'folder-kanban')
  assert.equal(iconNameOf('/node_modules/@lucide/svelte/dist/icons/a-arrow-down.svelte'), 'a-arrow-down')
  assert.equal(iconNameOf('/x/index.d.ts'), null)
})
