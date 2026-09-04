<script setup lang="ts">
// The public shell: masthead + primary navigation + routed content. The nav
// mirrors the legacy portal's route set so deep links and section labels are
// preserved through the migration. Routes are declared as data; pages are
// added under app/pages as each is ported to parity.
interface NavItem {
  to: string
  label: string
}

// Ordering and labels track the legacy portal's primary navigation. Entries
// are enabled as their pages land; this foundation ships the shell and the
// overview route, with the rest scaffolded in subsequent stages.
const nav: NavItem[] = [
  { to: '/', label: 'Overview' },
  { to: '/pay', label: 'Pay' },
  { to: '/contracts', label: 'Contracts' },
  { to: '/providers', label: 'Providers' },
  { to: '/geography', label: 'Places' },
  { to: '/treatment', label: 'Treatment' },
  { to: '/cqc', label: 'CQC' },
  { to: '/pfd', label: 'PFD' },
  { to: '/relationships', label: 'Relationships' },
  { to: '/claims', label: 'Claims' },
  { to: '/documents', label: 'Documents' },
  { to: '/compare', label: 'Compare' },
  { to: '/cooccurrence', label: 'Co-occurrence' },
  { to: '/changes', label: 'Changes' },
  { to: '/calendar', label: 'Calendar' },
  { to: '/catalogue', label: 'Catalogue' },
  { to: '/api', label: 'API' },
]

const library: NavItem[] = [
  { to: '/notebook', label: 'Notebook' },
  { to: '/saved', label: 'Saved' },
  { to: '/journey', label: 'Journey' },
]

// The reader's per-browser collections. Save keeps the current filtered view;
// Note pins the current page into the notebook. Both act on the live URL and
// title, so a "filtered view is a link" stays true.
const saved = useSavedSearches()
const notebook = useNotebook()

function currentTitle(): string {
  if (typeof document === 'undefined') return 'SectorTrace'
  return document.title.replace(/\s*·\s*SectorTrace.*/, '').replace(/^SectorTrace\s*[—-]\s*/, '') || 'SectorTrace'
}
function currentHref(): string {
  return typeof location !== 'undefined' ? (location.hash || '#/') : '#/'
}
function saveView() {
  saved.save(currentTitle(), currentHref())
}
function noteView() {
  notebook.add({ title: currentTitle(), href: currentHref() })
}
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <header class="border-b border-black/10 dark:border-white/10">
      <div class="mx-auto max-w-6xl px-4 py-3 flex items-center gap-6">
        <NuxtLink to="/" class="font-semibold text-lg tracking-tight">
          SectorTrace
        </NuxtLink>
        <nav class="flex flex-wrap gap-x-4 gap-y-1 text-sm flex-1">
          <NuxtLink
            v-for="item in nav"
            :key="item.to"
            :to="item.to"
            class="opacity-70 hover:opacity-100"
            active-class="opacity-100 font-medium"
          >
            {{ item.label }}
          </NuxtLink>
        </nav>
        <div class="flex items-center gap-2 shrink-0">
          <button
            type="button"
            class="text-xs opacity-70 hover:opacity-100"
            title="Save this filtered view"
            @click="saveView"
          >☆ Save</button>
          <button
            type="button"
            class="text-xs opacity-70 hover:opacity-100"
            title="Pin this page to your notebook"
            @click="noteView"
          >✎ Note</button>
        </div>
      </div>
      <div class="mx-auto max-w-6xl px-4 pb-2 flex gap-x-4 text-xs">
        <NuxtLink
          v-for="item in library"
          :key="item.to"
          :to="item.to"
          class="opacity-60 hover:opacity-100"
          active-class="opacity-100 font-medium"
        >{{ item.label }}</NuxtLink>
      </div>
    </header>

    <main id="main" class="flex-1 mx-auto w-full max-w-6xl px-4 py-6">
      <slot />
    </main>

    <footer class="border-t border-black/10 dark:border-white/10 text-xs opacity-60">
      <div class="mx-auto max-w-6xl px-4 py-3">
        Public-domain evidence. Every figure carries its source, fetch time, and
        content hash.
      </div>
    </footer>
  </div>
</template>
