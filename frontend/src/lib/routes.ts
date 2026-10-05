export type ProjectPageName = 'overview' | 'tasks'

export type Route =
  | { name: 'home' }
  | { name: 'project'; id: number; page: ProjectPageName }
  | { name: 'settings' }
  | { name: 'access' }
  | { name: 'account' }
  | { name: 'docs'; slug: string }
  | { name: 'invite'; token: string }
  | { name: 'not-found' }

export function parse(path: string): Route {
  if (path === '/' || path === '') return { name: 'home' }
  if (path === '/settings') return { name: 'settings' }
  if (path === '/access') return { name: 'access' }
  if (path === '/account') return { name: 'account' }
  const docs = path.match(/^\/docs(?:\/([\w-]+))?\/?$/)
  if (docs) return { name: 'docs', slug: docs[1] ?? 'overview' }
  const invite = path.match(/^\/invite\/([\w-]+)\/?$/)
  if (invite) return { name: 'invite', token: invite[1] }
  const m = path.match(/^\/projects\/(\d+)(?:\/(tasks))?\/?$/)
  if (m) return { name: 'project', id: Number(m[1]), page: m[2] ? 'tasks' : 'overview' }
  return { name: 'not-found' }
}
