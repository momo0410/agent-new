import { reactive, readonly, computed, onMounted, onUnmounted } from 'vue';
import type { PayloadItem, PayloaderState, I18nText } from '../types';
import { webPayloads } from '../data/webPayloads';
import { intranetPayloads } from '../data/intranetPayloads';
import { toolCommands } from '../data/toolCommands';

function getText(text: I18nText, lang: 'zh' | 'en' = 'zh'): string {
  if (typeof text === 'string') return text;
  return text[lang];
}

function getAllCategories(payloads: PayloadItem[]): { id: string; label: I18nText }[] {
  const categorySet = new Set<string>();
  const categoryMap = new Map<string, I18nText>();
  
  payloads.forEach(payload => {
    const categoryKey = typeof payload.category === 'string' ? payload.category : payload.category.zh;
    if (!categorySet.has(categoryKey)) {
      categorySet.add(categoryKey);
      categoryMap.set(categoryKey, payload.category);
    }
  });
  
  return Array.from(categoryMap.entries()).map(([id, label]) => ({ id, label }));
}

export function usePayloader() {
  const state = reactive<PayloaderState>({
    isLoading: false,
    error: null,
    webPayloads: [],
    intranetPayloads: [],
    toolCommands: [],
    selectedCategory: 'all',
    searchQuery: '',
    isInitialized: false,
    currentView: 'web',
    viewMode: 'list',
    selectedItemId: null,
  });

  let refreshTimer: ReturnType<typeof setTimeout> | null = null;
  let eventListenerRegistered = false;

  const currentPayloads = computed<PayloadItem[]>(() => {
    switch (state.currentView) {
      case 'web':
        return state.webPayloads;
      case 'intranet':
        return state.intranetPayloads;
      case 'tools':
        return [];
      default:
        return state.webPayloads;
    }
  });

  const categories = computed(() => {
    if (state.currentView === 'tools') {
      return [];
    }
    return [
      { id: 'all', label: { zh: '全部', en: 'All' } },
      ...getAllCategories(currentPayloads.value)
    ];
  });

  const filteredPayloads = computed<PayloadItem[]>(() => {
    let result = currentPayloads.value;
    
    if (state.selectedCategory !== 'all') {
      result = result.filter(p => {
        const categoryKey = typeof p.category === 'string' ? p.category : p.category.zh;
        return categoryKey === state.selectedCategory;
      });
    }
    
    if (state.searchQuery) {
      const query = state.searchQuery.toLowerCase();
      result = result.filter(p => {
        const name = getText(p.name).toLowerCase();
        const desc = getText(p.description).toLowerCase();
        const code = p.execution.map(e => e.command).join('\n').toLowerCase();
        return name.includes(query) || desc.includes(query) || code.includes(query);
      });
    }
    
    return result;
  });

  const loadPayloads = async (): Promise<void> => {
    state.isLoading = true;
    state.error = null;
    
    try {
      await new Promise(resolve => setTimeout(resolve, 300));
      state.webPayloads = webPayloads;
      state.intranetPayloads = intranetPayloads;
      state.toolCommands = toolCommands;
      state.isInitialized = true;
    } catch (err) {
      state.error = err instanceof Error ? err.message : '加载 Payload 失败';
      state.webPayloads = [];
      state.intranetPayloads = [];
      state.toolCommands = [];
    } finally {
      state.isLoading = false;
    }
  };

  const initialize = async (): Promise<void> => {
    if (state.isInitialized) {
      return;
    }
    await loadPayloads();
  };

  const refresh = async (): Promise<void> => {
    await loadPayloads();
  };

  const selectCategory = (categoryId: string): void => {
    state.selectedCategory = categoryId;
  };

  const setSearchQuery = (query: string): void => {
    state.searchQuery = query;
  };

  const setCurrentView = (view: 'web' | 'intranet' | 'tools'): void => {
    state.currentView = view;
    state.selectedCategory = 'all';
    state.searchQuery = '';
    state.viewMode = 'list';
    state.selectedItemId = null;
  };

  const setViewMode = (mode: 'list' | 'detail'): void => {
    state.viewMode = mode;
  };

  const setSelectedItemId = (id: string | null): void => {
    state.selectedItemId = id;
    if (id) {
      state.viewMode = 'detail';
    } else {
      state.viewMode = 'list';
    }
  };

  const copyPayload = async (code: string): Promise<boolean> => {
    try {
      await navigator.clipboard.writeText(code);
      showNotification('Payload 已复制到剪贴板', 'success');
      return true;
    } catch (err) {
      console.error('复制失败:', err);
      showNotification('复制失败', 'error');
      return false;
    }
  };

  const usePayload = (payload: PayloadItem): void => {
    console.log('使用 Payload:', payload);
    showNotification(`已选择：${getText(payload.name)}`, 'info');
  };

  const showNotification = (message: string, type: 'success' | 'error' | 'info' | 'warning' = 'info'): void => {
    const win = window as any;
    if (win.showNotification) {
      win.showNotification(message, type);
    } else {
      console.log(`[${type.toUpperCase()}] ${message}`);
    }
  };

  const reset = (): void => {
    state.selectedCategory = 'all';
    state.searchQuery = '';
    state.error = null;
  };

  const destroy = (): void => {
    if (refreshTimer) {
      clearTimeout(refreshTimer);
      refreshTimer = null;
    }
    
    state.webPayloads = [];
    state.intranetPayloads = [];
    state.toolCommands = [];
    state.isInitialized = false;
    state.error = null;
  };

  const handleKeyDown = (e: KeyboardEvent): void => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
      e.preventDefault();
      const searchInput = document.querySelector('.payloader-search-input') as HTMLInputElement;
      if (searchInput) {
        searchInput.focus();
      }
    }
  };

  onMounted(async () => {
    await initialize();
    
    if (!eventListenerRegistered) {
      document.addEventListener('keydown', handleKeyDown);
      eventListenerRegistered = true;
    }
  });

  onUnmounted(() => {
    if (eventListenerRegistered) {
      document.removeEventListener('keydown', handleKeyDown);
      eventListenerRegistered = false;
    }
    destroy();
  });

  return {
    state: readonly(state),
    filteredPayloads: computed(() => filteredPayloads.value),
    categories: computed(() => categories.value),
    isLoading: computed(() => state.isLoading),
    error: computed(() => state.error),
    initialize,
    refresh,
    selectCategory,
    setSearchQuery,
    setCurrentView,
    setViewMode,
    setSelectedItemId,
    copyPayload,
    usePayload,
    reset,
    destroy,
  };
}

export default usePayloader;
