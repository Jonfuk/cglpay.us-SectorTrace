<script setup lang="ts">
import { textValue, labelFor, safeUrl } from '~/lib/operator';
defineProps<{ value: unknown }>();
</script>
<template>
  <div class="admin-record">
    <dl v-if="value && typeof value === 'object' && !Array.isArray(value)">
      <div
        v-for="(entry, key) in value"
        :key="key"
        class="py-2 border-b border-black/5"
      >
        <dt>{{ labelFor(String(key)) }}</dt>
        <dd>
          <StLink v-if="safeUrl(entry)" :href="String(entry)" /><AdminRecord
            v-else-if="entry && typeof entry === 'object'"
            :value="entry"
          /><span v-else class="whitespace-pre-wrap">{{
            textValue(entry)
          }}</span>
        </dd>
      </div>
    </dl>
    <div v-else-if="Array.isArray(value)" class="space-y-3">
      <p v-if="!value.length" class="admin-note">No records.</p>
      <details v-for="(entry, index) in value" :key="index" class="admin-panel">
        <summary>
          {{
            typeof entry === 'object' ? `Record ${index + 1}` : textValue(entry)
          }}
        </summary>
        <AdminRecord v-if="entry && typeof entry === 'object'" :value="entry" />
      </details>
    </div>
    <span v-else>{{ textValue(value) }}</span>
  </div>
</template>
