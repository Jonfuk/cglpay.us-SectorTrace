<script setup lang="ts">
const documentId = ref(''),
  parser = ref('');
const replay = useOperatorResource(
  '/api/admin/parser-replay',
  () => ({ document_id: documentId.value, parser: parser.value || undefined }),
  false,
);
useHead({ title: 'SectorTrace — Parser replay' });
</script>
<template>
  <section>
    <AdminPageHeader
      title="Parser replay"
      description="Replay a parser against archived bytes and compare proposed output with the stored version. Nothing is written."
      eyebrow="Quality · Archived-source inspection"
    />
    <form class="admin-filters" @submit.prevent="replay.refresh">
      <label class="grow"
        >Document ID<input
          v-model="documentId"
          required
          placeholder="document_id" /></label
      ><label
        >Parser<select v-model="parser">
          <option value="">Automatic</option>
          <option>html</option>
          <option>docx</option>
          <option>pptx</option>
        </select></label
      ><UButton
        type="submit"
        :loading="replay.pending.value"
        :disabled="!documentId"
        >Replay</UButton
      >
    </form>
    <p v-if="replay.error.value" class="admin-error">
      {{ replay.error.value }}
    </p>
    <template v-if="replay.data.value"
      ><p class="admin-note mb-5">{{ replay.data.value.note }}</p>
      <p v-if="!replay.data.value.available" class="admin-error">
        Replay unavailable: {{ replay.data.value.reason }}
      </p>
      <div class="admin-grid">
        <section class="admin-panel">
          <h2>Stored parse</h2>
          <AdminRecord :value="replay.data.value.stored" />
        </section>
        <section class="admin-panel">
          <h2>Proposed parse</h2>
          <AdminRecord :value="replay.data.value.proposed" />
        </section>
      </div>
      <section class="admin-panel mt-5">
        <h2>Changes and archive provenance</h2>
        <AdminRecord :value="replay.data.value.archive" /><AdminRecord
          :value="replay.data.value.diff"
        /></section
    ></template>
  </section>
</template>
