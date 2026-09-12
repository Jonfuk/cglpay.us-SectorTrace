<script setup lang="ts">
const route = useRoute(),
  action = useOperatorAction();
const view = computed(() => String(route.query.view || 'warehouse'));
const tabs = [
  { key: 'warehouse', label: 'Warehouse' },
  { key: 'freshness', label: 'Freshness' },
  { key: 'coverage', label: 'Coverage' },
  { key: 'failures', label: 'Parse failures' },
  { key: 'audits', label: 'Archive audits' },
  { key: 'rules', label: 'Validation rules' },
  { key: 'overlaps', label: 'URL overlaps' },
];
const tier = ref('upper');
const jobId = ref<number | null>(null);
const job = useOperatorResource(
  () => `/api/admin/jobs/${jobId.value}`,
  {},
  false,
);
async function check() {
  const result = await action.run('/api/admin/check', {});
  if (result) {
    jobId.value = result.id;
    await job.refresh();
  }
}
useAdminPolling(async () => {
  if (
    jobId.value &&
    (job.data.value?.running ||
      ['queued', 'pending'].includes(job.data.value?.state))
  )
    await job.refresh();
}, 1000);
useHead({ title: 'SectorTrace — Health' });
</script>
<template>
  <section>
    <AdminPageHeader
      title="Health"
      description="Inspect warehouse health and source coverage. Open a view to load its checks; an unavailable check never means healthy."
      eyebrow="Quality · Warehouse health"
      ><UButton
        color="neutral"
        variant="outline"
        :loading="action.busy.value"
        @click="check"
        >Run integrity check</UButton
      ></AdminPageHeader
    ><AdminLocalTabs :tabs="tabs" :current="view" />
    <p v-if="action.error.value" class="admin-error">
      {{ action.error.value }}
    </p>
    <section v-if="jobId" class="admin-panel mb-5">
      <h2>Integrity job #{{ jobId }}</h2>
      <AdminRecord :value="job.data.value" />
      <p v-if="job.error.value" class="admin-error">{{ job.error.value }}</p>
    </section>
    <div class="space-y-5">
      <template v-if="view === 'warehouse'"
        ><AdminResourcePanel
          title="Warehouse and derived structures"
          path="/api/admin/health" /><AdminResourcePanel
          title="Storage"
          path="/api/admin/storage"
          field="storage" /><AdminResourcePanel
          title="PostgreSQL capabilities"
          path="/api/admin/pg-capabilities"
      /></template>
      <AdminResourcePanel
        v-if="view === 'freshness'"
        title="Source requests and evidence freshness"
        path="/api/admin/freshness"
      />
      <template v-if="view === 'coverage'"
        ><label class="admin-field mb-4"
          >Authority coverage<select v-model="tier">
            <option value="upper">Public-health authorities</option>
            <option value="all">All authorities</option>
          </select></label
        ><AdminCoverage :tier="tier" /><LazyAdminCompleteness
      /></template>
      <LazyAdminFailures v-if="view === 'failures'" />
      <AdminResourcePanel
        v-if="view === 'audits'"
        title="Archive audits"
        path="/api/admin/archive-audits"
      />
      <LazyAdminValidationRules v-if="view === 'rules'" />
      <AdminResourcePanel
        v-if="view === 'overlaps'"
        title="Canonical URL overlaps"
        path="/api/admin/url-overlaps"
      />
    </div>
  </section>
</template>
