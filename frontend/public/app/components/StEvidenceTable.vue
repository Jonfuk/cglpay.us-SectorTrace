<script setup lang="ts" generic="Row extends object">
import { computed } from 'vue'
import type { Provenance } from '~/types/api'

// A deliberately COARSE evidence table. The plan warns against replacing one
// table row with a deep tree of wrapper components (update + memory cost), so
// this renders a flat <table> and reads cell values as text nodes. It is not a
// virtualised grid — server pagination bounds the row count, and Tabulator is
// reserved for viewport-scale rendering on the routes that need it.
//
// Every value reaches the DOM as text (never markup). A column may opt into the
// safe StLink renderer for URL cells; nothing here interpolates HTML.

export interface Column<R> {
  /** Row key to read. */
  key: Extract<keyof R, string>
  /** Header label. */
  label: string
  /** Render as a validated http(s) link (uses StLink). */
  link?: boolean
  /** Render the cell as an internal NuxtLink to the returned in-app path
   *  (e.g. an entity detail page). Returning null/undefined renders plain text.
   *  Internal paths are app-controlled, not source-derived, so they do not need
   *  the StLink external-URL validation. */
  to?: (row: R) => string | null | undefined
  /** Right-align + thousands-format numeric values. */
  numeric?: boolean
  /** Monospace (ids, hashes, dates). */
  mono?: boolean
}

const props = defineProps<{
  columns: Column<Row>[]
  rows: Row[] | null | undefined
  /** Stable row key for :key. Falls back to index if absent. */
  rowKey?: Extract<keyof Row, string>
  caption?: string
  sourceDetails?: boolean
}>()

const rowsSafe = computed<Row[]>(() => (Array.isArray(props.rows) ? props.rows : []))

function cell(row: Row, col: Column<Row>): string {
  const v = row[col.key]
  if (v === null || v === undefined || v === '') return '—'
  if (col.numeric && typeof v === 'number') return v.toLocaleString('en-GB')
  return String(v)
}

function keyFor(row: Row, i: number): string | number {
  if (props.rowKey) {
    const v = row[props.rowKey]
    if (v !== null && v !== undefined) return String(v)
  }
  return i
}
</script>

<template>
  <div class="overflow-x-auto" :tabindex="caption ? 0 : undefined" :role="caption ? 'region' : undefined" :aria-label="caption">
    <table class="w-full text-sm border-collapse">
      <caption v-if="caption" class="text-left mb-3 atlas-footnote">{{ caption }}</caption>
      <thead>
        <tr class="text-left border-b border-black/15 dark:border-white/15">
          <th
            v-for="col in columns"
            :key="col.key"
            scope="col"
            class="py-2 pr-4 font-medium opacity-70 whitespace-nowrap"
            :class="{ 'text-right': col.numeric }"
          >
            {{ col.label }}
          </th>
          <th v-if="sourceDetails" scope="col" class="py-2 pr-4 font-medium">Provenance</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, i) in rowsSafe"
          :key="keyFor(row, i)"
          class="border-b border-black/5 dark:border-white/5 align-top"
        >
          <td
            v-for="col in columns"
            :key="col.key"
            class="py-2 pr-4"
            :class="{
              'text-right tabular-nums': col.numeric,
              'font-mono text-xs': col.mono,
            }"
          >
            <StLink v-if="col.link" :href="(row[col.key] as string | null | undefined)" />
            <NuxtLink
              v-else-if="col.to && col.to(row)"
              :to="col.to(row) as string"
              class="text-[var(--st-accent)] underline underline-offset-2"
            >{{ cell(row, col) }}</NuxtLink>
            <template v-else>{{ cell(row, col) }}</template>
          </td>
          <td v-if="sourceDetails" class="py-2 pr-4"><StProvenance :provenance="row as Provenance" /></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
