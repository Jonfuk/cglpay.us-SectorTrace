import { computed } from 'vue'

// The operator's own name, recorded on every decision as the `*_by` field.
//
// There is no authentication, by explicit project decision — the security model
// is the JSON content-type + same-origin Origin guard on writes, not a login.
// So the reviewer identity is operator-entered and persisted per browser, and a
// decision cannot be submitted without one: every promotion, rejection, and
// verification carries a named human, which is the point of the human-in-the-
// loop rule. This is an accountability label, not an access control.
const KEY = 'st.admin.reviewer'
const VERSION = 1

export function useReviewer() {
  const store = useLocalStore<string>(KEY, VERSION, () => '')
  const name = useState<string>('admin-reviewer', () => store.read())

  const set = (value: string) => {
    const trimmed = value.trim()
    name.value = trimmed
    store.write(trimmed)
  }

  const isSet = computed(() => name.value.trim().length > 0)

  return { name, set, isSet }
}
