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

  taskToDelete = $state<Task | null>(null)
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

  openTask(task: Task) {
    this.sheetTaskId = task.id
    this.sheetBoardId = task.board_id
    this.sheetOpen = true
  }

  addTask(boardId: number, status: TaskStatus = 'backlog') {
    this.sheetTaskId = null
    this.sheetBoardId = boardId
    this.sheetStatus = status
    this.sheetOpen = true
  }

  async moveTask(task: Task, status: TaskStatus, position: number) {
    const before = this.tasks
    this.tasks = this.tasks.map((t) => (t.id === task.id ? { ...t, status, position } : t)) // optimistic
    try {
      await api.updateTask(task.id, { status, position })
      await this.load()
    } catch (e) {
      this.tasks = before
      this.loadError = e instanceof Error ? e.message : 'Could not move the task'
    }
  }

  askDelete(task: Task) {
    this.deleteError = ''
    this.taskToDelete = task
  }

  async confirmDelete() {
    const task = this.taskToDelete
    if (!task) return
    try {
      await api.deleteTask(task.id)
      if (this.sheetTaskId === task.id) this.sheetOpen = false
      this.taskToDelete = null
      await this.reload()
    } catch (e) {
      this.deleteError = e instanceof Error ? e.message : 'Could not delete the task'
    }
  }
}
