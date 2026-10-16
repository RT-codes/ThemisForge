/** A message that pops up in the corner of the page and goes away by itself (see Toasts.svelte). Clicking it runs
 * `onSelect`, so a toast can take the person straight to what it is about. */
export interface Toast {
  id: number
  title: string
  body?: string
  /** a smaller line under the body: where it comes from */
  meta?: string
  /** 'attention' is for something that waits for a person */
  tone?: 'default' | 'attention'
  onSelect?: () => void
  /** how long it stays; the timer stops while the pointer or the keyboard is on it */
  ms?: number
}

class Toasts {
  list = $state<Toast[]>([])
  #next = 1
  static MAX = 4 // more than this and the oldest make room: the corner is not a log

  push(toast: Omit<Toast, 'id'>): number {
    const id = this.#next++
    this.list = [...this.list, { ms: 10_000, ...toast, id }].slice(-Toasts.MAX)
    return id
  }

  dismiss(id: number) {
    this.list = this.list.filter((t) => t.id !== id)
  }

  /** takes down every toast of a tone (the panel they all lead to has just opened) */
  dismissTone(tone: NonNullable<Toast['tone']>) {
    this.list = this.list.filter((t) => t.tone !== tone)
  }
}

export const toasts = new Toasts()
