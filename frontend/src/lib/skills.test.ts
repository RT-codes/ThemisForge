import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isSkillName, skillTemplate, withName } from './skills.ts'

test('a new skill starts from a template that is already a valid file', () => {
  const text = skillTemplate('pdf-tips')
  assert.match(text, /^---\nname: pdf-tips\ndescription: .+\n---\n/)
})

test('naming a skill rewrites the name line and leaves the rest alone', () => {
  const text = withName(skillTemplate('my-skill'), 'web-search')
  assert.match(text, /^---\nname: web-search\n/)
  assert.ok(text.includes('description: What this skill does'))
  assert.ok(text.endsWith('applies.\n'))
})

test('a missing name line is added, and a file without frontmatter is left as it is', () => {
  assert.match(withName('---\ndescription: d\n---\nbody', 'a'), /^---\nname: a\ndescription: d\n---\nbody/)
  assert.equal(withName('just text', 'a'), 'just text')
})

test('skill names follow the server rule', () => {
  for (const ok of ['a', 'pdf-tips', 'x1', '1a']) assert.ok(isSkillName(ok), ok)
  for (const bad of ['', 'A', '-a', 'a b', 'a/b', 'x'.repeat(41)]) assert.ok(!isSkillName(bad), bad)
})
