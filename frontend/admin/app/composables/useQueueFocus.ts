export function useQueueFocus(focused: Ref<string | number | null>) {
  let queueControl: HTMLElement | null = null
  let queueScroll = 0
  watch(focused, async (value, previous) => {
    if (!window.matchMedia('(max-width: 767px)').matches) return
    const body = document.querySelector<HTMLElement>('.admin-workspace > [data-slot=body]')
    if (value && !previous) queueScroll = body?.scrollTop || 0
    if (value && document.activeElement?.closest('.admin-queue'))
      queueControl = document.activeElement as HTMLElement
    await nextTick()
    if (value) {
      queueControl ||= document.querySelector<HTMLElement>('.admin-queue [data-active=true] button, .admin-queue button[data-active=true]')
      const heading = document.querySelector<HTMLElement>(
        '.admin-detail-pane h2',
      )
      if (heading) {
        heading.tabIndex = -1
        heading.focus()
      }
    } else {
      if (body) body.scrollTop = queueScroll
      if (queueControl?.isConnected) queueControl.focus({ preventScroll: true })
      queueControl = null
    }
  })
}
