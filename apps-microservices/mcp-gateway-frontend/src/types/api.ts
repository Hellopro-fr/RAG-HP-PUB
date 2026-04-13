export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body?: unknown
  ) {
    super(`API Error ${status}: ${statusText}`)
    this.name = 'ApiError'
  }
}

export interface ApiListResponse<T> {
  total?: number
  [key: string]: T[] | number | undefined
}
