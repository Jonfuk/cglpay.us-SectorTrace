<script setup lang="ts">
import { adminPath } from '~/lib/navigation';
const cockpit = useOperatorResource('/api/admin/cockpit');
const mission = useOperatorResource('/api/admin/mission-control');
const health = useOperatorResource('/api/admin/health');
const counts = useOperatorResource('/api/admin/candidates/counts');
useAdminPolling(() => mission.refresh(), 15000);
useHead({ title: 'SectorTrace — Operator desk' });
</script>
<template>
  <section>
    <AdminPageHeader
      title="Your operator desk"
      description="Pick up review work, follow collection, and keep the evidence trail in view."
      eyebrow="Overview · SectorTrace"
      ><NuxtLink to="/review" class="text-sm"
        >Open review queue →</NuxtLink
      ></AdminPageHeader
    >
    <div class="admin-grid items-start">
      <section class="admin-panel">
        <div class="admin-actions justify-between mb-5">
          <h2>Ready for attention</h2>
          <span class="admin-note">Review &amp; quality</span>
        </div>
        <p
          v-if="cockpit.pending.value && !cockpit.data.value"
          class="admin-note"
        >
          Loading worklists…
        </p>
        <p v-if="cockpit.error.value" class="admin-error">
          Worklists unavailable. <button @click="cockpit.refresh">Retry</button>
        </p>
        <div v-if="cockpit.data.value" class="space-y-2">
          <NuxtLink
            v-for="card in cockpit.data.value.cards"
            :key="card.key"
            :to="adminPath(card.link || '/')"
            class="operator-task"
            ><div class="flex justify-between gap-3">
              <h3>{{ card.title }}</h3>
              <span class="text-xl font-semibold tabular-nums">{{
                card.metric ?? 'Unavailable'
              }}</span>
            </div>
            <p class="admin-note mt-1">{{ card.reason }}</p>
            <span class="text-xs mt-3 inline-block"
              >Inspect worklist →</span
            ></NuxtLink
          >
        </div>
      </section>
      <section class="admin-panel">
        <div class="admin-actions justify-between mb-5">
          <h2>Collection &amp; jobs</h2>
          <NuxtLink to="/pipeline" class="text-sm">Open pipeline →</NuxtLink>
        </div>
        <p
          v-if="mission.pending.value && !mission.data.value"
          class="admin-note"
        >
          Loading pipeline state…
        </p>
        <p v-if="mission.error.value" class="admin-error">
          Pipeline state unavailable.
          <button @click="mission.refresh">Retry</button>
        </p>
        <template v-if="mission.data.value"
          ><StatusPill
            :label="
              mission.data.value.active
                ? 'Running · job ' + mission.data.value.active.id
                : 'No active collection'
            "
            level="neutral" /><AdminRecord
            v-if="mission.data.value.active"
            :value="mission.data.value.active" />
          <h3 class="mt-6 mb-3">Most recent run</h3>
          <AdminRecord
            v-if="mission.data.value.last_run"
            :value="mission.data.value.last_run" />
          <p v-else class="admin-note">No durable run recorded.</p>
          <h3 class="mt-6 mb-3">Failures to investigate</h3>
          <AdminRows
            :rows="mission.data.value.failure_summary || []"
            :columns="[
              'module',
              'parse_failures',
              'pending_review',
              'last_status',
            ]"
        /></template>
      </section>
    </div>
    <div class="admin-grid mt-5">
      <section class="admin-panel">
        <h2>Warehouse reference</h2>
        <p class="admin-note mb-4">
          Supporting operational counts. Unavailable values are never treated as
          zero.
        </p>
        <p v-if="health.error.value" class="admin-error">
          Warehouse status unavailable.
        </p>
        <AdminRecord
          v-if="health.data.value"
          :value="health.data.value.warehouse"
        />
        <details v-if="counts.data.value" class="mt-5">
          <summary>Candidate counts by source</summary>
          <AdminRecord :value="counts.data.value" />
        </details>
        <p v-if="counts.error.value" class="admin-note">
          Candidate counts unavailable.
        </p>
        <NuxtLink to="/health" class="block mt-5 text-sm"
          >Inspect health and coverage →</NuxtLink
        >
      </section>
      <LazyAdminResourcePanel
        title="Decision history by month"
        path="/api/admin/review-analytics"
        field="by_month"
      /><LazyAdminResourcePanel
        title="Recent jobs"
        path="/api/admin/jobs"
        field="jobs"
        :query="{ limit: 10 }"
        :columns="['id', 'label', 'state', 'started_at']"
      />
    </div>
  </section>
</template>
