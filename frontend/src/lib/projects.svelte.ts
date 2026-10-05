import { api, type ProjectSummary } from './api'

class Projects {
  list = $state<ProjectSummary[]>([])
  loaded = $state(false)

  async refresh() {
    try {
      this.list = await api.projects()
    } finally {
      this.loaded = true
    }
  }

  get(id: number) {
    return this.list.find((p) => p.id === id)
  }
}

export const projects = new Projects()
