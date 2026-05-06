import { defineStore } from 'pinia'
import { ref } from 'vue'
import { serversApi, type ServerListFilters } from '@/api/servers'
import type { Server } from '@/types/server'

export const useServersStore = defineStore('servers', () => {
  const servers = ref<Server[]>([])
  const tags = ref<string[]>([])
  const isLoading = ref(false)

  async function fetchServers(filters?: ServerListFilters): Promise<void> {
    isLoading.value = true
    try {
      const response = await serversApi.list(filters)
      servers.value = response.servers
    } finally {
      isLoading.value = false
    }
  }

  async function fetchTags(): Promise<void> {
    tags.value = await serversApi.listTags()
  }

  function patchServer(updated: Server): void {
    const idx = servers.value.findIndex(s => s.id === updated.id)
    if (idx >= 0) servers.value[idx] = updated
  }

  async function createServer(data: Parameters<typeof serversApi.create>[0]): Promise<Server> {
    const server = await serversApi.create(data)
    // List refetch — current filter may be active, blind prepend can contaminate
    // a filtered view (and tags may have changed).
    await fetchServers()
    return server
  }

  async function updateServer(id: string, data: Parameters<typeof serversApi.update>[1]): Promise<Server> {
    const server = await serversApi.update(id, data)
    patchServer(server)
    return server
  }

  async function deleteServer(id: string): Promise<void> {
    await serversApi.delete(id)
    servers.value = servers.value.filter(s => s.id !== id)
  }

  async function toggleServer(id: string, enable: boolean): Promise<void> {
    if (enable) {
      await serversApi.enable(id)
    } else {
      await serversApi.disable(id)
    }
    // enable/disable return void — fetch the single row to patch in place.
    const fresh = await serversApi.get(id)
    patchServer(fresh)
  }

  async function discoverServer(id: string): Promise<void> {
    const fresh = await serversApi.discover(id)
    patchServer(fresh)
  }

  async function discoverAll(): Promise<void> {
    await serversApi.discoverAll()
    // Cluster-wide refresh — every row's discovered tool set may have changed.
    await fetchServers()
  }

  async function importServers(json: unknown, autoDiscover?: boolean) {
    const result = await serversApi.import(json, autoDiscover)
    // Bulk insert — refetch to surface new rows under the active filter.
    await fetchServers()
    return result
  }

  return {
    servers,
    tags,
    isLoading,
    fetchServers,
    fetchTags,
    createServer,
    updateServer,
    deleteServer,
    toggleServer,
    discoverServer,
    discoverAll,
    importServers
  }
})
