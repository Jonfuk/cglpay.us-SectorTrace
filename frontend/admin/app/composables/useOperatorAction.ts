import { postOperator, type AdminRecord } from '~/lib/operator'
export function useOperatorAction() {
  const busy = ref(false),
    error = ref(''),
    result = shallowRef<AdminRecord | null>(null)
  async function run(
    path: string | (() => Promise<AdminRecord>),
    body?: unknown,
  ) {
    if (busy.value) return null
    busy.value = true
    error.value = ''
    try {
      result.value = await (typeof path === 'function'
        ? path()
        : postOperator(path, body))
      return result.value
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      return null
    } finally {
      busy.value = false
    }
  }
  return { busy, error, result, run }
}
