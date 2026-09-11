<script setup lang="ts">
import { parseCollection, type CollectionEntry, type CollectionKind } from '~/lib/collections'
const props = defineProps<{ kind: CollectionKind; entries: CollectionEntry[] }>()
const emit = defineEmits<{ imported: [entries: CollectionEntry[]] }>()
const status = ref('')
function download() {
  const blob = new Blob([JSON.stringify({ format: 'sectortrace-collection', version: 1, kind: props.kind, entries: props.entries }, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `sectortrace-${props.kind}.json`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    if (file.size > 10 * 1024 * 1024) throw new Error('Choose a JSON file no larger than 10 MiB. No entries were imported.')
    const entries = parseCollection(await file.text(), props.kind)
    emit('imported', entries)
    status.value = ''
  } catch (error) { status.value = error instanceof SyntaxError ? 'This file is not valid JSON. No entries were imported.' : error instanceof Error ? error.message : 'The file could not be read. No entries were imported.' }
  finally { input.value = '' }
}
</script>
<template>
  <section class="space-y-3" aria-label="Collection import and export">
    <button type="button" class="atlas-button" @click="download">Export collection JSON</button>
    <label class="grid gap-2">Import collection JSON<input type="file" accept="application/json,.json" @change="upload"></label>
    <p class="atlas-footnote">Files stay on this device. Import adds entries without replacing the collection. Exact duplicate records are skipped. Conflicting identifiers keep both records. Version-one files are supported, up to 10 MiB. Export includes the collection currently in memory, even if browser storage is unavailable.</p>
    <p v-if="status" role="status">{{ status }}</p>
  </section>
</template>
