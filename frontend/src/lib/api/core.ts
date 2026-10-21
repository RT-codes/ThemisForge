// What every area of the client shares: the error type and the one place that calls fetch.

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

/** the error for a response that was not ok, with the server's own explanation */
export async function failure(res: Response): Promise<ApiError> {
  let detail = res.statusText
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') detail = body.detail
    else if (Array.isArray(body.detail)) detail = body.detail[0]?.msg?.replace(/^Value error, /, '') ?? detail
  } catch {
    // non-JSON error body
  }
  return new ApiError(res.status, detail)
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) throw await failure(res)
  return res.status === 204 ? (undefined as T) : res.json()
}

export const send = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
})
