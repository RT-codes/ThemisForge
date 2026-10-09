// Workspaces and boards: pure helpers for picking and describing them (the pages do the loading).

import type { Board, Workspace } from './api'

/** The project's first board: first workspace, first board in it (the server sends both in display order). */
export function defaultBoard(workspaces: Workspace[]): Board | null {
  for (const workspace of workspaces) if (workspace.boards.length) return workspace.boards[0]
  return null
}
