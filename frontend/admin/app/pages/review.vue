<script setup lang="ts">
import { getOperator, type AdminRecord } from '~/lib/operator';
import type { ReviewDecision } from '~/types/operator';
const api = useAdminApi();
const route = useRoute(),
  filters = useFilterState(),
  reviewer = useReviewer(),
  dialog = useAdminDialog();
const action = useOperatorAction(),
  toast = useToast();
const query = computed(
  () =>
    ({ status: 'pending', limit: 50, ...route.query }) as Record<
      string,
      string | number
    >,
);
const list = useOperatorResource('/api/review', query);
const facets = useOperatorResource('/api/review/facets');
const items = computed<AdminRecord[]>(() => list.data.value?.items || []);
const selected = ref<number[]>([]),
  focusedId = ref<number | null>(null),
  note = ref('');
const clusterOpen = ref(false);
const clusters = shallowRef<AdminRecord | null>(null);
const clusterError = ref('');
const sessionCount = ref(0);
const undo = shallowRef<Map<string, number[]> | null>(null);
const undoExpires = ref(0);
const presetsStore = useLocalStore<
  Record<
    string,
    { filters: Record<string, string | string[] | undefined>; note: string }
  >
>('st.admin.review.presets', 1, () => ({}));
const presets = ref(presetsStore.read()),
  presetName = ref('');
