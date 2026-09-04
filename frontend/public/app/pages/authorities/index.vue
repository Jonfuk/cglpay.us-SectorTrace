<script setup lang="ts">
useHead({ title: 'SectorTrace — Authorities' })
</script>

<template>
  <section class="space-y-6"><div class="atlas-hero"><div><p class="atlas-kicker">Authority evidence · local commissioning areas</p><h1>Find an authority</h1><p class="atlas-lede">Choose an authority from Places to open its evidence workspace. The authority route is keyed by its ONS code so the source identity stays unambiguous.</p><NuxtLink to="/geography" class="atlas-button primary">Open Places</NuxtLink></div></div><StEmptyState title="Choose an authority from Places" message="The authority workspace opens from the Places table or map." /></section>
</template>
