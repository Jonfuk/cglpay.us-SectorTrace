export function useUnsavedAdmin(dirty: () => boolean) {
  const dialog = useAdminDialog()
  // In-app navigation can use an accessible dialog; closing the browser still
  // needs its native beforeunload gate because custom UI cannot delay closing.
  onBeforeRouteLeave(
    async () =>
      !dirty() ||
      (await dialog.confirm('Leave this workspace and discard unsaved edits?')),
  )
  function beforeUnload(event: BeforeUnloadEvent) {
    if (dirty()) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onUnmounted(() => window.removeEventListener('beforeunload', beforeUnload))
}
