import { api, ApiError, type User } from './api'

class Auth {
  user = $state<User | null>(null)
  loading = $state(true)
  /** No account exists yet: the first registration creates the administrator. */
  needsAdmin = $state(false)

  async init() {
    try {
      this.user = await api.me()
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) console.error(e)
      this.user = null
      try {
        this.needsAdmin = (await api.setup()).needs_admin
      } catch (err) {
        console.error(err)
      }
    } finally {
      this.loading = false
    }
  }

  async login(email: string, password: string) {
    this.user = await api.login(email, password)
  }

  async register(name: string, email: string, password: string) {
    this.signedIn(await api.register(name, email, password))
  }

  async logout() {
    await api.logout()
    this.user = null
    this.needsAdmin = (await api.setup()).needs_admin
  }

  /** For screens that create the account themselves (accepting an invite). */
  signedIn(user: User) {
    this.user = user
    this.needsAdmin = false
  }
}

export const auth = new Auth()
