<script setup lang="ts">
import { collectionHref, validCollectionEntry, type CollectionEntry } from '~/lib/collections'
import type { NotebookEntry } from '~/composables/useLibrary'
const notebook = useNotebook()
const status = ref('')
const clearing = ref(false)
const editing = ref<{ id: string; title: string; snapshot: string } | null>(null)
const draft = ref('')
const originalAnnotation = ref('')
const dirty = computed(() => editing.value !== null && draft.value !== originalAnnotation.value)
const input = ref<HTMLTextAreaElement | null>(null)
// Guard only changed drafts. Opening an editor or returning to its original
// text must not interrupt ordinary navigation or attach an unload listener.
function beforeUnload(event: BeforeUnloadEvent) { event.preventDefault(); event.returnValue = '' }
watch(dirty, value => { if (value) window.addEventListener('beforeunload', beforeUnload); else window.removeEventListener('beforeunload', beforeUnload) })
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
onBeforeRouteLeave(() => !dirty.value || window.confirm('Leave without saving your personal note? Your draft will be lost.'))
let editTrigger: HTMLElement | null = null
async function edit(entry: NotebookEntry, event: Event) {
  if (editing.value) { status.value = 'Save or cancel the current edit before opening another entry.'; input.value?.focus(); return }
  editTrigger = event.currentTarget as HTMLElement
  editing.value = { id: entry.id, title: entry.title, snapshot: JSON.stringify(entry) }
  draft.value = entry.annotation ?? ''
  originalAnnotation.value = draft.value
  await nextTick()
  input.value?.focus()
}
async function cancelEdit() { editing.value = null; await nextTick(); if (editTrigger?.isConnected) editTrigger.focus() }
async function saveNote() {
  if (!editing.value) return
  const result = notebook.annotate(editing.value.id, editing.value.snapshot, draft.value)
  if (!result.updated) { status.value = 'The entry is missing, changed or has a duplicate identifier. Your draft remains here. No entry was overwritten.'; return }
  status.value = result.persisted ? 'Personal note saved in this browser.' : 'Personal note updated in memory. Browser storage could not be updated. Export the notebook before leaving.'
  await cancelEdit()
}
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
    <form v-if="editing" class="atlas-panel atlas-panel-body space-y-3" aria-label="Edit personal note" @submit.prevent="saveNote"><h2>Personal note for {{ editing.title }}</h2><p>The saved note or reference stays unchanged. This text is your own annotation.</p><label class="grid gap-2">Personal note<textarea ref="input" v-model="draft" rows="6" class="w-full border rounded p-3" /></label><div class="flex flex-wrap gap-2"><button type="submit" class="atlas-button">Save personal note</button><button type="button" class="atlas-button" @click="cancelEdit">Cancel edit</button></div></form>
    <div v-if="notebook.entries.value.length"><button v-if="!clearing" type="button" class="atlas-button" @click="clearing = true">Clear notebook</button><div v-else class="space-y-3"><p>Clear every entry in this browser? Export a copy first if you want to keep them.</p><button type="button" class="atlas-button" @click="clear">Confirm clear notebook</button><button type="button" class="atlas-button" @click="clearing = false">Cancel</button></div></div>
    <StEmptyState v-if="!notebook.entries.value.length" title="Your notebook is empty" message="Use Add note in the header or Save on an evidence record to keep a reference here." />
    <ul v-else class="space-y-4"><li v-for="(entry, index) in notebook.entries.value" :key="index" class="atlas-panel atlas-panel-body space-y-3">
      <template v-if="validCollectionEntry(entry, 'notebook')"><a :href="collectionHref(entry.href)!" class="break-words">{{ entry.title }}</a><div v-if="entry.note"><h2 class="text-sm">Saved note or reference</h2><p class="whitespace-pre-wrap break-words">{{ entry.note }}</p></div><div v-if="entry.annotation"><h2 class="text-sm">Personal note</h2><p class="whitespace-pre-wrap break-words">{{ entry.annotation }}</p></div><div class="flex flex-wrap gap-2"><button type="button" class="atlas-button" :aria-label="`Edit personal note for ${entry.title}`" @click="edit(entry, $event)">Edit personal note</button><button type="button" class="atlas-button" :aria-label="`Remove ${entry.title}`" @click="remove(entry.id)">Remove</button></div></template>
      <template v-else><p>Unrecognised stored entry. It remains in exports, but its link is unavailable.</p><pre class="whitespace-pre-wrap break-words">{{ JSON.stringify(entry, null, 2) }}</pre></template>
    </li></ul>
  </section>
</template>
