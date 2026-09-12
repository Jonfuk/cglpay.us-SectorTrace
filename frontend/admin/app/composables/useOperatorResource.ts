import { getOperator, type AdminRecord } from '~/lib/operator'
export function useOperatorResource(
  path: MaybeRefOrGetter<string>,
  query: MaybeRefOrGetter<
    Record<string, string | number | boolean | undefined | null>
  > = {},
  immediate = true,
) {
  const data = shallowRef<AdminRecord | null>(null)
  const pending = ref(false)
  const error = ref('')
  let controller: AbortController | undefined
  let sequence = 0
  async function refresh() {
    const ticket = ++sequence
    controller?.abort()
    controller = new AbortController()
    pending.value = true
    error.value = ''
    try {
      const result = await getOperator(
        toValue(path),
        toValue(query),
        controller.signal,
      )
      if (ticket === sequence) data.value = result
    } catch (e) {
      if (ticket === sequence && !controller.signal.aborted)
        error.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (ticket === sequence) pending.value = false
    }
  }
  watch(
    () => [toValue(path), toValue(query)],
    () => {
      if (immediate) void refresh()
    },
    { deep: true, immediate },
  )
  onScopeDispose(() => {
    sequence++
    controller?.abort()
  })
  return { data, pending, error, refresh }
}
