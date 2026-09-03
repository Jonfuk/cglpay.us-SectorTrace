<script setup lang="ts">
import { computed } from 'vue'

// A single figure: label, value, and (optionally) the caveat that bounds how it
// may be read. Crucially, a null/undefined value renders as an em dash, NOT as
// zero — "we do not have this" and "this is zero" are different claims, and the
// portal must never collapse the former into the latter.
const props = defineProps<{
  label: string
  value: number | string | null | undefined
  /** Optional unit/suffix rendered after the value (e.g. "providers"). */
  unit?: string
  caveat?: string | null
  /** Format a number with thousands separators. Default true for numbers. */
  format?: boolean
}>()

const display = computed<string>(() => {
  const v = props.value
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'number' && (props.format ?? true)) {
    return v.toLocaleString('en-GB')
  }
  return String(v)
})

const isMissing = computed(() => display.value === '—')
</script>

<template>
  <div class="space-y-1">
    <div class="text-2xl font-semibold tabular-nums" :class="{ 'opacity-40': isMissing }">
      {{ display }}<span v-if="unit && !isMissing" class="text-base font-normal opacity-60"> {{ unit }}</span>
    </div>
    <div class="text-xs uppercase tracking-wide opacity-60">{{ label }}</div>
    <StCaveat :text="caveat" />
  </div>
</template>
