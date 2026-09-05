<script setup lang="ts">
const props = defineProps<{ name: string }>();
const paths: Record<string, string> = {
  '/': 'M3 10 12 3 21 10M5 9v12h14V9M9 21v-7h6v7',
  '/review': 'M6 3h12v18H6zM9 7h6M9 11h6M9 15h3',
  '/candidates': 'M4 5h7l2 3h7v13H4zM7 2h6l3 3h4',
  '/census': 'M4 21v-8h4v8M10 21V8h4v13M16 21V3h4v18',
  '/claimreview': 'm4 12 5 5L20 6',
  '/claims': 'M4 4h16v13H9l-5 4zM8 8h8M8 12h6',
  '/search': 'M16 16 21 21M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  '/exports': 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  '/pipeline': 'M4 4h5v5H4zM15 15h5v5h-5zM9 6h8v9M6 9v8h9',
  '/analysis': 'M4 20V4m0 16h16M7 14l4-5 4 3 5-8',
  '/health': 'M2 12h5l3-8 4 16 3-8h5',
  '/aliases': 'M3 7h17m-4-4 4 4-4 4M21 17H4m4-4-4 4 4 4',
  '/qc': 'M3 3h8v8H3zM15 3h6v8h-6zM3 15h8v6H3zm12 2 2 3 5-6',
  '/parser-replay': 'M4 9a8 8 0 1 1 0 7M4 3v6h6',
  '/review-analytics': 'M3 21h18M6 17V9m6 8V3m6 14v-5',
  '/database':
    'M3 6c0-5 18-5 18 0v12c0 5-18 5-18 0zM3 6c0 5 18 5 18 0M3 12c0 5 18 5 18 0',
  '/sql': 'm8 6-6 6 6 6m8-12 6 6-6 6m-3-14-2 16',
  '/lineage': 'M9 2h6v6H9zM2 16h6v6H2zm14 0h6v6h-6zM12 8v4M5 16v-4h14v4',
};
</script>
<template>
  <svg
    viewBox="0 0 24 24"
    width="18"
    height="18"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[props.name] || paths['/review']" />
  </svg>
</template>
