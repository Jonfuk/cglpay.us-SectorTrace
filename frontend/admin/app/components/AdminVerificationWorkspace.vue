<script setup lang="ts">
import {
  getOperator,
  postOperator,
  safeUrl,
  type AdminRecord,
} from '~/lib/operator';
const props = defineProps<{ mode: 'candidates' | 'census' }>();
const census = props.mode === 'census';
const route = useRoute(),
  filters = useFilterState(),
  reviewer = useReviewer(),
  dialog = useAdminDialog();
const query = computed(
  () =>
    ({
      status: census ? 'unchecked' : 'undecided',
      limit: 25,
      ...(census ? {} : { kind: 'cdp_document' }),
      ...route.query,
    }) as Record<string, string | number>,
);
const base = `/api/admin/${props.mode}`;
const list = useOperatorResource(base, query),
  counts = useOperatorResource(`${base}/counts`);
const authorities = census
  ? null
  : useOperatorResource(`${base}/authorities`, () => ({
      kind: query.value.kind,
    }));
const rows = computed<AdminRecord[]>(() => list.data.value?.items || []);
const selected = ref<string[]>([]),
  focusedKey = ref<string | null>(null),
  opened = ref(new Set<string>());
const previews = ref<Record<string, AdminRecord>>({}),
  fields = ref<Record<string, Record<string, string>>>({}),
  notes = ref<Record<string, string>>({});
const batchNote = ref(''),
  fill = ref(''),
  busy = ref(false),
  error = ref(''),
  outcomes = ref<AdminRecord[]>([]);
