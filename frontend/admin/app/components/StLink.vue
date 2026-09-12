<script setup lang="ts">
import { computed } from 'vue'

// The only component allowed to render a source-derived URL as a hyperlink.
//
// Warehouse and source-derived values reach the DOM as text, never as markup
// (v-html is prohibited on such values). A destination URL is the one exception
// that must become an attribute — and it is validated here: only http(s) is
// permitted, so a `javascript:`, `data:`, `vbscript:`, or relative-scheme value
// coming from source data can never become an executable or exfiltrating link.
// An invalid destination renders as inert text, not a link.
const props = withDefaults(
  defineProps<{
    href: string | null | undefined
    /** Open in a new tab (adds rel=noopener noreferrer). Default true for
     *  external evidence sources. */
    external?: boolean
  }>(),
  { external: true },
)

const safeHref = computed<string | null>(() => {
  const raw = props.href
  if (!raw || typeof raw !== 'string') return null
  let url: URL
  try {
    url = new URL(raw)
  } catch {
    return null
  }
  return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
})
</script>

<template>
  <a
    v-if="safeHref"
    :href="safeHref"
    :target="external ? '_blank' : undefined"
    :rel="external ? 'noopener noreferrer' : undefined"
    class="text-[var(--st-accent)] underline underline-offset-2 break-words"
  >
    <slot>{{ safeHref }}</slot>
  </a>
  <span v-else class="opacity-70 break-words">
    <slot>{{ href ?? '—' }}</slot>
  </span>
</template>
