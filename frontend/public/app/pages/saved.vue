<script setup lang="ts">
import { collectionHref, validCollectionEntry, type CollectionEntry } from '~/lib/collections'
import type { SavedSearch } from '~/composables/useLibrary'
const saved = useSavedSearches()
const status = ref('')
function imported(entries: CollectionEntry[]) {
  const result = saved.importEntries(entries as SavedSearch[])
  status.value = `${result.added} ${result.added === 1 ? 'entry' : 'entries'} added. ${result.skipped} exact ${result.skipped === 1 ? 'duplicate' : 'duplicates'} skipped. ${result.persisted ? 'Collection saved in this browser.' : 'Browser storage is unavailable. Export this collection before leaving this view.'}`
}
function remove(id: string) { status.value = saved.remove(id) ? 'View removed from this browser.' : 'View removed from memory. Browser storage could not be updated. Export the current collection before leaving.' }
useHead({ title: 'Saved views · SectorTrace' })
</script>
<template>
  <section class="space-y-6">
    <header class="st-page-header"><h1>Saved views</h1><p>Named links to your selected evidence, kept in this browser. They are not synchronised to an account.</p></header>
    <StCollectionTransfer kind="saved" :entries="saved.searches.value" @imported="imported" />
    <p v-if="status" role="status">{{ status }}</p>
    <StEmptyState v-if="!saved.searches.value.length" title="No saved views" message="Use Save view in the header to keep the current selection here." />
    <ul v-else class="space-y-4"><li v-for="(entry, index) in saved.searches.value" :key="index" class="atlas-panel atlas-panel-body space-y-3">
      <template v-if="validCollectionEntry(entry, 'saved')"><a :href="collectionHref(entry.href)!" class="break-words">{{ entry.label }}</a><div><button type="button" class="atlas-button" :aria-label="`Remove ${entry.label}`" @click="remove(entry.id)">Remove</button></div></template>
      <template v-else><p>Unrecognised stored entry. It remains in exports, but its link is unavailable.</p><pre class="whitespace-pre-wrap break-words">{{ JSON.stringify(entry, null, 2) }}</pre></template>
    </li></ul>
  </section>
</template>
