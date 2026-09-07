<script setup lang="ts">
import { ref } from 'vue'
import type { DocumentContextResponse, DocumentElement } from '~/types/documents'
const props = defineProps<{ documentId: string; elementId?: string; embedded?: boolean }>()
const emit = defineEmits<{ select: [id: string | undefined] }>()
const api = usePublicApi()
const notebook = useNotebook()
const feedback = ref('')
const { data, pending, error, refresh } = await useAsyncData(() => `public-passage:${props.documentId}:${props.elementId ?? ''}`, (_app, { signal }) => api.get<DocumentContextResponse>(`/documents/${encodeURIComponent(props.documentId)}`, { query: { element_id: props.elementId || undefined, context: 8 }, signal }))
function reference(element?: DocumentElement) {
  const d = data.value
  return [d?.source_title || d?.title || props.documentId, d?.title_basis !== 'source_label' && !d?.source_title ? 'Display title, not a quoted source title' : null,
    d?.source_url, element ? `Element: ${element.document_element_id}` : null,
    element?.page_number != null ? `Page: ${element.page_number}` : null,
    d?.published_at ? `Published: ${d.published_at}` : null, d?.retrieved_at ? `Retrieved: ${d.retrieved_at}` : null].filter(Boolean).join('\n')
}
async function copy(element?: DocumentElement, passage = false) {
  try { await navigator.clipboard.writeText(`${passage ? `${element?.text ?? ''}\n\n` : ''}${reference(element)}`); feedback.value = passage ? 'Passage and reference copied.' : 'Reference copied.' }
  catch { feedback.value = 'Copy is unavailable. Select the text and source reference to copy them.' }
}
function note(element: DocumentElement) {
  const query = new URLSearchParams({ element_id: element.document_element_id })
  const saved = notebook.add({ title: data.value?.title ?? props.documentId, href: `#/documents/${encodeURIComponent(props.documentId)}?${query}`, note: `Saved passage:\n${element.text ?? ''}\n\n${reference(element)}` })
  feedback.value = saved ? 'Passage reference saved to your notebook.' : 'Reference kept for this visit. Browser storage is unavailable.'
}
function headingTag(element: DocumentElement) { return element.element_type === 'heading' ? `h${Math.max(2, Math.min(6, (element.heading_level ?? 1) + 1))}` : 'p' }
</script>
<template>
  <section class="st-passage-reader" aria-label="Document passage reader">
    <h1 v-if="!embedded && (pending || error || !data)" class="st-page-header">Document reader</h1>
    <p v-if="pending" role="status" aria-busy="true">Loading passage…</p>
    <div v-else-if="error" class="st-evidence-state" role="status"><h2>Exact passage unavailable</h2><p>Document {{ documentId }}<span v-if="elementId">, element {{ elementId }}</span> could not be loaded. Older passage links can stop resolving after a reparse. No replacement passage has been selected.</p><div class="atlas-actions"><button type="button" class="atlas-button" @click="refresh()">Retry</button><button v-if="elementId" type="button" class="atlas-button" @click="emit('select', undefined)">Open current document from the start</button></div></div>
    <template v-else-if="data">
      <header class="st-reader-header"><component :is="embedded ? 'h2' : 'h1'">{{ data.title ?? 'Document reader' }}</component><p v-if="data.title_basis !== 'source_label'" class="atlas-footnote">Display title basis: {{ data.title_basis ?? 'Not supplied' }}<span v-if="data.source_title">. Source title: {{ data.source_title }}</span></p><p class="atlas-footnote">{{ data.document_type ?? 'Document' }} · {{ data.source_system ?? 'Source system not supplied' }}</p><StProvenance :provenance="data" scope="result-window" /><p class="atlas-footnote">Parser: {{ data.parser.name ?? 'Not supplied' }} · {{ data.parser.version ?? 'Version not supplied' }}</p><div class="atlas-actions"><StLink v-if="data.source_url" :href="data.source_url">Open source document</StLink><NuxtLink :to="{ path: '/doctables', query: { document_id: documentId } }">Extracted tables</NuxtLink><button type="button" class="atlas-button" @click="copy()">Copy reference</button></div></header>
      <StCaveat :text="data.caveat" />
      <p class="atlas-footnote">{{ data.element_count ? `Elements ${data.range.from + 1} to ${data.range.to} of ${data.element_count}` : 'No extractable elements in this response' }}. This is a bounded context window.</p>
      <div class="atlas-actions"><button type="button" class="atlas-button" :disabled="!data.has_more_before" @click="emit('select', data.elements[0]?.document_element_id)">Earlier context</button><button type="button" class="atlas-button" :disabled="!data.has_more_after" @click="emit('select', data.elements.at(-1)?.document_element_id)">Later context</button></div>
      <p role="status">{{ feedback }}</p>
      <article v-for="element in data.elements" :key="element.document_element_id" class="st-document-element" :class="{ 'is-anchor': element.is_anchor }"><component :is="headingTag(element)" class="st-passage-text">{{ element.text ?? 'No text supplied for this element' }}</component><p class="atlas-footnote">{{ element.page_number != null ? `Page ${element.page_number}` : 'Page not supplied' }}<span v-if="element.is_anchor"> · Selected passage</span></p><div class="st-passage-actions"><button type="button" @click="emit('select', element.document_element_id)">Select passage</button><button type="button" @click="copy(element, true)">Copy passage</button><button type="button" @click="note(element)">Save note</button></div></article>
    </template>
  </section>
</template>