const focused = computed(() =>
  items.value.find((i) => i.id === focusedId.value),
);
watch(
  () => route.query,
  () => {
    selected.value = [];
    focusedId.value = null;
  },
);
function setFilter(key: string, event: Event) {
  return filters.setAll({
    ...filters.all(),
    [key]: (event.target as HTMLInputElement).value || undefined,
    offset: undefined,
  });
}
async function savePreset() {
  const name = await dialog.prompt('Name this filter and note preset');
  if (!name?.trim()) return;
  presets.value[name.trim()] = { filters: filters.all(), note: note.value };
  presetsStore.write(presets.value);
}
function loadPreset() {
  const p = presets.value[presetName.value];
  if (p) {
    void filters.setAll(p.filters);
    note.value = p.note;
  }
}
function toggle(id: number) {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((x) => x !== id)
    : [...selected.value, id];
}
function requireReviewer() {
  if (reviewer.isSet.value) return true;
  document.getElementById('admin-reviewer')?.focus();
  toast.add({ title: 'Enter your reviewer name first', color: 'warning' });
  return false;
}
async function decide(ids: number[], decision: string, restoring = false) {
  if (!ids.length || action.busy.value || !requireReviewer()) return;
  const answered = items.value.filter(
    (i) => ids.includes(i.id) && i.status === 'answered',
  ).length;
  if (
    !restoring &&
    !(await dialog.confirm(
      `${decision === 'pending' ? 'Reset' : decision} ${ids.length} review item(s)?${note.value ? '\nNote: ' + note.value : ''}${answered ? `\n${answered} answered item(s) cannot be restored through undo; that state belongs to source resolution.` : ''}`,
    ))
  )
    return;
  const prior = new Map(
    items.value.filter((i) => ids.includes(i.id)).map((i) => [i.id, i.status]),
  );
  const result = await action.run(() =>
    api.decideReviewItems({
      ids,
      decision: decision as ReviewDecision,
      decided_by: reviewer.name.value,
      note: restoring ? null : note.value,
    }),
  );
  if (!result) return;
  if (!restoring) {
    const groups = new Map<string, number[]>();
    for (const id of result.updated || []) {
      const old = prior.get(id);
      if (['pending', 'approved', 'rejected'].includes(old))
        groups.set(old, [...(groups.get(old) || []), id]);
    }
    undo.value = groups;
    undoExpires.value = Date.now() + 15000;
    sessionCount.value += result.updated?.length || 0;
  }
  const updated = new Set(result.updated || []);
  if (list.data.value) {
    for (const item of items.value)
      if (updated.has(item.id)) item.status = decision;
    if (query.value.status !== 'all' && query.value.status !== decision) {
      list.data.value = {
        ...list.data.value,
        items: items.value.filter((i) => !updated.has(i.id)),
        total: Math.max(0, list.data.value.total - updated.size),
      };
    } else list.data.value = { ...list.data.value, items: [...items.value] };
  }
  selected.value = selected.value.filter((id) => !updated.has(id));
  if (!focused.value) focusedId.value = items.value[0]?.id ?? null;
  if (!items.value.length) await list.refresh();
  void facets.refresh();
}
async function undoDecision() {
  if (action.busy.value) return;
  if (!undo.value || Date.now() > undoExpires.value) {
    undo.value = null;
    return;
  }
  const groups = undo.value;
  for (const [status, ids] of groups) {
    await decide(ids, status, true);
    if (action.error.value) return;
    groups.delete(status);
  }
  undo.value = null;
  await list.refresh();
}
async function matching(decision: string) {
  if (action.busy.value || !requireReviewer() || list.data.value?.total == null)
    return;
  const total = list.data.value.total;
  const typed = await dialog.prompt(
    `${decision} ALL ${total} matching review items? This has no bulk undo. Type ${total} to confirm.`,
  );
  if (typed?.replace(/[,\s]/g, '') !== String(total)) return;
  const q = query.value;
  if (
    await action.run('/api/review/decide-matching', {
      decision,
      decided_by: reviewer.name.value,
      confirm_count: total,
      note: note.value,
      status: q.status,
      module: q.module,
      item_type: q.item_type,
      search: q.q,
    })
  ) {
    selected.value = [];
    await list.refresh();
    void facets.refresh();
  }
}
async function decideCluster(cluster: AdminRecord, decision: string) {
  if (!requireReviewer() || action.busy.value) return;
  const ids: number[] = cluster.item_ids || [];
  if (
    !(await dialog.confirm(
      `${decision} the ${ids.length} listed items in this cluster? ${cluster.count > ids.length ? 'The cluster ID list is capped; remaining items are not included.' : ''} Grouping is not evidence that they share a decision.`,
    ))
  )
    return;
  if (
    await action.run('/api/review/decide', {
      ids,
      decision,
      decided_by: reviewer.name.value,
      note: note.value,
    })
  ) {
    await list.refresh();
    clusterOpen.value = false;
    void facets.refresh();
  }
}
async function showClusters() {
  clusterOpen.value = !clusterOpen.value;
  if (!clusterOpen.value) return;
  try {
    clusters.value = await getOperator('/api/review/clusters', {
      status: String(query.value.status),
    });
    clusterError.value = '';
  } catch (e) {
    clusterError.value = String(e);
  }
}
function keyboard(event: KeyboardEvent) {
  if (
    event.ctrlKey ||
    event.metaKey ||
    event.altKey ||
    dialog.request.value ||
    (event.target as HTMLElement)?.closest(
      'input, textarea, select, [contenteditable], [role=dialog]',
    )
  )
    return;
  const index = items.value.findIndex((i) => i.id === focusedId.value);
  if (event.key === 'j' || event.key === 'k') {
    event.preventDefault();
    focusedId.value =
      items.value[
        Math.max(
          0,
          Math.min(
            items.value.length - 1,
            index + (event.key === 'j' ? 1 : -1),
          ),
        )
      ]?.id ?? null;
  }
  if (event.key === '/') {
    event.preventDefault();
    document.getElementById('review-search')?.focus();
  }
  if (!focused.value) return;
  if (event.key === 'x') {
    event.preventDefault();
    toggle(focused.value.id);
  }
  if (['a', 'r', 'u'].includes(event.key)) {
    event.preventDefault();
    void decide(
      [focused.value.id],
      (
        { a: 'approved', r: 'rejected', u: 'pending' } as Record<string, string>
      )[event.key]!,
    );
  }
  if (event.key === 'o') {
    event.preventDefault();
    document
      .querySelector<HTMLAnchorElement>('.admin-detail-pane a[target="_blank"]')
      ?.click();
  }
}
onMounted(() => document.addEventListener('keydown', keyboard));
onUnmounted(() => document.removeEventListener('keydown', keyboard));
useQueueFocus(focusedId);
useUnsavedAdmin(() => note.value.length > 0);
useHead({ title: 'SectorTrace — Review queue' });
</script>
<template>
  <section class="admin-review-workspace" :data-focused="!!focused">
    <AdminPageHeader
      title="Review queue"
      description="Read the source, record your judgement, move on. A review decision does not promote evidence."
      eyebrow="Review · Human judgement"
      ><UButton
        color="neutral"
        variant="outline"
        :loading="list.pending.value"
        @click="list.refresh"
        >Refresh</UButton
      ></AdminPageHeader
    >
    <div class="admin-filters">
      <label
        >Status<select
          :value="query.status"
          @change="setFilter('status', $event)"
        >
          <option
            v-for="status in [
              'pending',
              'approved',
              'rejected',
              'answered',
              'all',
            ]"
            :key="status"
          >
            {{ status }}
          </option>
        </select></label
      >
      <label
        >Module<select
          :value="query.module || ''"
          @change="setFilter('module', $event)"
        >
          <option value="">All modules</option>
          <option
            v-for="m in facets.data.value?.modules"
            :key="m.module"
            :value="m.module"
          >
            {{ m.module }} ({{ m.pending }})
          </option>
        </select></label
      >
      <label
        >Item type<select
          :value="query.item_type || ''"
          @change="setFilter('item_type', $event)"
        >
          <option value="">All types</option>
          <option
            v-for="t in facets.data.value?.item_types?.filter(
              (t: AdminRecord) => !query.module || t.module === query.module,
            )"
            :key="`${t.module}-${t.item_type}`"
            :value="t.item_type"
          >
            {{ t.item_type }}
          </option>
        </select></label
      >
      <label class="grow"
        >Search<input
          id="review-search"
          type="search"
          :value="query.q || ''"
          placeholder="Raw value or context…"
          @change="setFilter('q', $event)"
      /></label>
      <label
        >Order<select
          :value="query.newest_first || ''"
          @change="setFilter('newest_first', $event)"
        >
          <option value="">Oldest first</option>
          <option value="1">Newest first</option>
        </select></label
      >
      <label
        >Rows<select :value="query.limit" @change="setFilter('limit', $event)">
          <option v-for="n in [25, 50, 100, 250]" :key="n">{{ n }}</option>
        </select></label
      >
    </div>
    <div class="admin-actions mb-5">
      <label class="admin-field"
        >Saved preset<select v-model="presetName" @change="loadPreset">
          <option value="">Choose a preset</option>
          <option v-for="(_, name) in presets" :key="name">{{ name }}</option>
        </select></label
      ><UButton color="neutral" variant="outline" @click="savePreset"
        >Save preset</UButton
      ><UButton
        v-if="presetName"
        color="neutral"
        variant="ghost"
        @click="
          delete presets[presetName];
          presetsStore.write(presets);
          presetName = '';
        "
        >Delete preset</UButton
      ><UButton color="neutral" variant="outline" @click="showClusters">{{
        clusterOpen ? 'Hide clusters' : 'Cluster view'
      }}</UButton
      ><span class="admin-note ml-auto"
        >{{ sessionCount }} decisions this session</span
      >
    </div>
    <section v-if="clusterOpen && clusters" class="admin-panel mb-5">
      <p class="admin-note mb-4">{{ clusters.caveat }}</p>
      <p v-if="clusters.truncated" class="admin-note">
        The source scan was capped. These clusters do not cover the full queue.
      </p>
      <AdminRows
        :rows="clusters.clusters || []"
        :columns="['module', 'item_type', 'token', 'count', 'sample_raw']"
        ><template #actions="{ row }"
          ><UButton
            size="xs"
            color="neutral"
            variant="outline"
            @click="
              filters.setAll({
                status: String(query.status),
                module: row.module,
                item_type: row.item_type,
                q: row.token,
              });
              clusterOpen = false;
            "
            >Open worklist</UButton
          ><UButton
            size="xs"
            :disabled="action.busy.value"
            @click="decideCluster(row, 'approved')"
            >Approve listed</UButton
          ><UButton
            size="xs"
            color="error"
            variant="outline"
            :disabled="action.busy.value"
            @click="decideCluster(row, 'rejected')"
            >Reject listed</UButton
          ></template
        ></AdminRows
      >
    </section>
    <p v-if="clusterError && clusterOpen" class="admin-error">
      {{ clusterError }}
    </p>
    <p v-if="list.error.value" role="alert" class="admin-error">
      {{ list.error.value }}
    </p>
    <p v-if="list.pending.value" role="status" class="admin-note">
      Refreshing queue…
    </p>
    <AdminPager
      :total="list.data.value?.total"
      :limit="Number(query.limit)"
      :offset="Number(query.offset || 0)"
    />
    <div class="admin-detail" :data-focused="!!focused">
      <div class="admin-queue admin-panel !p-0">
        <label class="flex items-center gap-2 p-3 border-b border-black/10"
          ><input
            type="checkbox"
            :checked="items.length > 0 && selected.length === items.length"
            @change="
              selected = ($event.target as HTMLInputElement).checked
                ? items.map((i) => i.id)
                : []
            "
          />
          Select this page</label
        >
        <p v-if="!items.length && !list.pending.value" class="p-5 admin-note">
          No items in this view.
        </p>
        <div
          v-for="item in items"
          :key="item.id"
          class="admin-queue-row flex gap-3"
          :data-active="focusedId === item.id"
        >
          <input
            type="checkbox"
            :aria-label="`Select item ${item.id}`"
            :checked="selected.includes(item.id)"
            @change="toggle(item.id)"
          /><button
            class="text-left min-w-0 flex-1"
            @click="focusedId = item.id"
          >
            <span class="block text-sm break-words">{{ item.raw_value }}</span
            ><span class="admin-note block mt-2"
              >#{{ item.id }} · {{ item.module }}</span
            ><StatusPill :label="item.status" />
          </button>
        </div>
      </div>
      <div class="admin-detail-pane admin-panel">
        <template v-if="focused"
          ><UButton
            color="neutral"
            variant="ghost"
            class="admin-mobile-back mb-3"
            @click="focusedId = null"
            >← Back to queue</UButton
          ><AdminReviewDetail
            :key="focused.id"
            :item="focused"
            :note="note"
            :resolvable="facets.data.value?.resolvable?.[focused.item_type]"
            @resolved="
              list.refresh();
              facets.refresh();
            "
          />
          <div class="admin-actions mt-5">
            <UButton
              :disabled="action.busy.value"
              @click="decide([focused.id], 'approved')"
              >Approve</UButton
            ><UButton
              color="error"
              variant="outline"
              :disabled="action.busy.value"
              @click="decide([focused.id], 'rejected')"
              >Reject</UButton
            ><UButton
              color="neutral"
              variant="outline"
              :disabled="action.busy.value"
              @click="decide([focused.id], 'pending')"
              >Reset to pending</UButton
            >
          </div></template
        >
        <p v-else class="admin-note">
          Choose an item to read its source, context and decision history.
        </p>
      </div>
    </div>
    <div class="admin-actionbar space-y-3">
      <label class="admin-field"
        >Decision note<input
          v-model="note"
          maxlength="2000"
          placeholder="Context for the audit trail (optional)"
      /></label>
      <div class="admin-actions">
        <span class="admin-note">{{ selected.length }} selected</span
        ><UButton
          :disabled="!selected.length || action.busy.value"
          @click="decide(selected, 'approved')"
          >Approve selected</UButton
        ><UButton
          color="error"
          variant="outline"
          :disabled="!selected.length || action.busy.value"
          @click="decide(selected, 'rejected')"
          >Reject selected</UButton
        ><UButton
          color="neutral"
          variant="outline"
          :disabled="!selected.length || action.busy.value"
          @click="decide(selected, 'pending')"
          >Reset selected</UButton
        ><UButton color="neutral" variant="ghost" @click="selected = []"
          >Clear</UButton
        >
        <details class="ml-auto">
          <summary class="text-sm">All matching…</summary>
          <div class="admin-actions py-3">
            <UButton
              size="xs"
              :disabled="action.busy.value || !list.data.value?.total"
              @click="matching('approved')"
              >Approve all matching</UButton
            ><UButton
              size="xs"
              color="error"
              :disabled="action.busy.value || !list.data.value?.total"
              @click="matching('rejected')"
              >Reject all matching</UButton
            >
          </div>
        </details>
      </div>
      <div v-if="undo" class="admin-actions">
        <span class="admin-note"
          >The last decision can be restored for 15 seconds. Undo is recorded in
          the audit trail.</span
        ><UButton
          size="xs"
          color="neutral"
          variant="outline"
          :disabled="action.busy.value"
          @click="undoDecision"
          >Undo</UButton
        >
      </div>
      <p v-if="action.error.value" role="alert" class="admin-error">
        {{ action.error.value }}
      </p>
      <details v-if="action.result.value">
        <summary class="admin-note">Decision outcome</summary>
        <AdminRecord :value="action.result.value" />
      </details>
    </div>
    <p class="admin-note mt-4">
      Keys: j/k move · a approve · r reject · u reset · x select · o open source
      · / search · Ctrl/Cmd K jump
    </p>
  </section>
</template>
