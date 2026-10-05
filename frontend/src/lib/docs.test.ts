import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { test } from 'node:test'

// The docs are plain markdown in /docs. These checks keep them navigable: every page has a title and a
// group, and every link to another docs page points at a page that exists.
const dir = new URL('../../../docs/', import.meta.url)
const files = readdirSync(dir).filter((f) => f.endsWith('.md')).sort()
const slugs = new Set(files.map((f) => f.replace(/^\d+-/, '').replace(/\.md$/, '')))

test('there are docs pages', () => assert.ok(files.length >= 5))

test('every page names itself, its group and has a single title heading', () => {
  for (const file of files) {
    const text = readFileSync(new URL(file, dir), 'utf8')
    const front = text.match(/^---\n([\s\S]*?)\n---\n/)
    assert.ok(front, `${file}: missing front matter`)
    assert.match(front[1], /^title: .+/m, `${file}: missing title`)
    assert.match(front[1], /^group: .+/m, `${file}: missing group`)
    assert.equal((text.match(/^# /gm) ?? []).length, 1, `${file}: expected exactly one # heading`)
  }
})

test('links between docs pages resolve', () => {
  for (const file of files) {
    const text = readFileSync(new URL(file, dir), 'utf8')
    for (const [, slug] of text.matchAll(/\]\(\/docs\/([\w-]+)(?:#[\w-]+)?\)/g)) {
      assert.ok(slugs.has(slug), `${file}: link to unknown page /docs/${slug}`)
    }
  }
})

test('no em dashes in the docs', () => {
  for (const file of files) assert.ok(!readFileSync(new URL(file, dir), 'utf8').includes('—'), `${file}: contains an em dash`)
})
