import { ref, computed } from 'vue'
import type { Server } from '@/types/server'

export interface DragDropServer {
  id: string
  name: string
  tools: DragDropTool[]
}

export interface DragDropTool {
  serverId: string
  name: string
  description?: string
}

export function useDragDrop() {
  const available = ref<DragDropServer[]>([])
  const selected = ref<DragDropServer[]>([])
  const availableSearch = ref('')
  const selectedSearch = ref('')

  const selectedCount = computed(() => {
    const srvCount = selected.value.length
    const toolCount = selected.value.reduce((sum, s) => sum + s.tools.length, 0)
    return { servers: srvCount, tools: toolCount }
  })

  function init(servers: Server[]) {
    console.log('[useDragDrop] init called with', servers.length, 'servers, active:', servers.filter(s => s.is_active).length, 'first server tools:', servers[0]?.tool_names?.length)
    const mapped = servers
      .filter(s => s.is_active)
      .map(s => ({
        id: s.id,
        name: s.name,
        tools: (s.tool_names || [])
          .filter(t => t.is_active)
          .map(t => ({
            serverId: s.id,
            name: t.name,
            description: t.description
          }))
      }))
    console.log('[useDragDrop] mapped available:', mapped.length, 'servers, first tools:', mapped[0]?.tools?.length)
    available.value = mapped
    selected.value = []
  }

  function initWithSelection(servers: Server[], serverIds: string[], serverTools?: { server_id: string; tool_names: string[] }[]) {
    console.log('[useDragDrop] initWithSelection called with', servers.length, 'servers, selectedIds:', serverIds, 'serverTools:', JSON.stringify(serverTools), 'active:', servers.filter(s => s.is_active).length)
    const firstSelected = servers.find(s => serverIds.includes(s.id))
    if (firstSelected) {
      console.log('[useDragDrop] first selected server tool_names:', firstSelected.tool_names?.map(t => t.name))
    }
    // Build a prefix map: serverId → tool_prefix
    const prefixMap = new Map<string, string>()
    for (const s of servers) {
      if (s.tool_prefix) prefixMap.set(s.id, s.tool_prefix)
    }

    const allServers = servers.filter(s => s.is_active).map(s => ({
      id: s.id,
      name: s.name,
      tools: (s.tool_names || []).filter(t => t.is_active).map(t => ({
        serverId: s.id,
        name: t.name,
        description: t.description
      }))
    }))

    selected.value = []
    available.value = []

    // Helper: check if a prefixed tool name matches an unprefixed scope name
    function toolMatchesScope(prefixedName: string, scopeName: string, serverId: string): boolean {
      if (prefixedName === scopeName) return true
      const prefix = prefixMap.get(serverId)
      if (prefix) {
        // Strip prefix: "ringovers_get_calls" → "get_calls"
        const unprefixed = prefixedName.startsWith(prefix + '_')
          ? prefixedName.substring(prefix.length + 1)
          : prefixedName
        return unprefixed === scopeName
      }
      return false
    }

    for (const srv of allServers) {
      const isSelected = serverIds.includes(srv.id)
      if (isSelected) {
        const toolScope = serverTools?.find(st => st.server_id === srv.id)
        if (toolScope && toolScope.tool_names.length > 0) {
          const selectedTools = srv.tools.filter(t =>
            toolScope.tool_names.some(scopeName => toolMatchesScope(t.name, scopeName, srv.id))
          )
          const remainingTools = srv.tools.filter(t =>
            !toolScope.tool_names.some(scopeName => toolMatchesScope(t.name, scopeName, srv.id))
          )
          if (selectedTools.length > 0) {
            selected.value.push({ ...srv, tools: selectedTools })
          }
          if (remainingTools.length > 0) {
            available.value.push({ ...srv, tools: remainingTools })
          }
        } else {
          selected.value.push(srv)
        }
      } else {
        available.value.push(srv)
      }
    }
    console.log('[useDragDrop] result: available=', available.value.length, 'selected=', selected.value.length, 'selectedTools:', selected.value.map(s => s.id + ':' + s.tools.length))
  }

  function moveAllToSelected() {
    selected.value.push(...available.value)
    available.value = []
  }

  function moveAllToAvailable() {
    available.value.push(...selected.value)
    selected.value = []
  }

  function getServerIds(): string[] {
    return selected.value.map(s => s.id)
  }

  function getServerTools(): { server_id: string; tool_names: string[] }[] {
    return selected.value.map(s => ({
      server_id: s.id,
      tool_names: s.tools.map(t => t.name)
    }))
  }

  const filteredAvailable = computed(() => {
    if (!availableSearch.value) return available.value
    const q = availableSearch.value.toLowerCase()
    return available.value
      .map(s => ({
        ...s,
        tools: s.tools.filter(t => t.name.toLowerCase().includes(q))
      }))
      .filter(s => s.name.toLowerCase().includes(q) || s.tools.length > 0)
  })

  const filteredSelected = computed(() => {
    if (!selectedSearch.value) return selected.value
    const q = selectedSearch.value.toLowerCase()
    return selected.value
      .map(s => ({
        ...s,
        tools: s.tools.filter(t => t.name.toLowerCase().includes(q))
      }))
      .filter(s => s.name.toLowerCase().includes(q) || s.tools.length > 0)
  })

  return {
    available,
    selected,
    availableSearch,
    selectedSearch,
    selectedCount,
    filteredAvailable,
    filteredSelected,
    init,
    initWithSelection,
    moveAllToSelected,
    moveAllToAvailable,
    getServerIds,
    getServerTools
  }
}
