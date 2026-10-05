import { Marked, type Tokens } from 'marked'

/** The documentation lives in /docs at the repository root, so it reads well on GitHub and in the app. */
const files = import.meta.glob('../../../docs/*.md', { query: '?raw', import: 'default', eager: true }) as Record<
  string,
  string
>

export interface Heading {
  id: string
  text: string
  depth: 2 | 3
}

export interface DocPage {
  slug: string
  title: string
  group: string
  summary: string
  markdown: string
}

export interface RenderedDoc {
  html: string
  headings: Heading[]
}

export interface SearchHit {
  slug: string
  page: string
  heading: string
  id: string | null
  snippet: string
}

const escapeHtml = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

export const slugify = (text: string) =>
  text
    .toLowerCase()
    .replace(/<[^>]+>/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')

function parseFrontmatter(source: string): { meta: Record<string, string>; body: string } {
  const match = source.match(/^---\n([\s\S]*?)\n---\n?/)
  if (!match) return { meta: {}, body: source }
  const meta: Record<string, string> = {}
  for (const line of match[1].split('\n')) {
    const i = line.indexOf(':')
    if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).trim()
  }
  return { meta, body: source.slice(match[0].length) }
}

/** Files are named NN-slug.md: the number is the order, the rest is the address (/docs/slug). */
export const pages: DocPage[] = Object.entries(files)
  .map(([path, source]) => {
    const file = path.split('/').pop()!.replace(/\.md$/, '')
    const { meta, body } = parseFrontmatter(source)
    const slug = file.replace(/^\d+-/, '')
    return {
      order: file,
      page: {
        slug,
        title: meta.title ?? slug,
        group: meta.group ?? 'Docs',
        summary: meta.summary ?? '',
        markdown: body,
      } satisfies DocPage,
    }
  })
  .sort((a, b) => a.order.localeCompare(b.order))
  .map((x) => x.page)

export const groups = [...new Set(pages.map((p) => p.group))].map((name) => ({
  name,
  pages: pages.filter((p) => p.group === name),
}))

export const findPage = (slug: string) => pages.find((p) => p.slug === slug)

const ALERTS = { NOTE: 'Note', TIP: 'Tip', WARNING: 'Warning' } as const

function renderMarkdown(markdown: string): RenderedDoc {
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
        const external = /^https?:\/\//.test(href) || href.startsWith('/api/')
        const attrs = external ? ' target="_blank" rel="noopener"' : ''
        return `<a href="${escapeHtml(href)}"${title ? ` title="${escapeHtml(title)}"` : ''}${attrs}>${text}</a>`
      },
    },
  })

  // wide tables scroll sideways instead of breaking the layout
  const html = (marked.parse(markdown) as string)
    .replaceAll('<table>', '<div class="docs-table"><table>')
    .replaceAll('</table>', '</table></div>')
  return { html, headings }
}

const cache = new Map<string, RenderedDoc>()
export function render(page: DocPage): RenderedDoc {
  let doc = cache.get(page.slug)
  if (!doc) cache.set(page.slug, (doc = renderMarkdown(page.markdown)))
  return doc
}

// search: one entry per section (text between headings)

interface Section {
  page: DocPage
  heading: string
  id: string | null
  text: string
}

function plain(markdown: string) {
  return markdown
    .replace(/<[^>]+>/g, ' ')
    .replace(/```[a-z]*\n?/g, ' ')
    .replace(/[`*>|#]/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
}

const sections: Section[] = pages.flatMap((page) => {
  const out: Section[] = []
  let current: Section = { page, heading: page.title, id: null, text: '' }
  const ids = render(page).headings
  let h = 0
  for (const line of page.markdown.split('\n')) {
    const m = line.match(/^(#{2,3})\s+(.*)/)
    if (m) {
      out.push(current)
      current = { page, heading: m[2], id: ids[h++]?.id ?? null, text: '' }
    } else {
      current.text += ` ${line}`
    }
  }
  out.push(current)
  return out.map((s) => ({ ...s, text: plain(s.text) }))
})

export function search(query: string, limit = 8): SearchHit[] {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!terms.length) return []
  return sections
    .map((s) => {
      const heading = s.heading.toLowerCase()
      const text = s.text.toLowerCase()
      if (!terms.every((t) => heading.includes(t) || text.includes(t) || s.page.title.toLowerCase().includes(t))) return null
      const score = terms.reduce((n, t) => n + (heading.includes(t) ? 5 : 0) + (text.includes(t) ? 1 : 0), 0)
      const at = Math.max(0, text.indexOf(terms[0]))
      const snippet = s.text.slice(Math.max(0, at - 40), at + 110).trim()
      return {
        score,
        hit: {
          slug: s.page.slug,
          page: s.page.title,
          heading: s.heading,
          id: s.id,
          snippet: `${at > 40 ? '...' : ''}${snippet}${s.text.length > at + 110 ? '...' : ''}`,
        } satisfies SearchHit,
      }
    })
    .filter((x): x is { score: number; hit: SearchHit } => x !== null)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((x) => x.hit)
}
