<script setup lang="ts">
import { adminNavigation } from '~/lib/navigation';
const route = useRoute();
const reviewer = useReviewer();
const { prefs, save } = useAdminPreferences();
const dialog = useAdminDialog();
const colorMode = useColorMode();
const searchOpen = ref(false);
const term = ref('');
watch(searchOpen, async (value) => {
  if (!value) {
    await nextTick();
    document
      .querySelector<HTMLButtonElement>('[aria-label="Search commands"]')
      ?.focus();
  }
});
const mobileOpen = ref(false);
watch(mobileOpen, async (value) => {
  if (!value) {
    await nextTick();
    document
      .querySelector<HTMLButtonElement>('[aria-label="Open navigation"]')
      ?.focus();
  }
});
const current = computed(() =>
  adminNavigation.find((i) => i.to === route.path),
);
const matches = computed(() =>
  adminNavigation.filter((i) =>
    `${i.label} ${i.group}`.toLowerCase().includes(term.value.toLowerCase()),
  ),
);
function shortcut(e: KeyboardEvent) {
  if (
    (e.target as HTMLElement)?.closest(
      'input, textarea, select, [contenteditable], [role=dialog]',
    )
  )
    return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    searchOpen.value = !searchOpen.value;
  }
}
onMounted(() => document.addEventListener('keydown', shortcut));
onUnmounted(() => document.removeEventListener('keydown', shortcut));
watch(
  () => route.fullPath,
  () => {
    mobileOpen.value = false;
    searchOpen.value = false;
  },
);
function focusMain() {
  document.getElementById('main')?.focus();
}
</script>
<template>
  <a class="skip-link" href="#main" @click.prevent="focusMain"
    >Skip to content</a
  >
  <UDashboardGroup
    unit="px"
    :persistent="false"
    class="admin-shell"
    :data-density="prefs.compact ? 'compact' : 'comfortable'"
  >
    <aside
      class="admin-sidebar admin-desktop-sidebar"
      :style="{ width: prefs.collapsed ? '64px' : '256px' }"
    >
      <NuxtLink
        to="/"
        class="admin-brand p-4 h-[74px]"
        aria-label="SectorTrace Operations"
        ><span class="brand-mark" aria-hidden="true">S</span
        ><span v-if="!prefs.collapsed"
          >SectorTrace<span class="block text-xs font-normal opacity-70"
            >Operator workspace</span
          ></span
        ></NuxtLink
      >
      <div class="flex-1 overflow-auto">
        <AdminNavigation :collapsed="prefs.collapsed" />
      </div>
      <div class="p-3">
        <UButton
          color="neutral"
          variant="ghost"
          :aria-label="prefs.collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
          :aria-expanded="!prefs.collapsed"
          @click="
            prefs.collapsed = !prefs.collapsed;
            save();
          "
          >{{ prefs.collapsed ? '»' : '«'
          }}<span v-if="!prefs.collapsed">Collapse sidebar</span></UButton
        >
      </div>
    </aside>
    <UDashboardPanel
      class="admin-workspace"
      :ui="{ root: 'min-h-0', body: 'p-0 sm:p-0 gap-0 sm:gap-0' }"
    >
      <template #header>
        <UDashboardNavbar
          :toggle="false"
          class="admin-toolbar"
          :ui="{ left: 'min-w-0', right: 'gap-2' }"
        >
          <template #leading
            ><UButton
              class="lg:hidden"
              aria-label="Open navigation"
              color="neutral"
              variant="ghost"
              @click="mobileOpen = true"
              >☰</UButton
            ></template
          >
          <template #title
            ><span class="text-sm font-normal opacity-70 hidden sm:inline"
              >{{ current?.group }} <span class="mx-2">/</span></span
            ><span class="text-sm">{{
              current?.label || 'Operations'
            }}</span></template
          >
          <template #right>
            <UButton
              aria-label="Search commands"
              color="neutral"
              variant="ghost"
              @click="searchOpen = true"
              >⌕ <span class="hidden lg:inline">Jump to…</span
              ><kbd class="hidden xl:inline text-xs">Ctrl K</kbd></UButton
            >
            <label class="admin-field"
              ><span class="sr-only">Theme</span
              ><select
                v-model="colorMode.preference"
                aria-label="Theme"
                class="text-xs"
              >
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select></label
            >
            <UButton
              color="neutral"
              variant="ghost"
              aria-label="Compact spacing"
              :aria-pressed="prefs.compact"
              @click="
                prefs.compact = !prefs.compact;
                save();
              "
              >☷</UButton
            >
            <a href="/" class="text-xs hidden xl:inline">Public portal ↗</a>
          </template>
        </UDashboardNavbar>
        <div
          class="flex flex-wrap items-center justify-between gap-2 px-5 py-2 border-b border-black/10 text-xs"
        >
          <AdminRunIndicator />
          <label class="flex items-center gap-2"
            ><span class="opacity-70">Reviewer</span
            ><input
              id="admin-reviewer"
              :value="reviewer.name.value"
              autocomplete="name"
              placeholder="Your name"
              aria-label="Reviewer name"
              class="w-36 text-xs"
              @change="reviewer.set(($event.target as HTMLInputElement).value)"
            /><span
              v-if="!reviewer.isSet.value"
              class="opacity-70 hidden sm:inline"
              >Required for decisions</span
            ></label
          >
        </div>
      </template>
      <template #body
        ><main id="main" tabindex="-1" class="admin-content"><slot /></main
      ></template>
    </UDashboardPanel>
  </UDashboardGroup>
  <LazyUSlideover
    v-if="mobileOpen"
    v-model:open="mobileOpen"
    side="left"
    title="SectorTrace navigation"
    description="Operator workspaces"
    :ui="{ content: 'max-w-72', body: 'p-0' }"
    ><template #body
      ><AdminNavigation /><a href="/" class="block p-5"
        >Public portal ↗</a
      ></template
    ></LazyUSlideover
  >
  <LazyUModal
    v-if="searchOpen"
    v-model:open="searchOpen"
    title="Jump to a workspace"
    description="Search navigation. Commands open a workspace; they never submit a decision."
  >
    <template #body
      ><input
        v-model="term"
        autofocus
        type="search"
        aria-label="Search workspaces"
        placeholder="Review, database, pipeline…"
        class="w-full mb-4" />
      <div class="max-h-96 overflow-auto">
        <NuxtLink
          v-for="item in matches"
          :key="item.to"
          :to="item.to"
          class="admin-nav-link"
          @click="searchOpen = false"
          ><AdminIcon :name="item.to" />{{ item.label
          }}<span class="ml-auto text-xs opacity-70">{{
            item.group
          }}</span></NuxtLink
        >
        <p v-if="!matches.length" class="admin-note">No matching workspaces.</p>
      </div>
      <LazyAdminPaletteCatalogue :term="term" @navigate="searchOpen = false"
    /></template>
  </LazyUModal>
  <LazyAdminDialog v-if="dialog.request.value" />
</template>
