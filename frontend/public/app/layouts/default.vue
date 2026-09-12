<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { navigationLabel } from '~/lib/navigation'
const route = useRoute()
const theme = useColorMode()
const navOpen = ref(false)
const drawerUsed = ref(false)
const compact = ref(false)
const status = ref('')
const linkNotice = useState('research-link-notice', () => ({ path: '', messages: [] as string[] }))
const saved = useSavedSearches()
const notebook = useNotebook()
const layoutStore = useLocalStore<boolean>('st.sidebar', 1, () => false)
onMounted(() => { compact.value = layoutStore.read() === true })
function toggleSidebar() { compact.value = !compact.value; layoutStore.write(compact.value) }
function openNavigation() { drawerUsed.value = true; navOpen.value = true }
function skipContent() { document.getElementById('main')?.focus() }
function currentTitle() { return document.title.replace(/\s*[·—]\s*SectorTrace.*$/, '') || 'SectorTrace' }
function saveView() {
  const stored = saved.save(currentTitle(), `#${route.fullPath}`)
  status.value = stored ? 'View saved in this browser.' : 'View kept for this visit. Browser storage is unavailable.'
}
function noteView() {
  const stored = notebook.add({ title: currentTitle(), href: `#${route.fullPath}` })
  status.value = stored ? 'Reference added to your notebook.' : 'Reference kept for this visit. Browser storage is unavailable.'
}
watch(() => route.path, async () => {
  navOpen.value = false
  status.value = ''
  await nextTick()
  const heading = document.querySelector<HTMLElement>('main h1')
  heading?.setAttribute('tabindex', '-1')
  heading?.focus({ preventScroll: true })
})
</script>
<template>
  <div class="st-shell" :class="{ 'sidebar-compact': compact }">
    <a href="#main" class="st-skip" @click.prevent="skipContent">Skip to content</a>
    <header class="st-topbar">
      <NuxtLink to="/" class="st-brand">SectorTrace<span class="st-brand-dot" aria-hidden="true">.</span></NuxtLink>
      <span class="st-topbar-context">England's substance misuse sector</span>
      <NuxtLink to="/search" class="atlas-button st-global-search">Search</NuxtLink>
      <label class="st-theme"><span class="sr-only">Colour theme</span>
        <select v-model="theme.preference" aria-label="Colour theme"><option value="dark">Dark</option><option value="light">Light</option><option value="system">System</option></select>
      </label>
      <button type="button" class="atlas-button st-sections" :aria-expanded="navOpen" @click="openNavigation">Sections</button>
    </header>
    <aside class="st-sidebar" aria-label="Sections">
      <button type="button" class="st-collapse" :aria-expanded="!compact" :aria-label="compact ? 'Expand sidebar' : 'Collapse sidebar'" @click="toggleSidebar">{{ compact ? '»' : '« Collapse' }}</button>
      <StNavigation :compact="compact" />
    </aside>
    <div class="st-workspace">
      <div class="st-contextbar">
        <div aria-label="Location"><NuxtLink to="/">Overview</NuxtLink><span v-if="route.path !== '/'"> / {{ navigationLabel(route.path) }}</span></div>
        <div class="st-page-actions"><button type="button" class="atlas-button" @click="saveView">Save view</button><button type="button" class="atlas-button" @click="noteView">Add note</button></div>
      </div>
      <p v-if="status" role="status" class="st-save-status">{{ status }}</p>
      <div v-if="linkNotice.messages.length" role="status" class="st-save-status"><p v-for="message in linkNotice.messages" :key="message">{{ message }}</p><button type="button" class="atlas-button" @click="linkNotice.messages = []">Dismiss</button></div>
      <main id="main" tabindex="-1" class="st-main"><slot /></main>
      <footer class="st-footer"><span>Published evidence with sources and limitations.</span><NuxtLink to="/about">About</NuxtLink><NuxtLink to="/coverage">Evidence coverage</NuxtLink><NuxtLink to="/api">API</NuxtLink></footer>
    </div>
    <LazyStNavigationDrawer v-if="drawerUsed" v-model:open="navOpen" />
  </div>
</template>
