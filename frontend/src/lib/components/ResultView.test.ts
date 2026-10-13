import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { createServer, type ViteDevServer } from 'vite'

let server: ViteDevServer
let result: (text: string) => string

before(async () => {
  server = await createServer({
    server: { middlewareMode: true },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true },
    ssr: { optimizeDeps: { noDiscovery: true } },
  })
  const { render } = await server.ssrLoadModule('svelte/server')
  const { default: ResultView } = await server.ssrLoadModule('/src/lib/components/ResultView.svelte')
  result = (text) => render(ResultView, { props: { text } }).body
})

after(async () => { await server?.close() })

test('results open as Markdown with a raw view available', () => {
  const html = result('# Report\n\n- **Done**\n\n| Step | Status |\n| --- | --- |\n| Build | Passed |\n\n[Review](https://example.com/pr/1)\n\n```ts\nconst done = true\n```')
  assert.match(html, /aria-pressed="true"[^>]*><!---->Rendered/)
  assert.match(html, /aria-pressed="false"[^>]*><!---->Raw/)
  assert.match(html, /<h1>Report<\/h1>/)
  assert.match(html, /<li><strong>Done<\/strong><\/li>/)
  assert.match(html, /<table>/)
  assert.match(html, /href="https:\/\/example.com\/pr\/1" target="_blank" rel="noopener noreferrer"/)
  assert.match(html, /data-copy>Copy<\/button>/)
  assert.match(html, /<code>const done = true<\/code>/)
})

test('agent HTML, unsafe links and remote images cannot become active content', () => {
  const html = result('<script>alert(1)</script>\n\n[bad](javascript:alert(1))\n\n![tracking](https://example.com/pixel.png)')
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/)
  assert.doesNotMatch(html, /<script|<img|href="javascript:/)
  assert.match(html, /tracking/)
})

test('plain text and empty results are supported', () => {
  assert.match(result('All checks passed.'), /<p>All checks passed\.<\/p>/)
  assert.doesNotThrow(() => result(''))
})
