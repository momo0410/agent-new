<template>
  <div class="payloader-content">
    <div class="payloader-content__body">
      <slot></slot>
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.payloader-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.payloader-content__body {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-lg);
}

.payloader-content__body::-webkit-scrollbar {
  width: 8px;
}

.payloader-content__body::-webkit-scrollbar-track {
  background: var(--bg-primary);
}

.payloader-content__body::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 4px;
}

.payloader-content__body::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
}
</style>
