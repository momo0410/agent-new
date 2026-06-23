<template>
  <div class="payloader-toolbar">
    <div class="payloader-toolbar__left">
      <slot name="left"></slot>
    </div>
    <div class="payloader-toolbar__center">
      <slot name="center"></slot>
    </div>
    <div class="payloader-toolbar__right">
      <slot name="right"></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.payloader-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md) var(--spacing-lg);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  gap: var(--spacing-md);
}

.payloader-toolbar__left,
.payloader-toolbar__center,
.payloader-toolbar__right {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.payloader-toolbar__center {
  flex: 1;
  justify-content: center;
}

.payloader-toolbar__right {
  justify-content: flex-end;
}
</style>
