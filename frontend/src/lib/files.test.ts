import assert from 'node:assert/strict'
import { test } from 'node:test'
import { PANE_MAX, PANE_MIN, ZOOM_MAX, arrange, changedPaths, clampPan, clampPane, clampScale, configLink, crumbs, emptyFileView, fileKind, flattenTree, formatSize, isInside, isMarkdown, isValidFolderName, isValidName, joinPath, parentPath, previewKind, resolveRelative, scaleToSlider, sliderToScale, splitFrontmatter, watchDelay, zoomAt } from './files.ts'

test('paths join and split relative to the root', () => {
  assert.equal(joinPath('', 'a.txt'), 'a.txt')
  assert.equal(joinPath('reports/2024', 'a.txt'), 'reports/2024/a.txt')
  assert.equal(parentPath('reports/2024/a.txt'), 'reports/2024')
  assert.equal(parentPath('a.txt'), '')
})
test('breadcrumbs lead back up the path', () => {
  assert.deepEqual(crumbs(''), [])
  assert.deepEqual(crumbs('reports/2024'), [
    { name: 'reports', path: 'reports' },
    { name: '2024', path: 'reports/2024' },
  ])
})
test('a name cannot hold a slash or stand for a folder', () => {
  for (const bad of ['', '  ', '.', '..', 'a/b']) assert.equal(isValidName(bad), false)
  assert.equal(isValidName('report 1.md'), true)
})
test('images and small text files can be previewed, the rest are downloads', () => {
  assert.equal(previewKind('chart.PNG', 10), 'image')
  assert.equal(previewKind('notes.md', 10), 'text')
  assert.equal(previewKind('notes.md', 5 * 1024 * 1024), null)
  assert.equal(previewKind('archive.zip', 10), null)
  assert.equal(previewKind('logo.SVG', 10), 'image') // shown in an <img>, where it cannot run script
})
test('sizes read naturally', () => {
  assert.equal(formatSize(0), '0 B')
  assert.equal(formatSize(1536), '1.5 KB')
  assert.equal(formatSize(20 * 1024 * 1024), '20 MB')
})

const e = (name: string, size = 1, modified = '2026-01-01T00:00:00Z', is_dir = false) => ({ name, size, modified, is_dir })
const listing = [
  e('b.txt', 5, '2026-01-02T00:00:00Z'),
  e('a.png', 50, '2026-01-03T00:00:00Z'),
  e('docs', 0, '2026-01-01T00:00:00Z', true),
  e('c.zip', 500, '2026-01-01T00:00:00Z'),
  e('Archive', 0, '2026-01-09T00:00:00Z', true),
]
const names = (v: Partial<ReturnType<typeof emptyFileView>>) => arrange(listing, { ...emptyFileView(), ...v }).map((x) => x.name)

test('files are told apart by their extension', () => {
  assert.deepEqual(['a.PNG', 'a.md', 'a.zip', '.env', 'Makefile', 'notes'].map(fileKind), ['image', 'text', 'other', 'text', 'text', 'other'])
})
test('folders come first by name, then files in the chosen order', () => {
  assert.deepEqual(names({}), ['Archive', 'docs', 'a.png', 'b.txt', 'c.zip'])
  assert.deepEqual(names({ sort: 'newest' }), ['Archive', 'docs', 'a.png', 'b.txt', 'c.zip'])
  assert.deepEqual(names({ sort: 'oldest' }), ['Archive', 'docs', 'c.zip', 'b.txt', 'a.png'])
  assert.deepEqual(names({ sort: 'largest' }), ['Archive', 'docs', 'c.zip', 'a.png', 'b.txt'])
  assert.deepEqual(names({ sort: 'smallest' }), ['Archive', 'docs', 'b.txt', 'a.png', 'c.zip'])
})
test('numbers inside names sort naturally', () => {
  const items = [e('file10.txt'), e('file2.txt')]
  assert.deepEqual(arrange(items, emptyFileView()).map((x) => x.name), ['file2.txt', 'file10.txt'])
})
test('search matches part of a file name, ignoring case, and never hides folders', () => {
  assert.deepEqual(names({ search: ' PN ' }), ['Archive', 'docs', 'a.png'])
  assert.deepEqual(names({ search: '.t' }), ['Archive', 'docs', 'b.txt'])
})
test('the type filter narrows files but keeps folders to move through', () => {
  assert.deepEqual(names({ type: 'image' }), ['Archive', 'docs', 'a.png'])
  assert.deepEqual(names({ type: 'other' }), ['Archive', 'docs', 'c.zip'])
})

