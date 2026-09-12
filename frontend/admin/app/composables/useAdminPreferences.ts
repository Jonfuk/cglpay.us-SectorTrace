export function useAdminPreferences() {
  const store = useLocalStore('st.admin.preferences', 1, () => ({
    compact: false,
    collapsed: false,
    groups: {} as Record<string, boolean>,
  }))
  const prefs = useState('admin-preferences', () => {
    const saved = store.read()
    return {
      compact: saved.compact === true,
      collapsed: saved.collapsed === true,
      groups:
        saved.groups && typeof saved.groups === 'object' ? saved.groups : {},
    }
  })
  function save() {
    store.write(prefs.value)
  }
  return { prefs, save }
}
