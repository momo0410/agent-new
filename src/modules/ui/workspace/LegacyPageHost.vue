<template>
  <div
    :id="`page-${pageId}`"
    class="page-container"
    v-show="visible"
    v-html="html"
  ></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, watch, ref } from 'vue';
import type { AppPage } from '../pageTypes';
import type { ModernUIRenderer } from '../modernUIRenderer';

const props = defineProps<{
  pageId: AppPage;
  visible: boolean;
  renderer: ModernUIRenderer;
}>();

const html = ref('');

function renderPage() {
  html.value = props.renderer.getPageHTMLForVue(props.pageId);
}

function handleRefresh(event: Event) {
  const detail = (event as CustomEvent<{ pageId?: AppPage }>).detail;
  if (!detail?.pageId || detail.pageId === props.pageId) {
    renderPage();
  }
}

watch(
  () => props.visible,
  (next, prev) => {
    if (next && !prev) {
      props.renderer.activatePageForVue(props.pageId);
    } else if (!next && prev) {
      props.renderer.deactivatePageForVue(props.pageId);
    }
  }
);

onMounted(() => {
  renderPage();
  window.addEventListener('workspace-page-refresh', handleRefresh as EventListener);
  if (props.visible) {
    props.renderer.activatePageForVue(props.pageId);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener('workspace-page-refresh', handleRefresh as EventListener);
  if (props.visible) {
    props.renderer.deactivatePageForVue(props.pageId);
  }
});
</script>
