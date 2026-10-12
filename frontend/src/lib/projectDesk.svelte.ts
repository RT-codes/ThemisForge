import { api, ApiError, type Project, type SystemStatus, type Task, type TaskStatus, type WorkflowSummary } from './api'
import { projects } from './projects.svelte'
import { structure } from './structure.svelte'

/** Everything a page that works on a project's tasks needs: the project, its tasks, the open task panel, moving and
 *  deleting. The board page and the workspace page both sit on one, so they behave the same. */
export class ProjectDesk {
  project = $state<Project | null>(null)
  tasks = $state<Task[]>([])
  workflows = $state<WorkflowSummary[]>([])
  system = $state<SystemStatus | null>(null)
  notFound = $state(false)
  loadError = $state('')
  now = $state(Date.now())
  /** counts up on every load, for views that fetch their own data and must refetch when the tasks changed */
  revision = $state(0)

  // the task panel: an existing task, or a new one for a board and status
  sheetOpen = $state(false)
  sheetTaskId = $state<number | null>(null)
  sheetBoardId = $state<number | null>(null)
  sheetStatus = $state<TaskStatus>('backlog')
  /** the card selected on its own (a plain click): it unfolds. One for the whole page, so two boards never both do. */
  focusedTaskId = $state<number | null>(null)
  /** the open panel has changes that are not saved, and how to save them (both reported by the panel) */
  sheetDirty = $state(false)
  saveSheet = $state<(() => Promise<boolean>) | null>(null)
  /** what the person was about to do when unsaved changes stood in the way; the question is open while this is set */
  leaving = $state<(() => void) | null>(null)
  leaveSaving = $state(false)

  /** the tasks the "delete?" question is about (one from a card or the panel, several from a selection) */
  tasksToDelete = $state<Task[]>([])
  deleteError = $state('')

  sheetTask = $derived(this.tasks.find((t) => t.id === this.sheetTaskId) ?? null)

  constructor(readonly projectId: number) {}

  /** Load now and keep the tasks, workflows and scheduler status fresh. Returns what stops it (for onMount). */
  start(): () => void {
    this.load()
    const poll = setInterval(() => {
      if (document.hidden) return
      this.refreshTasks()
      api.workflows(this.projectId).then((w) => (this.workflows = w)).catch(() => {})
      api.systemStatus().then((s) => (this.system = s)).catch(() => {})
    }, 3000)
    const clock = setInterval(() => (this.now = Date.now()), 20_000)
    return () => (clearInterval(poll), clearInterval(clock))
  }

  private refreshTasks() {
    return api.tasks(this.projectId).then((t) => (this.tasks = t)).catch(() => {})
  }

  async load() {
    try {
      const [project, , tasks, workflows, system] = await Promise.all([
        api.project(this.projectId),
        structure.refresh(this.projectId),
        api.tasks(this.projectId),
        api.workflows(this.projectId),
        api.systemStatus(),
      ])
      Object.assign(this, { project, tasks, workflows, system, loadError: '' })
      this.revision++
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) this.notFound = true
      else this.loadError = e instanceof Error ? e.message : 'Could not load the project'
    }
  }

  /** after something changed: reload, and refresh the sidebar's counts */
  async reload() {
    await Promise.all([this.load(), projects.refresh()])
  }

  /** Runs `proceed` now, or after the person has answered the question about the changes that are not saved. */
  private whenClean(proceed: () => void) {
    if (this.sheetOpen && this.sheetDirty) this.leaving = proceed
    else proceed()
  }

  openTask(task: Task) {
    if (this.sheetOpen && this.sheetTaskId === task.id) return
    this.whenClean(() => {
      this.sheetTaskId = task.id
      this.sheetBoardId = task.board_id
      this.sheetOpen = true
    })
  }

  /** `after` runs once the panel is closed, which may be after the question about unsaved changes (or never) */
  closeTask(after?: () => void) {
    this.whenClean(() => {
      this.sheetOpen = false
      after?.()
    })
  }

  addTask(boardId: number, status: TaskStatus = 'backlog') {
    this.whenClean(() => {
      this.sheetTaskId = null
      this.sheetBoardId = boardId
      this.sheetStatus = status
      this.sheetOpen = true
    })
  }

  /** "Keep editing": the panel stays as it is. */
  keepEditing() {
    this.leaving = null
  }

  /** "Discard": the changes go, and the person gets what they were doing. */
  discardAndLeave() {
    const proceed = this.leaving
    this.leaving = null
    this.sheetDirty = false
    proceed?.()
  }

  /** "Save": saved first; if it cannot be (the form says why) the person stays where they were. */
  async saveAndLeave() {
    if (!this.saveSheet || this.leaveSaving) return
    this.leaveSaving = true
    try {
      const saved = await this.saveSheet()
      const proceed = this.leaving
      this.leaving = null
      if (saved) {
        this.sheetDirty = false
        proceed?.()
      }
    } finally {
      this.leaveSaving = false
    }
  }

  /** `boardId`: the board the card was dropped on; a different one than the task's sends the task there */
  async moveTask(task: Task, status: TaskStatus, position: number, boardId: number = task.board_id) {
    const before = this.tasks
    this.tasks = this.tasks.map((t) => (t.id === task.id ? { ...t, status, position, board_id: boardId } : t)) // optimistic
    try {
      if (boardId === task.board_id) await api.updateTask(task.id, { status, position })
      else await api.moveTask(task.id, { board_id: boardId, status, position })
      await this.load()
    } catch (e) {
      this.tasks = before
      this.loadError = e instanceof Error ? e.message : 'Could not move the task'
    }
  }

  /** Several tasks of one board into a status, at the given positions (the end of its column). Only the ones that
   *  were not already there should be passed. A task that cannot move (it started running meanwhile) is skipped. */
  async moveTasks(moves: { task: Task; position: number }[], status: TaskStatus) {
    const position = new Map(moves.map((m) => [m.task.id, m.position]))
    this.tasks = this.tasks.map((t) => (position.has(t.id) ? { ...t, status, position: position.get(t.id)! } : t)) // optimistic
    let failed = 0
    let reason = ''
    for (const { task, position: p } of moves) {
      try {
        await api.updateTask(task.id, { status, position: p })
      } catch (e) {
        failed++
        reason = e instanceof Error ? e.message : 'Could not move the task'
      }
    }
    await this.load() // the truth: what moved stays, and what could not goes back
    // after the load, which clears the error of an earlier one
    if (failed) this.loadError = failed === 1 ? reason : `${failed} of ${moves.length} tasks could not be moved: ${reason}`
  }

  askDelete(...tasks: Task[]) {
    this.deleteError = ''
    this.tasksToDelete = tasks
  }

  async confirmDelete() {
    // one by one, so that a task that cannot go (it started running meanwhile) does not stop the others
    const failed: Task[] = []
    let reason = ''
    for (const task of this.tasksToDelete) {
      try {
        await api.deleteTask(task.id)
        if (this.sheetTaskId === task.id) this.sheetOpen = false
      } catch (e) {
        failed.push(task)
        reason = e instanceof Error ? e.message : 'Could not delete the task'
      }
    }
    this.tasksToDelete = failed // what is left is what could not be deleted: the question stays, with the reason
    this.deleteError = failed.length ? (failed.length === 1 ? reason : `${failed.length} tasks could not be deleted: ${reason}`) : ''
    await this.reload()
  }
}
