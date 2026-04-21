import { defineStore } from 'pinia'
import { ref } from 'vue'
import { templatesApi } from '@/api/templates'
import type { Template, TemplateInstance, CreateInstanceParams } from '@/types/templates'

export const useTemplatesStore = defineStore('templates', () => {
  const templates = ref<Template[]>([])
  const instances = ref<TemplateInstance[]>([])
  const isLoading = ref(false)

  async function fetchTemplates(): Promise<void> {
    isLoading.value = true
    try {
      const response = await templatesApi.list()
      templates.value = response.templates
    } finally {
      isLoading.value = false
    }
  }

  async function fetchInstances(slug?: string): Promise<void> {
    isLoading.value = true
    try {
      const response = await templatesApi.listInstances(slug)
      instances.value = response.instances
    } finally {
      isLoading.value = false
    }
  }

  // Returns the created instance; does not mutate local `instances`. Callers
  // should call fetchInstances(slug) to refresh — the store has no concept of
  // "which slug is currently displayed" so a blind prepend can contaminate a
  // filtered list (see mcp-gateway-frontend/src/stores/servers.ts for the same
  // pattern in createServer).
  async function createInstance(params: CreateInstanceParams): Promise<TemplateInstance> {
    return await templatesApi.createInstance(params)
  }

  async function deleteInstance(id: string): Promise<void> {
    await templatesApi.delete(id)
    instances.value = instances.value.filter(i => i.id !== id)
  }

  async function restartInstance(id: string): Promise<void> {
    await templatesApi.restart(id)
  }

  async function rotateCredentials(id: string, credentials: File): Promise<void> {
    await templatesApi.rotate(id, credentials)
  }

  return {
    templates,
    instances,
    isLoading,
    fetchTemplates,
    fetchInstances,
    createInstance,
    deleteInstance,
    restartInstance,
    rotateCredentials
  }
})
