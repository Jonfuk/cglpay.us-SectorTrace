// The reader's own per-browser collections: a notebook of pinned evidence, a
// list of saved searches, and a journey of recently visited pages. All three
// are versioned browser storage (useLocalStore) — private to the viewer, never
// sent anywhere. They are conveniences: a failure to read or write degrades to
// an empty collection, never a broken page.
import { ref } from 'vue'

export interface NotebookEntry {
  id: string
  title: string
  href: string
  note?: string
  at: number
}

export interface SavedSearch {
  id: string
  label: string
  href: string
  at: number
}

export interface JourneyVisit {
  href: string
  label: string
  at: number
}

const NOTEBOOK_KEY = 'st.notebook'
const SAVED_KEY = 'st.saved'
const JOURNEY_KEY = 'st.journey'
const VERSION = 1
const JOURNEY_MAX = 50

function makeId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function useNotebook() {
  const store = useLocalStore<NotebookEntry[]>(NOTEBOOK_KEY, VERSION, () => [])
  const entries = ref<NotebookEntry[]>(store.read())

  const add = (entry: Omit<NotebookEntry, 'id' | 'at'>) => {
    const next: NotebookEntry = { ...entry, id: makeId(), at: Date.now() }
    entries.value = [next, ...entries.value]
    store.write(entries.value)
  }
  const remove = (id: string) => {
    entries.value = entries.value.filter((e) => e.id !== id)
    store.write(entries.value)
  }
  const clear = () => {
    entries.value = []
    store.clear()
  }
  return { entries, add, remove, clear }
}

export function useSavedSearches() {
  const store = useLocalStore<SavedSearch[]>(SAVED_KEY, VERSION, () => [])
  const searches = ref<SavedSearch[]>(store.read())

  const save = (label: string, href: string) => {
    // De-dupe by href: saving the same view twice updates its label rather
    // than stacking duplicates.
    const rest = searches.value.filter((s) => s.href !== href)
    searches.value = [{ id: makeId(), label, href, at: Date.now() }, ...rest]
    store.write(searches.value)
  }
  const remove = (id: string) => {
    searches.value = searches.value.filter((s) => s.id !== id)
    store.write(searches.value)
  }
  return { searches, save, remove }
}

export function useJourney() {
  const store = useLocalStore<JourneyVisit[]>(JOURNEY_KEY, VERSION, () => [])
  const visits = ref<JourneyVisit[]>(store.read())

  const record = (href: string, label: string) => {
    // Keep the most recent visit per href at the front, bounded length.
    const rest = visits.value.filter((v) => v.href !== href)
    visits.value = [{ href, label, at: Date.now() }, ...rest].slice(0, JOURNEY_MAX)
    store.write(visits.value)
  }
  const clear = () => {
    visits.value = []
    store.clear()
  }
  return { visits, record, clear }
}
