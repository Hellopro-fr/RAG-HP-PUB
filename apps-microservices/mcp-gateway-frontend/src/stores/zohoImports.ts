import { defineStore } from 'pinia'
import { zohoImportsApi } from '@/api/zohoImports'
import type {
  ZohoImportRow,
  ZohoImportUpdateRequest,
  ZohoImportTestResponse,
  ZohoAdminUpsertRequest,
} from '@/types/zoho'

interface State {
  admin: ZohoImportRow | null
  users: ZohoImportRow[]
  usersTotal: number
  usersPage: number
  usersLimit: number
  usersSearch: string
  isLoading: boolean
  error: string | null
}

export const useZohoImportsStore = defineStore('zohoImports', {
  state: (): State => ({
    admin: null,
    users: [],
    usersTotal: 0,
    usersPage: 1,
    usersLimit: 20,
    usersSearch: '',
    isLoading: false,
    error: null,
  }),
  actions: {
    async fetchAdmin() {
      try {
        this.admin = await zohoImportsApi.getAdmin()
      } catch (e: unknown) {
        this.error = e instanceof Error ? e.message : 'Erreur de chargement'
      }
    },
    async fetchUsers(params: { page?: number; search?: string } = {}) {
      this.isLoading = true
      this.error = null
      try {
        const page = params.page ?? this.usersPage
        const search = params.search ?? this.usersSearch
        const out = await zohoImportsApi.list({ isAdmin: false, page, search, limit: this.usersLimit })
        this.users = out.rows
        this.usersTotal = out.total
        this.usersPage = out.page
        this.usersLimit = out.limit
        this.usersSearch = search
      } catch (e: unknown) {
        this.error = e instanceof Error ? e.message : 'Erreur de chargement'
      } finally {
        this.isLoading = false
      }
    },
    async upsertAdmin(payload: ZohoAdminUpsertRequest) {
      this.admin = await zohoImportsApi.upsertAdmin(payload)
    },
    async deleteAdmin() {
      await zohoImportsApi.deleteAdmin()
      this.admin = null
    },
    async updateRow(id: string, patch: ZohoImportUpdateRequest) {
      const row = await zohoImportsApi.patch(id, patch)
      if (row.is_admin) {
        this.admin = row
      } else {
        await this.fetchUsers()
      }
      return row
    },
    async deleteRow(id: string) {
      await zohoImportsApi.remove(id)
      await this.fetchUsers()
    },
    async testRow(id: string): Promise<ZohoImportTestResponse> {
      return zohoImportsApi.test(id)
    },
    async discoverRow(id: string): Promise<{ ok: boolean; tools: number }> {
      return zohoImportsApi.discover(id)
    },
    async toggleActive(id: string, active: boolean) {
      return this.updateRow(id, { is_active: active })
    },
  },
})
