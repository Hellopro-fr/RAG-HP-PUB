export interface User {
  id: number
  email: string
  display_name: string
  role: 'admin' | 'read-only' | 'config-only'
  login_count: number
  last_login_at?: string
  created_at: string
}
