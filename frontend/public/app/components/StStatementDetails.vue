<script setup lang="ts">
import type { ClaimRow } from '~/types/api'
const props = defineProps<{ statement: ClaimRow }>()
const filters = useFilterState()
const citations = computed(() => Array.isArray(props.statement.citations) ? props.statement.citations : null)
const identity = (citation: ClaimRow['citations'][number]) => JSON.stringify([citation.table ?? null, citation.key ?? null])
const requested = computed(() => String(filters.get('citation') ?? ''))
const matches = computed(() => requested.value ? (citations.value ?? []).filter(citation => identity(citation) === requested.value) : [])
const selected = computed(() => matches.value.length === 1 ? matches.value[0] : undefined)
const offset = computed(() => { const n = Number(filters.get('citation_offset') ?? 0); return Number.isSafeInteger(n) && n >= 0 ? n : 0 })
const displayed = computed(() => (citations.value ?? []).slice(offset.value, offset.value + 25))
async function select(citation: ClaimRow['citations'][number]) { await filters.set('citation', identity(citation)); await nextTick(); document.getElementById('statement-citation-heading')?.focus() }
</script>
<template>
  <div class="space-y-4">
    <p class="st-statement-text">{{ statement.claim_text ?? 'Statement text not supplied.' }}</p>
    <p>Authored by {{ statement.created_by ?? 'not supplied' }}. Created: {{ statement.created_at ?? 'not supplied' }}.</p>
    <p>Publication approved by {{ statement.published_by ?? 'not supplied' }}. Published: {{ statement.published_at ?? 'not supplied' }}.</p>
    <p v-if="statement.note != null" class="st-statement-text">Statement note: {{ statement.note }}</p>
    <h3>Statement caveats</h3><p v-if="!Array.isArray(statement.caveats)">The statement caveat array was not supplied.</p><p v-else-if="!statement.caveats.length">No statement-specific caveats were returned. The campaign statement caveat still applies.</p><p v-for="(caveat, index) in Array.isArray(statement.caveats) ? statement.caveats : []" :key="index" class="atlas-caveat st-statement-text">{{ caveat }}</p>
    <h3>Citations</h3><p v-if="!citations" role="status">The citation array was not supplied. Supporting evidence cannot be assessed from this response.</p><p v-else-if="!citations.length" role="status">No citations were returned for this published statement.</p>
    <template v-else><p class="atlas-footnote">{{ citations.length }} returned citation entries. Resolving a citation means the cited row is available. It does not automatically verify the statement.</p><ol class="st-statement-citations" :start="offset + 1"><li v-for="(citation, index) in displayed" :key="`${identity(citation)}:${index}`"><p>{{ citation.resolved?.label ?? 'Citation label not supplied' }}</p><p class="atlas-footnote">{{ citation.table ?? 'Table not supplied' }} · {{ citation.key ?? 'Key not supplied' }}</p><p v-if="citation.resolved === null" class="atlas-caveat">Unresolved citation. The cited evidence row is no longer held.</p><p v-else-if="!citation.resolved" class="atlas-caveat">Citation resolution was not supplied.</p><button type="button" class="atlas-button" :aria-label="`Inspect citation ${offset + index + 1}`" :aria-pressed="requested === identity(citation)" @click="select(citation)">Inspect citation</button></li></ol><p v-if="!displayed.length">No citations on this display page.</p><nav class="flex gap-2" aria-label="Citation display pages"><button type="button" class="atlas-button" :disabled="!offset" @click="filters.set('citation_offset', String(Math.max(0, offset - 25)))">Previous citations</button><button type="button" class="atlas-button" :disabled="offset + 25 >= citations.length" @click="filters.set('citation_offset', String(offset + 25))">Next citations</button></nav></template>
    <section v-if="requested" class="space-y-3" aria-label="Selected statement citation"><h3 id="statement-citation-heading" tabindex="-1">Selected citation</h3><p v-if="!selected" role="status">The saved table and key do not identify one citation in this statement. No replacement has been selected.</p><template v-else><dl><dt>Evidence table</dt><dd>{{ selected.table ?? 'Not supplied' }}</dd><dt>Evidence key</dt><dd>{{ selected.key ?? 'Not supplied' }}</dd></dl><template v-if="selected.resolved"><p>{{ selected.resolved.label ?? 'Citation label not supplied' }}</p><StResearchLink v-if="selected.resolved.url" :href="selected.resolved.url">Open cited evidence</StResearchLink><p v-else>No destination link was supplied for this cited row.</p><StProvenance :provenance="selected.resolved" /><p class="atlas-footnote">The citation response does not include a payload hash. The statement publication date is not the source retrieval date.</p></template><p v-else-if="selected.resolved === null" class="atlas-caveat">Unresolved citation. The cited evidence row is no longer held. Its original table and key remain visible.</p><p v-else class="atlas-caveat">Citation resolution was not supplied.</p></template></section>
  </div>
</template>
<style scoped>
.st-statement-text { white-space: pre-wrap; overflow-wrap: anywhere; }
.st-statement-citations { padding-left: 20px; } li { margin: 16px 0; overflow-wrap: anywhere; } li button { margin-top: 8px; }
dt { color: var(--text-muted); margin-top: 10px; } dd { overflow-wrap: anywhere; }
</style>
