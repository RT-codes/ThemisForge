export type ProjectPageName = 'overview' | 'settings' | 'tasks' | 'files'

export type Route =
  | { name: 'home' }
  | { name: 'project'; id: number; page: ProjectPageName } // tasks: the project's first board
  | { name: 'project'; id: number; page: 'workspace'; workspaceId: number } // a workspace with its boards stacked
  | { name: 'project'; id: number; page: 'board'; boardId: number } // one board on its own
  | { name: 'workflow'; id: number; workflowId: number | null; run: number | null; resume: boolean } // workflowId null: a new one, not saved yet; resume: no workflow chosen, open the latest
  | { name: 'agents'; id: number; agentId: number | null; isNew: boolean; editing: boolean } // agentId null and not new: the list, nothing chosen; an agent is shown first and edited on /edit
  | { name: 'settings' }
  | { name: 'theme'; id: string } // the editor of one custom theme
  | { name: 'access' }
  | { name: 'docs'; slug: string }
  | { name: 'invite'; token: string }
  | { name: 'not-found' }

export function parse(path: string): Route {
  if (path === '/' || path === '') return { name: 'home' }
  if (path === '/settings') return { name: 'settings' }
  const theme = path.match(/^\/settings\/themes\/([\w-]+)\/?$/)
  if (theme) return { name: 'theme', id: theme[1] }
  if (path === '/access') return { name: 'access' }
  const docs = path.match(/^\/docs(?:\/([\w-]+))?\/?$/)
  if (docs) return { name: 'docs', slug: docs[1] ?? 'overview' }
  const invite = path.match(/^\/invite\/([\w-]+)\/?$/)
  if (invite) return { name: 'invite', token: invite[1] }
  const fresh = path.match(/^\/projects\/(\d+)\/workflows\/new\/?$/)
  if (fresh) return { name: 'workflow', id: Number(fresh[1]), workflowId: null, run: null, resume: false }
  const latest = path.match(/^\/projects\/(\d+)\/workflows\/?$/)
  if (latest) return { name: 'workflow', id: Number(latest[1]), workflowId: null, run: null, resume: true }
  const wf = path.match(/^\/projects\/(\d+)\/workflows\/(\d+)(?:\/runs\/(\d+))?\/?$/)
  if (wf) return { name: 'workflow', id: Number(wf[1]), workflowId: Number(wf[2]), run: wf[3] ? Number(wf[3]) : null, resume: false }
  const agent = path.match(/^\/projects\/(\d+)\/agents(?:\/(new|\d+(?:\/edit)?))?\/?$/)
  if (agent) {
    const [what, edit] = (agent[2] ?? '').split('/')
    const isNew = what === 'new'
    return { name: 'agents', id: Number(agent[1]), agentId: what && !isNew ? Number(what) : null, isNew, editing: isNew || edit === 'edit' }
  }
  const space = path.match(/^\/projects\/(\d+)\/workspaces\/(\d+)\/?$/)
  if (space) return { name: 'project', id: Number(space[1]), page: 'workspace', workspaceId: Number(space[2]) }
  const board = path.match(/^\/projects\/(\d+)\/boards\/(\d+)\/?$/)
  if (board) return { name: 'project', id: Number(board[1]), page: 'board', boardId: Number(board[2]) }
  const m = path.match(/^\/projects\/(\d+)(?:\/(tasks|files|settings))?\/?$/)
  if (m) return { name: 'project', id: Number(m[1]), page: (m[2] as ProjectPageName | undefined) ?? 'overview' }
  return { name: 'not-found' }
}

export type TaskTab = 'details' | 'history'

/** A link to one task: its board's page, which opens the task's panel on the given tab (see parseTaskTarget). */
export function taskHref(projectId: number, boardId: number, taskId: number, tab: TaskTab = 'details'): string {
  return `/projects/${projectId}/boards/${boardId}#task=${taskId}&tab=${tab}`
}

export const taskResultHref = (projectId: number, boardId: number, taskId: number): string => taskHref(projectId, boardId, taskId, 'history')

/** A link to a workspace page that lands on one of its boards: that board is open, the others are folded. */
export function workspaceBoardHref(projectId: number, workspaceId: number, boardId: number): string {
  return `/projects/${projectId}/workspaces/${workspaceId}#board=${boardId}`
}

export function parseBoardTarget(hash: string): number | null {
  const match = hash.match(/^board=([1-9]\d*)$/)
  return match && Number.isSafeInteger(Number(match[1])) ? Number(match[1]) : null
}

export function parseTaskTarget(hash: string): { taskId: number; tab: TaskTab } | null {
  const match = hash.match(/^task=([1-9]\d*)&tab=(details|history)$/)
  if (!match || !Number.isSafeInteger(Number(match[1]))) return null
  return { taskId: Number(match[1]), tab: match[2] as TaskTab }
}
