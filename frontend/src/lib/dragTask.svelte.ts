import type { Task } from './api'

/** The card being dragged. It lives outside any one board so that a card picked up on one board can be dropped on
 *  another board of the same page; each board only needs to ask what is being dragged. */
class DragTask {
  task = $state<Task | null>(null)

  start(task: Task) {
    this.task = task
  }

  end() {
    this.task = null
  }
}

export const dragTask = new DragTask()
