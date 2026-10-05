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

  navigate(url: string) {
    const target = new URL(url, window.location.origin)
    if (target.pathname === this.path && target.hash === window.location.hash) return
    window.history.pushState({}, '', target.pathname + target.hash)
    this.path = target.pathname
    this.hash = target.hash.slice(1)
  }
}

export const router = new Router()