const box = { w: 400, h: 300 }
const picture = { w: 400, h: 200 } // fitted to the width of the view
const fit = { scale: 1, x: 0, y: 0 }

test('the zoom slider and the scale convert both ways, and stay within range', () => {
  assert.equal(scaleToSlider(1), 0)
  assert.equal(scaleToSlider(ZOOM_MAX), 100)
  assert.equal(Math.round(sliderToScale(scaleToSlider(3)) * 10) / 10, 3)
  assert.equal(clampScale(0.2), 1)
  assert.equal(clampScale(99), ZOOM_MAX)
})
test('a picture cannot be dragged out of sight, and a small one stays centred', () => {
  assert.deepEqual(clampPan(500, 500, 2, box, picture), { x: 200, y: 50 }) // 800x400 in a 400x300 view
  assert.deepEqual(clampPan(-500, -500, 2, box, picture), { x: -200, y: -50 })
  assert.deepEqual(clampPan(30, 30, 1, box, picture), { x: 0, y: 0 })
})
test('zooming keeps the point under the cursor in place', () => {
  const cursor = { x: 100, y: 0 } // right of the centre
  const zoomed = zoomAt(fit, 2, cursor, box, picture)
  assert.equal(zoomed.scale, 2)
  assert.equal(zoomed.x, -100) // the picture moved left, so the same spot is still under the cursor
  assert.deepEqual(zoomAt(fit, 2, { x: 0, y: 0 }, box, picture), { scale: 2, x: 0, y: 0 })
})
test('zooming back out to fit recentres the picture', () => {
  const zoomed = zoomAt(fit, 4, { x: 150, y: 80 }, box, picture)
  assert.notEqual(zoomed.x, 0)
  assert.deepEqual(zoomAt(zoomed, 1, { x: 150, y: 80 }, box, picture), fit)
})

test('markdown is told apart by its extension', () => {
  assert.deepEqual(['README.md', 'notes.MARKDOWN', 'a.txt', 'md'].map(isMarkdown), [true, true, false, false])
})
test('a picture in a markdown file is read from its own folder, and only from there', () => {
  assert.equal(resolveRelative('reports', 'chart.png'), 'reports/chart.png')
  assert.equal(resolveRelative('reports/2024', '../logo.png'), 'reports/logo.png')
  assert.equal(resolveRelative('', './img/a%20b.png?raw=1#x'), 'img/a b.png')
  for (const bad of ['', '/etc/passwd', 'https://x.test/a.png', 'data:image/png;base64,AA', '//x.test/a.png', '../../a.png', 'javascript:alert(1)'])
    assert.equal(resolveRelative('reports', bad), null, bad)
})

test('a shared folder name follows the server rule, ignoring case and outer spaces', () => {
  for (const ok of ['reports', ' Reports ', 'a', '2024-q1']) assert.equal(isValidFolderName(ok), true, ok)
  for (const bad of ['', '-x', 'has space', 'a/b', '..', 'x'.repeat(41)]) assert.equal(isValidFolderName(bad), false, bad)
})

