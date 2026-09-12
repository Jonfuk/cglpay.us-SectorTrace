<script setup lang="ts">
const dialog = useAdminDialog();
const answer = ref(dialog.request.value?.initial ?? '');
watch(dialog.request, (value) => {
  answer.value = value?.initial ?? '';
});
</script>
<template>
  <UModal
    :open="!!dialog.request.value"
    title="Confirm action"
    description="Review the details before continuing."
    @update:open="
      (value) => {
        if (!value) dialog.finish(null);
      }
    "
  >
    <template #body
      ><form id="admin-confirm" @submit.prevent="dialog.finish(answer)">
        <p class="whitespace-pre-wrap">{{ dialog.request.value?.message }}</p>
        <label v-if="dialog.request.value?.input" class="admin-field mt-4"
          >Your response<textarea v-model="answer" rows="3" autofocus />
        </label></form
    ></template>
    <template #footer
      ><UButton color="neutral" variant="outline" @click="dialog.finish(null)"
        >Cancel</UButton
      ><UButton type="submit" form="admin-confirm">Continue</UButton></template
    >
  </UModal>
</template>
