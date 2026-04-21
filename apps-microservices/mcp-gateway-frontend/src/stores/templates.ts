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

  async function createInstance(params: CreateInstanceParams): Promise<TemplateInstance> {
    const instance = await templatesApi.createInstance(params)
    instances.value = [instance, ...instances.value]
    return instance
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
