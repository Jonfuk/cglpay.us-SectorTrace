<script setup lang="ts">
import { collectionHref, validCollectionEntry, type CollectionEntry } from '~/lib/collections'
import type { NotebookEntry } from '~/composables/useLibrary'
const notebook = useNotebook()
const status = ref('')
const clearing = ref(false)
function imported(entries: CollectionEntry[]) {
  const result = notebook.importEntries(entries as NotebookEntry[])
  status.value = `${result.added} ${result.added === 1 ? 'entry' : 'entries'} added. ${result.skipped} exact ${result.skipped === 1 ? 'duplicate' : 'duplicates'} skipped. ${result.persisted ? 'Notebook saved in this browser.' : 'Browser storage is unavailable. Export this notebook before leaving this view.'}`
}
function remove(id: string) { status.value = notebook.remove(id) ? 'Entry removed from this browser.' : 'Entry removed from memory. Browser storage could not be updated. Export the current notebook before leaving.' }
function clear() { status.value = notebook.clear() ? 'Notebook cleared in this browser.' : 'Notebook cleared in memory. Browser storage could not be updated.'; clearing.value = false }
useHead({ title: 'Notebook · SectorTrace' })
</script>
<template>
  <section class="space-y-6">
    <header class="st-page-header"><h1>Notebook</h1><p>Notes and evidence references kept in this browser. They are not synchronised to an account. Saved references remain as recorded even if their sources later change.</p></header>
    <StCollectionTransfer kind="notebook" :entries="notebook.entries.value" @imported="imported" />
    <p v-if="status" role="status">{{ status }}</p>
    <div v-if="notebook.entries.value.length"><button v-if="!clearing" type="button" class="atlas-button" @click="clearing = true">Clear notebook</button><div v-else class="space-y-3"><p>Clear every entry in this browser? Export a copy first if you want to keep them.</p><button type="button" class="atlas-button" @click="clear">Confirm clear notebook</button><button type="button" class="atlas-button" @click="clearing = false">Cancel</button></div></div>
    <StEmptyState v-if="!notebook.entries.value.length" title="Your notebook is empty" message="Use Add note in the header or Save on an evidence record to keep a reference here." />
    <ul v-else class="space-y-4"><li v-for="(entry, index) in notebook.entries.value" :key="index" class="atlas-panel atlas-panel-body space-y-3">
      <template v-if="validCollectionEntry(entry, 'notebook')"><a :href="collectionHref(entry.href)!" class="break-words">{{ entry.title }}</a><div v-if="entry.note"><h2 class="text-sm">Saved note or reference</h2><p class="whitespace-pre-wrap break-words">{{ entry.note }}</p></div><button type="button" class="atlas-button" :aria-label="`Remove ${entry.title}`" @click="remove(entry.id)">Remove</button></template>
      <template v-else><p>Unrecognised stored entry. It remains in exports, but its link is unavailable.</p><pre class="whitespace-pre-wrap break-words">{{ JSON.stringify(entry, null, 2) }}</pre></template>
    </li></ul>
  </section>
</template>
