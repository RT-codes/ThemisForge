// Shared folders and the files in them (backend/app/routers/volumes.py).

import { ApiError, failure, request, send } from './core'

export interface MountRoot {
  path: string
  allow_write: boolean
}

export interface Volume {
  id: number
  project_id: number
  name: string
  kind: 'managed' | 'host' | 'config' // config: the project's own agents, skills and tools, never mounted
  host_path: string
  mode: 'ro' | 'rw'
  exclusive_write: boolean
  created_at: string
  is_default: boolean
  problem: string | null
  can_write: boolean
}

export interface FileEntry {
  name: string
  is_dir: boolean
  size: number
  modified: string
}

export interface FolderListing {
  path: string
  entries: FileEntry[]
  writable: boolean // the folder allows changes
  runs: { task_id: number; title: string }[] // the runs using it: while there are any, it is locked
}

export interface VolumeInput {
  name: string
  kind?: 'managed' | 'host'
  host_path?: string
  mode?: 'ro' | 'rw'
  exclusive_write?: boolean | null
}

export interface MountRef {
  volume_id: number
  mode: 'ro' | 'rw'
}

/** where a file can be shown or downloaded from; the browser fetches it with the session cookie */
// `version` (the file's modified time) is ignored by the server; it only makes the browser fetch the file again after it changed
const fileUrl = (id: number, path: string, download = false, version = '') =>
  `/api/volumes/${id}/file?path=${encodeURIComponent(path)}${download ? '&download=true' : ''}${version ? `&v=${encodeURIComponent(version)}` : ''}`

export const volumesApi = {
  /** The shared folders; the Files page also asks for the config folder, which pickers must never offer. */
  volumes: (projectId: number, includeConfig = false) => request<Volume[]>(`/projects/${projectId}/volumes${includeConfig ? '?include_config=true' : ''}`),
  configFolder: (projectId: number) => request<Volume>(`/projects/${projectId}/config`),
  createVolume: (projectId: number, body: VolumeInput) => request<Volume>(`/projects/${projectId}/volumes`, send('POST', body)),
  updateVolume: (id: number, patch: { name?: string; mode?: 'ro' | 'rw'; exclusive_write?: boolean }) => request<Volume>(`/volumes/${id}`, send('PATCH', patch)),
  deleteVolume: (id: number) => request<void>(`/volumes/${id}`, send('DELETE')),
  /** A folder's contents. Pass the `etag` of the last answer: if nothing changed since, the server sends no body and
   * this returns null, so watching a folder is cheap. */
  listFiles: async (id: number, path: string, etag = ''): Promise<{ listing: FolderListing; etag: string } | null> => {
    const res = await fetch(`/api/volumes/${id}/files?path=${encodeURIComponent(path)}`, {
      headers: etag ? { 'If-None-Match': etag } : {},
      cache: 'no-store', // the conditional request is ours; the browser's own cache must not answer instead
    })
    if (res.status === 304) return null
    if (!res.ok) throw await failure(res)
    return { listing: await res.json(), etag: res.headers.get('ETag') ?? '' }
  },
  fileUrl,
  readFileText: async (id: number, path: string) => {
    const res = await fetch(fileUrl(id, path), { cache: 'no-store' }) // a file that was just saved must not come from the cache
    if (!res.ok) throw new ApiError(res.status, res.statusText)
    return res.text()
  },
  /** `base`: the modified time the file had when it was opened; the save is refused (412) if it changed since */
  uploadFile: (id: number, path: string, file: File, overwrite = false, base = '') =>
    request<void>(`/volumes/${id}/file?path=${encodeURIComponent(path)}&overwrite=${overwrite}${base ? `&base=${encodeURIComponent(base)}` : ''}`, {
      method: 'PUT',
      body: file,
      headers: { 'Content-Type': 'application/octet-stream' },
    }),
  createFolder: (id: number, path: string) => request<void>(`/volumes/${id}/folder`, send('POST', { path })),
  moveFile: (id: number, source: string, destination: string) => request<void>(`/volumes/${id}/move`, send('POST', { source, destination })),
  deleteFile: (id: number, path: string) => request<void>(`/volumes/${id}/file?path=${encodeURIComponent(path)}`, send('DELETE')),
}
