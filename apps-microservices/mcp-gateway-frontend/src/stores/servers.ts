import { defineStore } from 'pinia'
import { ref } from 'vue'
import { serversApi } from '@/api/servers'
import type { Server } from '@/types/server'

export const useServersStore = defineStore('servers', () => {
  const servers = ref<Server[]>([])
  const tags = ref<string[]>([])
  const isLoading = ref(false)

  async function fetchServers(filters?: { is_active?: string; tag?: string }): Promise<void> {
    isLoading.value = true
    try {
      const response = await serversApi.list(filters)
      console.log('[serversStore] API response:', JSON.stringify(response).substring(0, 500))
      console.log('[serversStore] servers count:', response.servers?.length, 'first server tool_names:', response.servers?.[0]?.tool_names?.length)
      servers.value = response.servers
    } finally {
      isLoading.value = false
    }
  }

  async function fetchTags(): Promise<void> {
    tags.value = await serversApi.listTags()
  }

  async function createServer(data: Parameters<typeof serversApi.create>[0]): Promise<Server> {
    const server = await serversApi.create(data)
    await fetchServers()
    return server
  }

  async function updateServer(id: string, data: Parameters<typeof serversApi.update>[1]): Promise<Server> {
    const server = await serversApi.update(id, data)
    await fetchServers()
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
    await fetchServers()
  }

  async function discoverServer(id: string): Promise<void> {
    await serversApi.discover(id)
    await fetchServers()
  }

  async function discoverAll(): Promise<void> {
    await serversApi.discoverAll()
    await fetchServers()
  }

  async function importServers(json: unknown, autoDiscover?: boolean) {
    const result = await serversApi.import(json, autoDiscover)
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
