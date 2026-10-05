import { api, ApiError, type User } from './api'

class Auth {
  user = $state<User | null>(null)
  loading = $state(true)

  async init() {
    try {
      this.user = await api.me()
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) console.error(e)
      this.user = null
    } finally {
      this.loading = false
    }
  }

  async login(email: string, password: string) {
    this.user = await api.login(email, password)
  }

  async register(name: string, email: string, password: string) {
    this.user = await api.register(name, email, password)
  }

  async logout() {
    await api.logout()
    this.user = null
  }
}

export const auth = new Auth()
