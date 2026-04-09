<template>
  <div class="flex items-center justify-center mb-8">
    <template v-for="(step, index) in steps" :key="index">
      <!-- Connector line (not before first step) -->
      <div
        v-if="index > 0"
        class="h-0.5 w-16 mx-2"
        :class="[
          index <= currentStep || completedSteps.includes(index)
            ? 'bg-blue-600'
            : 'bg-gray-200'
        ]"
      />
      <!-- Step circle + label -->
      <button
        type="button"
        class="flex flex-col items-center gap-1.5"
        :class="[
          completedSteps.includes(index) ? 'cursor-pointer' : 'cursor-default'
        ]"
        :disabled="!completedSteps.includes(index) && index !== currentStep"
        @click="handleClick(index)"
      >
        <div
          class="w-9 h-9 rounded-full flex items-center justify-center text-sm font-semibold transition-colors"
          :class="stepCircleClass(index)"
        >
          <i v-if="completedSteps.includes(index) && index !== currentStep" class="pi pi-check text-xs" />
          <span v-else>{{ index + 1 }}</span>
        </div>
        <span
          class="text-xs font-medium whitespace-nowrap"
          :class="stepLabelClass(index)"
        >
          {{ step }}
        </span>
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  steps: string[]
  currentStep: number
  completedSteps?: number[]
}>(), {
  completedSteps: () => []
})

const emit = defineEmits<{
  'update:currentStep': [step: number]
}>()

function stepCircleClass(index: number): string {
  if (index === props.currentStep) {
    return 'bg-blue-600 text-white'
  }
  if (props.completedSteps.includes(index)) {
    return 'bg-green-500 text-white'
  }
  return 'bg-gray-200 text-gray-500'
}

function stepLabelClass(index: number): string {
  if (index === props.currentStep) {
    return 'text-blue-600'
  }
  if (props.completedSteps.includes(index)) {
    return 'text-green-600'
  }
  return 'text-gray-400'
}

function handleClick(index: number) {
  if (props.completedSteps.includes(index) && index !== props.currentStep) {
    emit('update:currentStep', index)
  }
}
</script>
