<script setup lang="ts">
import type { Protocol } from '@/types/apiCatalog'

const props = defineProps<{ protocol: Protocol }>()

const clsMap: Record<Protocol, string> = {
  rest: 'bg-blue-100 text-blue-700',
  ws: 'bg-purple-100 text-purple-700',
  grpc: 'bg-green-100 text-green-700',
}

const labelMap: Record<Protocol, string> = {
  rest: 'REST',
  ws: 'WS',
  grpc: 'gRPC',
}
</script>
<template>
  <span
    class="inline-flex px-2 py-0.5 text-xs font-medium rounded"
    :class="clsMap[props.protocol]"
  >
    {{ labelMap[props.protocol] }}
  </span>
</template>
