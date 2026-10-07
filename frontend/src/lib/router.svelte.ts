import { parse } from './routes'

class Router {
  path = $state(window.location.pathname)
  hash = $state(window.location.hash.slice(1))
  route = $derived(parse(this.path))

  constructor() {
    window.addEventListener('popstate', () => {
      this.path = window.location.pathname
      this.hash = window.location.hash.slice(1)
    })
    // plain <a href="/..."> clicks navigate without a page load
    document.addEventListener('click', (e) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      const a = (e.target as Element | null)?.closest('a')
      if (!a || a.target || a.origin !== window.location.origin || a.hasAttribute('download')) return
      if (a.pathname === this.path && a.hash) {
        // a jump to a heading on this page: let the browser scroll, just keep our state in step
        queueMicrotask(() => (this.hash = a.hash.slice(1)))
        return
      }
      e.preventDefault()
      this.navigate(a.pathname + a.hash)
    })
  }

  /** change the address without adding a history entry (a new workflow gets its real address once it is saved) */
  replace(url: string) {
    const target = new URL(url, window.location.origin)
    window.history.replaceState({}, '', target.pathname + target.hash)
    this.path = target.pathname
    this.hash = target.hash.slice(1)
  }

  /** A page with unsaved work sets this. It is asked before every in-app navigation: return true to hold the move (and
   * call `go` later if the person decides to leave), or false to let it through. The browser's own back button and
   * closing the tab cannot be held this way; a page covers those with `beforeunload`. */
  guard: ((go: () => void) => boolean) | null = null

  navigate(url: string) {
    const target = new URL(url, window.location.origin)
    if (target.pathname === this.path && target.hash === window.location.hash) return
    const go = () => {
      window.history.pushState({}, '', target.pathname + target.hash)
      this.path = target.pathname
      this.hash = target.hash.slice(1)
    }
    if (!this.guard?.(go)) go()
  }
}

export const router = new Router()
