import assert from 'node:assert/strict'
import { test } from 'node:test'
import { renderMarkdown } from './markdown.ts'

const untrusted = (md: string, image: (src: string) => string | null = () => null) => renderMarkdown(md, { untrusted: true, image }).html

test('markdown renders as rich text', () => {
  const html = untrusted('# Title\n\nSome **bold** text and a [link](https://example.com).\n\n- a\n- b\n')
  assert.match(html, /<h1>Title<\/h1>/)
  assert.match(html, /<strong>bold<\/strong>/)
  assert.match(html, /<a href="https:\/\/example.com" target="_blank" rel="noopener noreferrer">link<\/a>/)
  assert.match(html, /<li>a<\/li>/)
})
test('raw HTML from an untrusted file is shown as text, never as markup', () => {
  const html = untrusted('<script>alert(1)</script>\n\nhello <img src=x onerror=alert(1)> there\n\n<div onclick="x()">hi</div>')
  assert.doesNotMatch(html, /<script|<img|<div onclick/)
  assert.match(html, /&lt;script&gt;/)
})
test('only safe links are kept in an untrusted file', () => {
  for (const bad of ['javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'data:text/html,x', 'vbscript:x', 'other.md', '//evil.test'])
    assert.doesNotMatch(untrusted(`[click](${bad})`), /<a /, bad)
  assert.match(untrusted('[x](#part)'), /<a href="#part"/)
  assert.match(untrusted('[x](mailto:a@b.co)'), /<a href="mailto:a@b.co"/)
  assert.match(untrusted('[click](javascript:alert(1))'), /click/) // its words stay
})
test('pictures come only from where the caller says', () => {
  const html = untrusted('![chart](a.png) ![web](https://evil.test/p.gif)', (src) => (src === 'a.png' ? '/api/file?path=a.png' : null))
  assert.match(html, /<img src="\/api\/file\?path=a.png" alt="chart"/)
  assert.doesNotMatch(html, /<img[^>]*evil/)
  assert.match(html, /web/) // left out, its alt text stays
})
test('code in an untrusted file is escaped', () => {
  assert.match(untrusted('```html\n<b onclick="x">hi</b>\n```'), /&lt;b onclick=&quot;x&quot;&gt;/)
  assert.match(untrusted('`<script>`'), /<code>&lt;script&gt;<\/code>/)
})
test('our own docs keep their anchors and raw html', () => {
  const doc = renderMarkdown('## Heading\n\n<kbd>Ctrl</kbd>')
  assert.match(doc.html, /<h2 id="heading">/)
  assert.match(doc.html, /<kbd>Ctrl<\/kbd>/)
  assert.deepEqual(doc.headings, [{ id: 'heading', text: 'Heading', depth: 2 }])
})
