import { projectsApi, type ProjectSummary } from './api/projects'

class Projects {
  list = $state<ProjectSummary[]>([])
  loaded = $state(false)

  async refresh() {
    try {
      this.list = await projectsApi.projects()
    } finally {
      this.loaded = true
    }
  }

  get(id: number) {
    return this.list.find((p) => p.id === id)
  }
}

export const projects = new Projects()
