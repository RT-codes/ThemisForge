import { authApi, type User } from './api/auth'
import { ApiError } from './api/core'

class Auth {
  user = $state<User | null>(null)
  loading = $state(true)
  /** No account exists yet: the first registration creates the administrator. */
  needsAdmin = $state(false)

  async init() {
    try {
      this.user = await authApi.me()
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) console.error(e)
      this.user = null
      try {
        this.needsAdmin = (await authApi.setup()).needs_admin
      } catch (err) {
        console.error(err)
      }
    } finally {
      this.loading = false
    }
  }

  async login(email: string, password: string) {
    this.user = await authApi.login(email, password)
  }

  async register(name: string, email: string, password: string) {
    this.signedIn(await authApi.register(name, email, password))
  }

  async logout() {
    await authApi.logout()
    this.user = null
    this.needsAdmin = (await authApi.setup()).needs_admin
  }

  /** For screens that create the account themselves (accepting an invite). */
  signedIn(user: User) {
    this.user = user
    this.needsAdmin = false
  }
}

export const auth = new Auth()
