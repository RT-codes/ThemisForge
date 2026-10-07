import { Marked, type Tokens } from 'marked'

// One markdown renderer for the whole app. The documentation uses it as is (it is written by us and ships with the app);
// a file an agent wrote is rendered with `untrusted` set, which cannot produce anything that runs script or reaches out.

export interface Heading {
  id: string
  text: string
  depth: 2 | 3
}

export interface RenderedDoc {
  html: string
  headings: Heading[]
}

export interface RenderOptions {
  /** the text is not ours: raw HTML is shown as text, only safe links are kept, and pictures only come from `image` */
  untrusted?: boolean
  /** untrusted only: where a picture in the text comes from, or null to leave the picture out (shown as its alt text) */
  image?: (src: string) => string | null
}

export const escapeHtml = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

export const slugify = (text: string) =>
  text
    .toLowerCase()
    .replace(/<[^>]+>/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')

const ALERTS = { NOTE: 'Note', TIP: 'Tip', WARNING: 'Warning' } as const

// what a link in untrusted text may point at: the web, a mail address, or a spot in the same page. A list of what is
// allowed, never of what is not (javascript:, data: and the many ways of spelling them).
const SAFE_LINK = /^(https?:\/\/|mailto:|#)/i

export function renderMarkdown(markdown: string, options: RenderOptions = {}): RenderedDoc {
  const { untrusted = false, image } = options
  const headings: Heading[] = []
  const used = new Map<string, number>()

  const marked = new Marked({
    gfm: true,
    renderer: {
      heading({ tokens, depth }) {
        const html = this.parser.parseInline(tokens)
        const text = tokens.map((t) => ('text' in t ? String(t.text) : '')).join('')
        let id = slugify(text)
        const n = used.get(id) ?? 0
        used.set(id, n + 1)
        if (n) id = `${id}-${n + 1}`
        if (depth === 2 || depth === 3) headings.push({ id, text, depth })
        if (untrusted) return `<h${depth}>${html}</h${depth}>\n` // no ids or anchors: they would change the address
        return `<h${depth} id="${id}">${html}<a class="docs-anchor" href="#${id}" aria-label="Link to this section">#</a></h${depth}>\n`
      },
      code({ text, lang }: Tokens.Code) {
        const label = lang && lang !== 'text' ? lang : 'text'
        return (
          `<div class="docs-code"><div class="docs-code-head"><span>${escapeHtml(label)}</span>` +
          `<button type="button" data-copy>Copy</button></div>` +
          `<pre><code>${escapeHtml(text)}</code></pre></div>\n`
        )
      },
      blockquote({ tokens }) {
        let body = this.parser.parse(tokens)
        const m = body.match(/^<p>\[!(NOTE|TIP|WARNING)\]\s*/)
        if (!m) return `<blockquote>${body}</blockquote>\n`
        body = body.replace(m[0], '<p>')
        const kind = m[1] as keyof typeof ALERTS
        return `<aside class="docs-callout" data-kind="${kind.toLowerCase()}"><strong>${ALERTS[kind]}</strong>${body}</aside>\n`
      },
      link({ href, title, tokens }) {
        const text = this.parser.parseInline(tokens)
        if (untrusted && !SAFE_LINK.test(href)) return text // a link that cannot be trusted is just its words
        const external = /^https?:\/\//i.test(href) || href.startsWith('/api/')
        const attrs = external ? ` target="_blank" rel="noopener${untrusted ? ' noreferrer' : ''}"` : ''
        return `<a href="${escapeHtml(href)}"${title ? ` title="${escapeHtml(title)}"` : ''}${attrs}>${text}</a>`
      },
      ...(untrusted && {
        // raw HTML, block or inline, is shown as the text it is
        html: ({ text }: Tokens.HTML | Tokens.Tag) => escapeHtml(text),
        image({ href, title, text }: Tokens.Image) {
          const src = image?.(href) ?? null
          if (src === null) return escapeHtml(text)
          return `<img src="${escapeHtml(src)}" alt="${escapeHtml(text)}"${title ? ` title="${escapeHtml(title)}"` : ''} loading="lazy">`
        },
      }),
    },
  })

  // wide tables scroll sideways instead of breaking the layout
  const html = (marked.parse(markdown) as string)
    .replaceAll('<table>', '<div class="docs-table"><table>')
    .replaceAll('</table>', '</table></div>')
  return { html, headings }
}

/** The click handler for the Copy buttons on rendered code blocks (set it on the element that holds the markdown). */
export async function onCodeCopyClick(e: MouseEvent) {
  const button = (e.target as Element).closest<HTMLButtonElement>('[data-copy]')
  if (!button) return
  const code = button.closest('.docs-code')?.querySelector('code')?.textContent ?? ''
  try {
    await navigator.clipboard.writeText(code)
    button.textContent = 'Copied'
  } catch {
    // not a secure context (plain http): select the code so Ctrl+C works
    const range = document.createRange()
    range.selectNodeContents(button.closest('.docs-code')!.querySelector('code')!)
    window.getSelection()?.removeAllRanges()
    window.getSelection()?.addRange(range)
    button.textContent = 'Press Ctrl+C'
  }
  setTimeout(() => (button.textContent = 'Copy'), 1800)
}
