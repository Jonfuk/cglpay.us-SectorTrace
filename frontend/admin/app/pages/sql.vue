<script setup lang="ts">
import { downloadCsv, textValue } from '~/lib/operator';
const api = useAdminApi();
const sql = ref(''),
  savedName = ref(''),
  action = useOperatorAction(),
  dialog = useAdminDialog();
const historyStore = useLocalStore<string[]>(
  'st.admin.sql.history',
  1,
  () => [],
);
const savedStore = useLocalStore<Record<string, string>>(
  'st.admin.sql.saved',
  1,
  () => ({}),
);
const resultStatement = ref('');
const history = ref(historyStore.read()),
  saved = ref(savedStore.read()),
  explain = ref(false),
  executed = ref('');
async function run(plan = false) {
  if (!sql.value.trim() || action.busy.value) return;
  const statement = sql.value.trim();
  const submitted = plan ? `EXPLAIN ${statement}` : statement;
  const result = await action.run(() => api.querySql(submitted));
  if (result) {
    explain.value = plan;
    resultStatement.value = submitted;
  }
  if (result && !plan) {
    executed.value = statement;
    history.value = [
      statement,
      ...history.value.filter((s) => s !== statement),
    ].slice(0, 50);
    historyStore.write(history.value);
  }
}
async function loadStatement(value: string, name = '') {
  if (
    sql.value &&
    sql.value !== executed.value &&
    sql.value !== value &&
    !(await dialog.confirm('Replace the unsaved SQL statement in the editor?'))
  )
    return;
  sql.value = value;
  savedName.value = name;
  executed.value = value;
}
async function save() {
  const name = await dialog.prompt(
    'Name this read-only query',
    savedName.value,
  );
  if (name?.trim()) {
    saved.value[name.trim()] = sql.value;
    savedStore.write(saved.value);
    savedName.value = name.trim();
    executed.value = sql.value;
  }
}
useUnsavedAdmin(() => !!sql.value && sql.value !== executed.value);
useHead({ title: 'SectorTrace — Read-only SQL' });
</script>
<template>
  <section>
    <AdminPageHeader
      title="Read-only SQL"
      description="One statement at a time, with a server-enforced deadline and result limit. Explain inspects the plan without running ANALYZE."
      eyebrow="Data · Query workspace"
    />
    <div class="admin-grid">
      <section class="admin-panel">
        <label class="admin-field"
          >SQL statement<textarea
            v-model="sql"
            rows="12"
            spellcheck="false"
            class="font-mono"
            placeholder="SELECT …"
            @keydown.ctrl.enter.prevent="run()"
            @keydown.meta.enter.prevent="run()"
          />
        </label>
        <div class="admin-actions mt-4">
          <UButton
            :loading="action.busy.value"
            :disabled="!sql.trim() || action.busy.value"
            @click="run()"
            >Run query</UButton
          ><UButton
            color="neutral"
            variant="outline"
            :disabled="!sql.trim() || action.busy.value"
            @click="run(true)"
            >Explain</UButton
          ><UButton
            color="neutral"
            variant="ghost"
            :disabled="!sql.trim()"
            @click="save"
            >Save query</UButton
          >
        </div>
        <p class="admin-note mt-3">
          Ctrl/Cmd Enter runs the statement. Saved queries stay in this browser.
        </p>
      </section>
      <section class="admin-panel">
        <h2>Saved queries</h2>
        <div
          v-for="(value, name) in saved"
          :key="name"
          class="admin-actions py-2"
        >
          <button
            class="text-left grow"
            @click="loadStatement(value, String(name))"
          >
            {{ name }}</button
          ><UButton
            size="xs"
            color="neutral"
            variant="ghost"
            @click="
              delete saved[name];
              savedStore.write(saved);
            "
            >Remove</UButton
          >
        </div>
        <p v-if="!Object.keys(saved).length" class="admin-note">
          Save a query to return to it later.
        </p>
        <details class="mt-6">
          <summary>Recent statements ({{ history.length }})</summary>
          <button
            v-for="(value, i) in history"
            :key="i"
            class="block text-left w-full py-3 border-b border-black/10 text-xs font-mono break-words"
            @click="loadStatement(value)"
          >
            {{ value }}
          </button>
        </details>
        <NuxtLink to="/database" class="block mt-5 text-sm"
          >Browse tables and schema →</NuxtLink
        >
      </section>
    </div>
    <p v-if="action.error.value" role="alert" class="admin-error mt-5">
      {{ action.error.value }}
    </p>
    <section v-if="action.result.value" class="admin-panel mt-5">
      <div class="admin-actions justify-between mb-4">
        <h2>{{ explain ? 'Query plan' : 'Query results' }}</h2>
        <UButton
          v-if="!explain"
          color="neutral"
          variant="outline"
          @click="
            downloadCsv(action.result.value.columns, action.result.value.rows)
          "
          >Download current result CSV</UButton
        >
      </div>
      <p class="admin-note mb-4">
        {{ action.result.value.rows?.length }} returned rows<span
          v-if="action.result.value.truncated"
        >
          · Result truncated at the server limit; this is not the full
          dataset.</span
        >
      </p>
      <details class="mb-4">
        <summary>Statement for this result</summary>
        <pre>{{ resultStatement }}</pre>
      </details>
      <div class="admin-scroll">
        <table>
          <thead>
            <tr>
              <th v-for="(column, i) in action.result.value.columns" :key="i">
                {{ column }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in action.result.value.rows" :key="i">
              <td v-for="(value, j) in row" :key="j">
                <pre>{{ textValue(value) }}</pre>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>
