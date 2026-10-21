import { projectsApi, type Workspace } from './api/projects'

/** The workspaces and boards of every project that was opened, shared by the sidebar, the top bar and the pages so they
 *  all show the same thing. A page that changes them refreshes the project here. */
class Structure {
  private byProject = $state<Record<number, Workspace[]>>({})

  get(projectId: number): Workspace[] | undefined {
    return this.byProject[projectId]
  }

  async refresh(projectId: number): Promise<Workspace[]> {
    const workspaces = await projectsApi.workspaces(projectId)
    this.byProject[projectId] = workspaces
    return workspaces
  }
}

export const structure = new Structure()
