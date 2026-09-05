interface DialogRequest {
  message: string
  input: boolean
  initial: string
  returnFocus: HTMLElement | null
  resolve: (value: string | null) => void
}
// Cancellation is distinct from an empty note. The caller retains ownership
// of the actual write and its error state; a dialog cannot mutate evidence.
const request = shallowRef<DialogRequest | null>(null)
export function useAdminDialog() {
  function ask(message: string, input = false, initial = '') {
    if (request.value) return Promise.resolve(null)
    const returnFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null
    return new Promise<string | null>((resolve) => {
      request.value = { message, input, initial, returnFocus, resolve }
    })
  }
  function finish(value: string | null) {
    const current = request.value
    request.value = null
    current?.resolve(value)
    // Lazy removal has no persistent DialogTrigger. Restore the invoking
    // control after teardown, unless the action opened its next confirmation.
    void nextTick(() => {
      if (!request.value && current?.returnFocus?.isConnected)
        current.returnFocus.focus({ preventScroll: true })
    })
  }
  return {
    request,
    finish,
    confirm: async (message: string) => (await ask(message)) !== null,
    prompt: (message: string, initial = '') => ask(message, true, initial),
  }
}
