<script setup lang="ts">
// Operator shell. The module list mirrors the legacy operator UI's sections so
// operator bookmarks and section labels are preserved through migration.
// Modules are enabled as their pages land in later stages.
interface NavItem {
  to: string
  label: string
}

// Mirrors the legacy operator UI's tab groups so operator bookmarks and section
// labels are preserved. Read-only views land first; write-action modules
// (promote/reject/decide) follow in a later stage.
const nav: NavItem[] = [
  { to: '/', label: 'Overview' },
  { to: '/review', label: 'Review' },
  { to: '/candidates', label: 'Candidates' },
  { to: '/census', label: 'Census' },
  { to: '/claims', label: 'Claims' },
  { to: '/claimreview', label: 'Claim review' },
  { to: '/search', label: 'Search' },
  { to: '/exports', label: 'Exports' },
  { to: '/pipeline', label: 'Pipeline' },
  { to: '/analysis', label: 'Analysis' },
  { to: '/health', label: 'Health' },
]

// The operator's own name, recorded on every decision. No authentication (by
// project decision); this is an accountability label required before any write.
const reviewer = useReviewer()
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <header class="border-b border-black/10 dark:border-white/10 bg-[var(--st-accent)]/5">
      <div class="mx-auto max-w-7xl px-4 py-3 flex items-center gap-6">
        <NuxtLink to="/" class="font-semibold text-lg tracking-tight">
          SectorTrace <span class="opacity-60 font-normal">Operations</span>
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
        <label class="text-xs opacity-70 flex items-center gap-2 shrink-0">
          Reviewer
          <input
            :value="reviewer.name.value"
            type="text"
            placeholder="your name"
            class="text-sm border rounded px-2 py-1 bg-transparent w-32"
            :class="reviewer.isSet.value
              ? 'border-black/15 dark:border-white/15'
              : 'border-amber-500'"
            @change="reviewer.set(($event.target as HTMLInputElement).value)"
          >
        </label>
      </div>
    </header>

    <main id="main" class="flex-1 mx-auto w-full max-w-7xl px-4 py-6">
      <slot />
    </main>
  </div>
</template>
