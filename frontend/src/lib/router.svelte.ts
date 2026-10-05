export type Route =
  | { name: 'home' }
  | { name: 'project'; id: number }
  | { name: 'settings' }
  | { name: 'access' }
  | { name: 'invite'; token: string }
  | { name: 'not-found' }

function parse(path: string): Route {
  if (path === '/' || path === '') return { name: 'home' }
  if (path === '/settings') return { name: 'settings' }
  if (path === '/access') return { name: 'access' }
  const invite = path.match(/^\/invite\/([\w-]+)\/?$/)
  if (invite) return { name: 'invite', token: invite[1] }
  const m = path.match(/^\/projects\/(\d+)\/?$/)
  if (m) return { name: 'project', id: Number(m[1]) }
  return { name: 'not-found' }
}

class Router {
  path = $state(window.location.pathname)
  route = $derived(parse(this.path))

  constructor() {
    window.addEventListener('popstate', () => (this.path = window.location.pathname))
    // plain <a href="/..."> clicks navigate without a page load
    document.addEventListener('click', (e) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      const a = (e.target as Element | null)?.closest('a')
      if (!a || a.target || a.origin !== window.location.origin || a.hasAttribute('download')) return
      e.preventDefault()
      this.navigate(a.pathname)
    })
  }

  navigate(path: string) {
    if (path === this.path) return
    window.history.pushState({}, '', path)
    this.path = path
  }
}

export const router = new Router()
