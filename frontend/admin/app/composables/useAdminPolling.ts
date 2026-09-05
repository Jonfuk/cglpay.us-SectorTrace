export function useAdminPolling(
  refresh: () => Promise<unknown>,
  milliseconds: number,
) {
  let timer: ReturnType<typeof setTimeout> | undefined
  let disposed = false
  async function tick() {
    if (disposed) return
    if (!document.hidden) {
      try {
        await refresh()
      } catch {
        /* the panel owns its error */
      }
    }
    if (!disposed) timer = setTimeout(tick, milliseconds)
  }
  onMounted(() => {
    timer = setTimeout(tick, milliseconds)
  })
  onUnmounted(() => {
    disposed = true
    clearTimeout(timer)
  })
}