const session = ref(0);
const key = (row: AdminRecord) => String(census ? row.key : row.url);
const pageKey = (row: AdminRecord) => `${row.census_year}:${row.source_page}`;
const readKey = (row: AdminRecord) => (census ? pageKey(row) : key(row));
const focused = computed(() =>
  rows.value.find((r) => key(r) === focusedKey.value),
);
const picked = computed(() =>
  rows.value.filter((r) => selected.value.includes(key(r))),
);
const required = computed<string[]>(() => list.data.value?.requires || []);
function blocked(row: AdminRecord): string {
  if (row.verified) return census ? 'Already verified' : 'Already promoted';
  if (census && row.rejected) return 'Rejected as a bad parse';
  if (!opened.value.has(readKey(row)))
    return census
      ? 'Source page not read in this session'
      : 'Document not opened in this session';
  if (
    !census &&
    required.value.some((f) => !fields.value[key(row)]?.[f]?.trim())
  )
    return 'Required promotion fields missing';
  return '';
}
const ready = computed(() => picked.value.filter((r) => !blocked(r)));
watch(
  rows,
  (value) => {
    for (const row of value) {
      fields.value[key(row)] ||= {};
      notes.value[key(row)] ||= '';
    }
  },
  { immediate: true },
);
watch(
  () => route.query,
  () => {
    selected.value = [];
    focusedKey.value = null;
  },
);
function setFilter(name: string, event: Event) {
  return filters.setAll({
    ...filters.all(),
    [name]: (event.target as HTMLInputElement).value || undefined,
    offset: undefined,
  });
}
function choose(row: AdminRecord) {
  focusedKey.value = key(row);
}
function toggle(row: AdminRecord) {
  const id = key(row);
  selected.value = selected.value.includes(id)
    ? selected.value.filter((x) => x !== id)
    : [...selected.value, id];
}
async function preview(row: AdminRecord) {
  error.value = '';
  try {
    const result = await getOperator(
      `${base}/${census ? 'page' : 'detail'}`,
      census
        ? { year: row.census_year, page: row.source_page }
        : { kind: query.value.kind, url: row.url },
    );
    previews.value[readKey(row)] = result;
    if (census) opened.value.add(readKey(row));
  } catch (e) {
    error.value = String(e);
  }
}
function openSource(row: AdminRecord) {
  const url = safeUrl(row.url);
  if (!url) {
    error.value = 'This record has no valid http(s) source URL.';
    return;
  }
  const child = window.open(url, '_blank');
  if (child) {
    child.opener = null;
    opened.value.add(key(row));
  } else
    error.value =
      'The browser blocked this tab. Allow this source to open, then try again.';
}
async function decide(
  action: 'promote' | 'verify' | 'reject' | 'reset',
  targets: AdminRecord[],
) {
  if (busy.value || !targets.length) return;
  if (!reviewer.isSet.value) {
    document.getElementById('admin-reviewer')?.focus();
    error.value = 'Enter your reviewer name first.';
    return;
  }
  // Single and batch verification share the same gate. Nothing is marked read
  // on hover, preview failure, selection, or a restored browser preference.
  const eligible = ['promote', 'verify'].includes(action)
    ? targets.filter((r) => !blocked(r))
    : targets;
  if (!eligible.length) {
    error.value = 'Read the source and complete the required fields first.';
    return;
  }
  if (
    !(await dialog.confirm(
      `${action} ${eligible.length} ${census ? 'figure(s)' : 'candidate(s)'}? Each result is recorded separately against ${reviewer.name.value}.`,
    ))
  )
    return;
  const kind = query.value.kind,
    decidedBy = reviewer.name.value;
  const inputs = Object.fromEntries(
    eligible.map((row) => [
      key(row),
      {
        fields: { ...fields.value[key(row)] },
        note: notes.value[key(row)] || batchNote.value || null,
      },
    ]),
  );
  busy.value = true;
  error.value = '';
  outcomes.value = [];
  try {
    for (const row of eligible) {
      const id = key(row),
        note = inputs[id]!.note;
      const body = census
        ? action === 'verify'
          ? { key: id, verified_by: decidedBy, note }
          : action === 'reject'
            ? { keys: [id], rejected_by: decidedBy, note }
            : { key: id }
        : action === 'promote'
          ? {
              kind: kind,
              url: row.url,
              promoted_by: decidedBy,
              fields: inputs[id]!.fields,
              note,
            }
          : action === 'reject'
            ? { kind: kind, urls: [row.url], rejected_by: decidedBy, note }
            : { kind: kind, url: row.url };
      try {
        const result = await postOperator(`${base}/${action}`, body);
        outcomes.value.push({ record: id, status: 'recorded', ...result });
        session.value++;
        notes.value[id] = '';
        fields.value[id] = {};
      } catch (e) {
        outcomes.value.push({ record: id, status: 'failed', error: String(e) });
      }
    }
    selected.value = selected.value.filter((id) =>
      outcomes.value.some((o) => o.record === id && o.status === 'failed'),
    );
    await list.refresh();
    await counts.refresh();
  } finally {
    busy.value = false;
  }
}
useQueueFocus(focusedKey);
useUnsavedAdmin(
  () =>
    busy.value ||
    !!batchNote.value ||
    Object.values(notes.value).some(Boolean) ||
    Object.values(fields.value).some((values) =>
      Object.values(values).some(Boolean),
    ),
);
</script>
<template>
  <section class="admin-review-workspace" :data-focused="!!focused">
    <AdminPageHeader
      :title="census ? 'Workforce census' : 'Candidates'"
      :description="
        census
          ? 'Read each archived source page before verifying its figures. Verification confirms transcription, never comparability between years.'
          : 'Inspect a discovered document, confirm its details, then promote it with its provenance. Every promotion fetches and archives one source.'
      "
      eyebrow="Review · Source verification"
      ><UButton
        color="neutral"
        variant="outline"
        :loading="list.pending.value"
        @click="
          list.refresh();
          counts.refresh();
        "
        >Refresh</UButton
      ></AdminPageHeader
    >
    <div class="admin-filters">
      <label v-if="!census"
        >Source kind<select
          :value="query.kind"
          @change="setFilter('kind', $event)"
        >
          <option
            v-for="(_, name) in counts.data.value?.kinds"
            :key="name"
            :value="name"
          >
            {{ name }}
          </option>
        </select></label
      >
      <label v-if="census"
        >Year<select
          :value="query.year || ''"
          @change="setFilter('year', $event)"
        >
          <option value="">All years</option>
          <option
            v-for="year in counts.data.value?.years"
            :key="year.census_year"
          >
            {{ year.census_year }}
          </option>
        </select></label
      >
      <label
        >Status<select
          :value="query.status"
          @change="setFilter('status', $event)"
        >
          <option
            v-for="status in census
              ? ['unchecked', 'verified', 'rejected', 'all']
              : ['undecided', 'promoted', 'rejected', 'all']"
            :key="status"
          >
            {{ status }}
          </option>
        </select></label
      >
      <label v-if="!census"
        >Authority<select
          :value="query.authority || ''"
          @change="setFilter('authority', $event)"
        >
          <option value="">All authorities</option>
          <option
            v-for="a in authorities?.data.value?.authorities"
            :key="a.ons_code"
            :value="a.ons_code"
          >
            {{ a.name || a.ons_code }} ({{ a.candidates }})
          </option>
        </select></label
      >
      <label v-if="!census" class="grow"
        >Search<input
          type="search"
          :value="query.q || ''"
          @change="setFilter('q', $event)"
      /></label>
      <span class="admin-note ml-auto"
        >{{ session }} decisions this session</span
      >
    </div>
    <div
      v-if="census && counts.data.value?.stale?.length"
      class="admin-error mb-4"
    >
      <h2>Verified sources have changed</h2>
      <AdminRows :rows="counts.data.value.stale" />
    </div>
    <p v-if="list.error.value || error" role="alert" class="admin-error">
      {{ list.error.value || error }}
    </p>
    <p v-if="list.pending.value" role="status" class="admin-note">
      Refreshing worklist…
    </p>
    <AdminPager
      :total="list.data.value?.total"
      :offset="Number(query.offset || 0)"
      :limit="Number(query.limit)"
    />
    <div class="admin-detail" :data-focused="!!focused">
      <div class="admin-queue admin-panel !p-0">
        <label class="flex gap-2 p-3"
          ><input
            type="checkbox"
            :checked="rows.length > 0 && selected.length === rows.length"
            @change="
              selected = ($event.target as HTMLInputElement).checked
                ? rows.map(key)
                : []
            "
          />Select page</label
        >
        <p v-if="!rows.length" class="admin-note p-5">
          No records in this view.
        </p>
        <div
          v-for="row in rows"
          :key="key(row)"
          class="admin-queue-row flex gap-3"
          :data-active="focusedKey === key(row)"
        >
          <input
            type="checkbox"
            :checked="selected.includes(key(row))"
            :aria-label="`Select ${key(row)}`"
            @change="toggle(row)"
          /><button class="min-w-0 text-left" @click="choose(row)">
            <span class="block text-sm break-words">{{
              census
                ? row.metric
                : row.summary?.title || row.summary?.report_title || row.url
            }}</span
            ><span class="admin-note block mt-2">{{
              census
                ? `${row.census_year} · ${row.workforce_segment}`
                : row.authority_name
            }}</span
            ><StatusPill
              v-if="opened.has(readKey(row))"
              label="Source opened"
            /><StatusPill
              v-if="row.verified"
              :label="census ? 'Verified' : 'Promoted'"
              level="ok"
            /><StatusPill v-if="row.rejected" label="Rejected" level="bad" />
          </button>
        </div>
      </div>
      <div class="admin-detail-pane admin-panel">
        <template v-if="focused"
          ><UButton
            class="admin-mobile-back mb-3"
            color="neutral"
            variant="ghost"
            @click="focusedKey = null"
            >← Back to worklist</UButton
          >
          <h2>
            {{
              census
                ? focused.metric
                : focused.summary?.title || 'Document candidate'
            }}
          </h2>
          <p v-if="census" class="text-2xl my-4">
            {{ focused.value ?? '—' }} {{ focused.unit || '' }}
          </p>
          <AdminRecord :value="census ? focused.source : focused.summary" />
          <div class="admin-actions my-4">
            <UButton
              color="neutral"
              variant="outline"
              @click="preview(focused)"
              >{{
                census
                  ? `Read extracted page ${focused.source_page}`
                  : 'Preview record'
              }}</UButton
            ><UButton
              v-if="!census"
              color="neutral"
              variant="outline"
              @click="openSource(focused)"
              >Open document ↗</UButton
            ><StLink v-if="census" :href="focused.source?.source_url"
              >Original source ↗</StLink
            >
          </div>
          <div v-if="previews[readKey(focused)]" class="admin-panel my-4">
            <template v-if="census"
              ><p class="admin-note">
                Extracted page {{ focused.source_page }} (PDF viewer page
                {{ Number(focused.source_page) + 1 }}).
              </p>
              <pre>{{ previews[readKey(focused)]?.page_text }}</pre></template
            ><AdminRecord v-else :value="previews[readKey(focused)]" />
          </div>
          <div v-if="!census" class="space-y-3">
            <label v-for="name in required" :key="name" class="admin-field"
              >Confirmed {{ name.replaceAll('_', ' ')
              }}<input
                v-model="fields[key(focused)]![name]"
                :aria-label="`Confirmed ${name}`"
            /></label>
          </div>
          <label class="admin-field mt-4"
            >Decision note<input v-model="notes[key(focused)]" maxlength="2000"
          /></label>
          <p v-if="blocked(focused)" class="admin-note mt-3">
            {{ blocked(focused) }}
          </p>
          <div class="admin-actions mt-4">
            <UButton
              :disabled="busy || !!blocked(focused)"
              @click="decide(census ? 'verify' : 'promote', [focused])"
              >{{
                census ? 'Verify against source' : 'Promote document'
              }}</UButton
            ><UButton
              color="error"
              variant="outline"
              :disabled="busy"
              @click="decide('reject', [focused])"
              >Reject</UButton
            ><UButton
              color="neutral"
              variant="ghost"
              :disabled="busy"
              @click="decide('reset', [focused])"
              >Reset</UButton
            >
          </div>
          <details class="mt-5">
            <summary>Full record and provenance</summary>
            <AdminRecord :value="focused" /></details
        ></template>
        <p v-else class="admin-note">Choose a record to inspect its source.</p>
      </div>
    </div>
    <div class="admin-actionbar space-y-3">
      <div class="admin-actions">
        <span class="admin-note"
          >{{ selected.length }} selected · {{ ready.length }} eligible</span
        ><UButton
          v-if="!census"
          color="neutral"
          variant="outline"
          :disabled="busy || !selected.length"
          @click="picked.slice(0, 10).forEach(openSource)"
          >Open up to 10 selected</UButton
        ><UButton
          :disabled="busy || !ready.length"
          @click="decide(census ? 'verify' : 'promote', ready)"
          >{{
            census ? 'Verify read figures' : 'Promote opened documents'
          }}</UButton
        ><UButton
          color="error"
          variant="outline"
          :disabled="busy || !selected.length"
          @click="decide('reject', picked)"
          >Reject selected</UButton
        ><UButton color="neutral" variant="ghost" @click="selected = []"
          >Clear selection</UButton
        >
      </div>
      <div
        v-if="!census && required.includes('document_type')"
        class="admin-actions"
      >
        <label class="admin-field"
          >Confirmed document type<input v-model="fill" /></label
        ><UButton
          color="neutral"
          variant="outline"
          :disabled="busy || !selected.length"
          @click="
            picked.forEach((r) => {
              fields[key(r)]!.document_type = fill;
            })
          "
          >Fill into selected</UButton
        >
      </div>
      <label class="admin-field"
        >Batch note<input v-model="batchNote" maxlength="2000"
      /></label>
      <ul v-if="picked.some((r) => blocked(r))" class="admin-note">
        <li v-for="r in picked.filter((r) => blocked(r))" :key="key(r)">
          {{ key(r) }} — {{ blocked(r) }}
        </li>
      </ul>
      <p v-if="busy" role="status">
        Recording {{ outcomes.length }} of {{ picked.length || 1 }}…
      </p>
    </div>
    <section v-if="outcomes.length" class="admin-panel mt-5">
      <h2>Batch outcomes</h2>
      <AdminRows :rows="outcomes" />
    </section>
    <details class="admin-panel mt-5">
      <summary>
        {{
          census
            ? 'Verification counts and decision history'
            : 'Source counts and promotion history'
        }}
      </summary>
      <AdminRecord :value="counts.data.value" />
      <p v-if="counts.error.value" class="admin-error">
        {{ counts.error.value }}
      </p>
    </details>
  </section>
</template>
