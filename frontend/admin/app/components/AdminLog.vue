<script setup lang="ts">
defineProps<{ text: string }>();
const follow = ref(true),
  element = ref<HTMLElement | null>(null);
function scroll() {
  const e = element.value;
  if (e) follow.value = e.scrollHeight - e.scrollTop - e.clientHeight < 30;
}
function latest() {
  follow.value = true;
  if (element.value) element.value.scrollTop = element.value.scrollHeight;
}
onUpdated(() => {
  if (follow.value) latest();
});
</script>
<template>
  <div>
    <div class="admin-actions justify-between mb-2">
      <span class="admin-note">{{
        follow ? 'Following latest output' : 'Reading earlier output'
      }}</span
      ><UButton color="neutral" variant="outline" size="xs" @click="latest"
        >Follow latest</UButton
      >
    </div>
    <pre
      ref="element"
      class="admin-log"
      tabindex="0"
      aria-label="Job log"
      @scroll="scroll"
      >{{ text }}</pre
    >
  </div>
</template>
