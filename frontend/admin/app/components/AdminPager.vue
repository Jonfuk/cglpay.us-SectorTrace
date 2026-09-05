<script setup lang="ts">
const props = withDefaults(
  defineProps<{ total?: number; limit?: number; offset?: number }>(),
  { limit: 50, offset: 0 },
);
const filters = useFilterState();
function go(offset: number) {
  return filters.set('offset', String(Math.max(0, offset)));
}
</script>
<template>
  <nav class="admin-actions justify-between py-4" aria-label="Pagination">
    <span class="admin-note">{{
      total == null
        ? 'Count unavailable'
        : total === 0
          ? 'No results'
          : `${offset + 1}–${Math.min(offset + limit, total)} of ${total.toLocaleString('en-GB')}`
    }}</span>
    <div class="admin-actions">
      <UButton
        color="neutral"
        variant="outline"
        :disabled="offset <= 0"
        @click="go(offset - limit)"
        >Previous</UButton
      ><UButton
        color="neutral"
        variant="outline"
        :disabled="total == null || offset + limit >= total"
        @click="go(offset + limit)"
        >Next</UButton
      >
    </div>
  </nav>
</template>
