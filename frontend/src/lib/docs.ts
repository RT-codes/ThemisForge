import { renderMarkdown, type RenderedDoc } from './markdown'

/** The documentation lives in /docs at the repository root, so it reads well on GitHub and in the app. */
const files = import.meta.glob('../../../docs/*.md', { query: '?raw', import: 'default', eager: true }) as Record<
  string,
  string
>

export interface DocPage {
  slug: string
  title: string
  group: string
  summary: string
  markdown: string
}

export interface SearchHit {
  slug: string
  page: string
  heading: string
  id: string | null
  snippet: string
}

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
