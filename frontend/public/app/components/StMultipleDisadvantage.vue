<script setup lang="ts">
import type { Column } from '~/components/StEvidenceTable.vue'

type Row = Record<string, unknown>
const props = defineProps<{ comparator?: { rows?: Row[]; caveat?: string | null } }>()
const rows = computed(() => (props.comparator?.rows ?? []).map((row, index) => ({ ...row, row_key: index })))
const stages = [
  { key: 'assessed', label: 'Assessed as owed a duty' },
  { key: 'prevention_secured', label: 'Accommodation secured after prevention duty' },
  { key: 'relief_secured', label: 'Accommodation secured after relief duty' },
]
const columns: Column<Row>[] = [
  { key: 'quarter_label', label: 'Quarter' },
  { key: 'md_pct_text', label: 'Published percentage' },
  { key: 'assessed_md_total_text', label: 'Assessed as owed a duty' },
  { key: 'prevention_secured_md_total_text', label: 'Accommodation secured after prevention duty' },
  { key: 'relief_secured_md_total_text', label: 'Accommodation secured after relief duty' },
]
function categoryColumns(stage: string): Column<Row>[] {
  return [
    { key: 'quarter_label', label: 'Quarter' },
    { key: stage + '_md_total_text', label: 'Multiple disadvantage total' },
    { key: stage + '_domestic_abuse_total_text', label: 'Domestic abuse' },
    { key: stage + '_mental_health_total_text', label: 'Mental health' },
    { key: stage + '_substance_dependency_total_text', label: 'Substance dependency' },
    { key: stage + '_homelessness_rough_sleeping_total_text', label: 'Homelessness / rough sleeping' },
    { key: stage + '_criminal_justice_total_text', label: 'Criminal justice contact' },
  ]
}
</script>

<template>
  <div class="atlas-panel atlas-panel-body space-y-4">
    <h3>Multiple disadvantage</h3>
    <p>Households recorded by MHCLG as experiencing three or more disadvantage flags. These are housing assessments, not treatment episodes or diagnoses.</p>
    <p class="atlas-footnote">Accommodation secured means six months or more after the relevant duty ended. Published [x] means missing data or non-submission; [z] means not applicable. Neither means zero. The published percentage can exceed 100% and is not recalculated.</p>
    <StEvidenceTable v-if="rows.length" caption="Multiple disadvantage observations" source-details :columns="columns" :rows="rows" row-key="row_key" />
    <StEmptyState v-else :title="props.comparator?.rows ? 'No multiple-disadvantage rows collected' : 'Multiple-disadvantage data not supplied'" />
    <p>The five category totals overlap. Do not sum them or combine them with NDTMS or Fingertips treatment figures.</p>
    <details v-if="rows.length">
      <summary>Published categories by duty stage</summary>
      <div v-for="stage in stages" :key="stage.key" class="mt-4">
        <StEvidenceTable :caption="stage.label" source-details :columns="categoryColumns(stage.key)" :rows="rows" row-key="row_key" />
      </div>
    </details>
    <StCaveat :text="props.comparator?.caveat" />
  </div>
</template>