test('the settings at the top of a markdown file are split from its text', () => {
  assert.deepEqual(splitFrontmatter('---\nname: a\ndescription: b\n---\n\n# Title\n'), { meta: 'name: a\ndescription: b', body: '\n# Title\n' })
  assert.deepEqual(splitFrontmatter('\uFEFF---\r\nname: a\r\n---\r\nbody'), { meta: 'name: a', body: 'body' })
  assert.deepEqual(splitFrontmatter('---\nname: a\n---'), { meta: 'name: a', body: '' })
  // not frontmatter: a rule in the middle, or no closing line
  assert.deepEqual(splitFrontmatter('text\n---\nmore\n---\n'), { meta: '', body: 'text\n---\nmore\n---\n' })
  assert.deepEqual(splitFrontmatter('---\nname: a'), { meta: '', body: '---\nname: a' })
})

// ----- what the page works out from the folders it has listed -----

test('a path is inside a folder only at a folder boundary', () => {
  assert.equal(isInside('docs', 'docs'), true)
  assert.equal(isInside('docs/a.md', 'docs'), true)
  assert.equal(isInside('docs2/a.md', 'docs'), false) // a longer name that merely starts the same
  assert.equal(isInside('a.md', 'docs'), false)
})

test('only what is new or really changed pulses, and nothing does the first time a folder is listed', () => {
  const before = { entries: [e('a.txt', 5, '2026-01-01T00:00:00Z'), e('b.txt', 5, '2026-01-01T00:00:00Z'), e('docs', 0, '2026-01-01T00:00:00Z', true)] }
  const after = {
    entries: [
      e('a.txt', 5, '2026-01-01T00:00:00Z'), // untouched
      e('b.txt', 9, '2026-01-01T00:00:00Z'), // grew
      e('c.txt', 1, '2026-01-02T00:00:00Z'), // new
      e('docs', 0, '2026-02-01T00:00:00Z', true), // a folder's own time moving is not a change
    ],
  }
  assert.deepEqual(changedPaths('reports', before, after), ['reports/b.txt', 'reports/c.txt'])
  assert.deepEqual(changedPaths('', before, after), ['b.txt', 'c.txt'])
  assert.deepEqual(changedPaths('', undefined, after), [])
})

test('the files on screen are listed top to bottom with open folders walked in place', () => {
  const tree = {
    '': { entries: [e('z.txt'), e('docs', 0, '2026-01-01T00:00:00Z', true), e('src', 0, '2026-01-01T00:00:00Z', true)] },
    docs: { entries: [e('b.md'), e('a.md')] },
    src: { entries: [e('main.ts')] },
  }
  const names = (expanded: string[]) => flattenTree(tree, expanded, emptyFileView()).map((f) => f.path)
  assert.deepEqual(names([]), ['z.txt']) // closed folders hold nothing visible
  assert.deepEqual(names(['docs']), ['docs/a.md', 'docs/b.md', 'z.txt'])
  assert.deepEqual(names(['docs', 'src']), ['docs/a.md', 'docs/b.md', 'src/main.ts', 'z.txt'])
  assert.deepEqual(flattenTree({}, [], emptyFileView()), []) // nothing listed yet
})

test('a link into the config folder names the path to open', () => {
  assert.deepEqual(configLink('config'), [])
  assert.deepEqual(configLink('config/agents/scout/agent.md'), ['agents', 'scout', 'agent.md'])
  assert.deepEqual(configLink('config//agents/'), ['agents'])
  assert.equal(configLink(''), null)
  assert.equal(configLink('configuration'), null) // only the folder of that exact name
  assert.equal(configLink('docs/config'), null)
})

test('a folder is watched often while it is in use or changing, and rarely when quiet', () => {
  assert.equal(watchDelay(true, 999_999), 1500) // a run is using it
  assert.equal(watchDelay(false, 1000), 1500) // something changed a moment ago
  assert.equal(watchDelay(false, 29_999), 1500)
  assert.equal(watchDelay(false, 30_000), 5000) // quiet for a while
})

test('the divider keeps both panes usable', () => {
  assert.equal(clampPane(10), PANE_MIN)
  assert.equal(clampPane(90), PANE_MAX)
  assert.equal(clampPane(45), 45)
})
