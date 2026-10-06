import { emptyColumn, emptyView, parseStored, toggled, type BoardView, type ColumnView } from './boardView'

/** what one project's board is showing, kept in this browser so it is still there after a reload */
export class BoardViewStore {
  board = $state<BoardView>(emptyView())
  columns = $state<Record<string, ColumnView>>({})
  /** statuses whose column is not shown on the board */
  hidden = $state<string[]>([])
  private key: string

  constructor(projectId: number) {
    this.key = `themis.board.${projectId}`
    try {
      const stored = parseStored(localStorage.getItem(this.key))
      this.board = stored.board
      this.columns = stored.columns
      this.hidden = stored.hidden
    } catch {
      // no storage: the board simply starts unfiltered
    }
  }

  column(status: string): ColumnView {
    return this.columns[status] ?? emptyColumn()
  }

  setBoard(patch: Partial<BoardView>) {
    this.board = { ...this.board, ...patch }
    this.save()
  }

  setColumn(status: string, patch: Partial<ColumnView>) {
    this.columns = { ...this.columns, [status]: { ...this.column(status), ...patch } }
    this.save()
  }

  toggleHidden(status: string) {
    this.hidden = toggled(this.hidden, status)
    this.save()
  }

  showAll() {
    this.hidden = []
    this.save()
  }

  resetColumn(status: string) {
    const { [status]: _gone, ...rest } = this.columns
    this.columns = rest
    this.save()
  }

  reset() {
    this.board = emptyView()
    this.columns = {}
    this.save() // the statuses you chose to hide stay hidden: that is a layout choice, not a filter
  }

  private save() {
    try {
      localStorage.setItem(this.key, JSON.stringify({ board: this.board, columns: this.columns, hidden: this.hidden }))
    } catch {
      // remembering is a convenience
    }
  }
}
