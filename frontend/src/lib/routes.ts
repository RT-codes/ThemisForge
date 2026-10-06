export type ProjectPageName = 'overview' | 'tasks'

export type Route =
  | { name: 'home' }
  | { name: 'project'; id: number; page: ProjectPageName }
  | { name: 'workflow'; id: number; workflowId: number | null; run: number | null } // workflowId null: a new one, not saved yet
  | { name: 'settings' }
  | { name: 'access' }
  | { name: 'docs'; slug: string }
  | { name: 'invite'; token: string }
  | { name: 'not-found' }

export function parse(path: string): Route {
  if (path === '/' || path === '') return { name: 'home' }
  if (path === '/settings') return { name: 'settings' }
  if (path === '/access') return { name: 'access' }
  const docs = path.match(/^\/docs(?:\/([\w-]+))?\/?$/)
  if (docs) return { name: 'docs', slug: docs[1] ?? 'overview' }
  const invite = path.match(/^\/invite\/([\w-]+)\/?$/)
  if (invite) return { name: 'invite', token: invite[1] }
  const fresh = path.match(/^\/projects\/(\d+)\/workflows\/new\/?$/)
  if (fresh) return { name: 'workflow', id: Number(fresh[1]), workflowId: null, run: null }
  const wf = path.match(/^\/projects\/(\d+)\/workflows\/(\d+)(?:\/runs\/(\d+))?\/?$/)
  if (wf) return { name: 'workflow', id: Number(wf[1]), workflowId: Number(wf[2]), run: wf[3] ? Number(wf[3]) : null }
  const m = path.match(/^\/projects\/(\d+)(?:\/(tasks))?\/?$/)
  if (m) return { name: 'project', id: Number(m[1]), page: m[2] ? 'tasks' : 'overview' }
  return { name: 'not-found' }
}
