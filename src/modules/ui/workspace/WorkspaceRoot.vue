<template>
  <div class="workspace-pages-root">
    <template v-if="state.loading">
      <div v-html="renderer.renderLoadingStateForVue()"></div>
    </template>
    <template v-else-if="!state.isConnected">
      <div v-html="renderer.renderConnectionPromptForVue()"></div>
    </template>
    <template v-else>
      <template v-for="pageId in pageIds" :key="pageId">
        <LegacyPageHost
          v-if="pageId !== 'payloader'"
          :page-id="pageId"
          :visible="state.currentPage === pageId"
          :renderer="renderer"
        />
      </template>
      <div
        id="page-payloader"
        class="page-container"
        v-show="state.currentPage === 'payloader'"
      >
        <PayloaderPage />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue';
import PayloaderPage from '../../payloader/PayloaderPage.vue';
import LegacyPageHost from './LegacyPageHost.vue';
import type { StateManager } from '../../core/stateManager';
import type { ModernUIRenderer } from '../modernUIRenderer';
import { ALL_PAGE_IDS, type AppState } from '../pageTypes';

const props = defineProps<{
  stateManager: StateManager;
  renderer: ModernUIRenderer;
}>();

const pageIds = ALL_PAGE_IDS;
const state = ref<AppState>(props.stateManager.getState());

const handleStateChange = (nextState: AppState) => {
  state.value = nextState;
};

onMounted(() => {
  props.stateManager.addListener(handleStateChange);
});

onBeforeUnmount(() => {
  props.stateManager.removeListener(handleStateChange);
});
</script>

<style scoped>
.workspace-pages-root {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  flex-direction: column;
}
</style>
