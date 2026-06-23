/**
 * 状态管理器
 * 负责应用状态的管理和同步
 */
import type { AppState } from '../ui/pageTypes';
import type { ModernUIRenderer } from '../ui/modernUIRenderer';
import type { AppPage, PageState } from '../ui/pageTypes';
import { DEFAULT_PAGE, DEFAULT_UI_MODE } from '../ui/pageTypes';
import { EventEmitter } from '../utils/EventEmitter';
export class StateManager extends EventEmitter<AppState> {
  private state: AppState;
  private uiRenderer?: ModernUIRenderer;
  private pageStates: Record<string, Partial<PageState>> = {};

  constructor() {
    super();
    this.state = {
      theme: 'light',
      uiMode: DEFAULT_UI_MODE,
      isConnected: false,
      currentServer: undefined,
      serverInfo: undefined,
      loading: false,
      currentPage: DEFAULT_PAGE,
    };
  }
  /**
   * 初始化状态管理器
   */
  async initialize(): Promise<void> {
    try {
      // 从本地存储加载状态
      await this.loadStateFromStorage();
      
      // 从后端加载状态
      await this.loadStateFromBackend();
      
      console.log('状态管理器初始化完成');
    } catch (error) {
      console.error('状态管理器初始化失败:', error);
    }
  }
  /**
   * 从本地存储加载状态
   */
  private async loadStateFromStorage(): Promise<void> {
    try {
      // 加载主题
      const savedTheme = localStorage.getItem('LERT-theme');
      if (savedTheme && ['light', 'dark'].includes(savedTheme)) {
        this.state.theme = savedTheme as 'light' | 'dark';
      }
      // 加载UI模式
      const savedStateStr = localStorage.getItem('LERT-state');
      if (savedStateStr) {
        const savedState = JSON.parse(savedStateStr);
        if (savedState.uiMode && savedState.uiMode === 'classic') {
          this.state.uiMode = 'classic';
        }
      }
    } catch (error) {
      console.error('从本地存储加载状态失败:', error);
      // 加载失败回退默认值
      this.state.uiMode = DEFAULT_UI_MODE;
      this.state.currentPage = DEFAULT_PAGE;
    }
  }
  /**
   * 从后端加载状态
   */
  private async loadStateFromBackend(): Promise<void> {
    try {
      // 这里可以调用后端API加载状态
      // const backendState = await invoke('get_app_state');
      // if (backendState) {
      //   this.setState(backendState);
      // }
    } catch (error) {
      console.error('从后端加载状态失败:', error);
    }
  }
  /**
   * 获取当前状态
   */
  getState(): AppState {
    return { ...this.state };
  }
  /**
   * 设置状态
   */
  setState(newState: Partial<AppState>): void {
    const oldState = { ...this.state };
    this.state = { ...this.state, ...newState };
    
    // 保存到本地存储
    this.saveStateToStorage();
    
    // 通知监听器
    this.notifyListeners();
    
    console.log('状态已更新:', { oldState, newState: this.state });
  }
  /**
   * 设置主题
   */
  setTheme(theme: 'light' | 'dark'): void {
    this.setState({ theme });
    // 应用主题到 DOM
    this.applyTheme(theme);
  }
  /**
   * 设置当前页面
   */
  setCurrentPage(page: AppPage): void {
    this.setState({ currentPage: page });
  }
  /**
   * 切换主题
   */
  toggleTheme(): 'light' | 'dark' {
    const themes: ('light' | 'dark')[] = ['light', 'dark'];
    const currentIndex = themes.indexOf(this.state.theme);
    const nextIndex = (currentIndex + 1) % themes.length;
    const newTheme = themes[nextIndex];
    
    this.setTheme(newTheme);
    return newTheme;
  }
  /**
   * 应用主题到 DOM
   */
  private applyTheme(theme: 'light' | 'dark'): void {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', theme);
      document.body.classList.remove('light-theme', 'dark-theme');
      document.body.classList.add(`${theme}-theme`);
    }
  }
  /**
   * 设置连接状态
   */
  setConnected(isConnected: boolean, server?: string, serverInfo?: any): void {
    this.setState({
      isConnected,
      currentServer: isConnected ? server : undefined,
      serverInfo: isConnected ? serverInfo : undefined
    });
  }
  /**
   * 设置加载状态
   */
  setLoading(loading: boolean): void {
    this.setState({ loading });
  }
  /**
   * 保存状态到本地存储
   */
  private saveStateToStorage(): void {
    try {
      localStorage.setItem('LERT-theme', this.state.theme);
      localStorage.setItem('LERT-state', JSON.stringify({
        theme: this.state.theme,
        uiMode: this.state.uiMode,
        // 不保存任何敏感信息
      }));
    } catch (error) {
      console.error('保存状态到本地存储失败:', error);
    }
  }
  private notifyListeners(): void {
    this.emit(this.getState());
  }
  /**
   * 保存页面状态
   */
  savePageState(pageId: string, partial: Partial<PageState>): void {
    if (!this.pageStates[pageId]) {
      this.pageStates[pageId] = {};
    }
    Object.assign(this.pageStates[pageId], partial);
  }

  /**
   * 获取页面状态
   */
  getPageState(pageId: string): Partial<PageState> {
    return { ...(this.pageStates[pageId] || {}) };
  }

  /**
   * 清除所有页面状态
   */
  clearPageStates(): void {
    this.pageStates = {};
  }

  /**
   * 重置状态
   */
  reset(): void {
    this.state = {
      theme: 'light',
      uiMode: DEFAULT_UI_MODE,
      isConnected: false,
      currentServer: undefined,
      serverInfo: undefined,
      loading: false,
      currentPage: DEFAULT_PAGE,
    };
    
    // 清除本地存储
    try {
      localStorage.removeItem('LERT-theme');
      localStorage.removeItem('LERT-state');
    } catch (error) {
      console.error('清除本地存储失败:', error);
    }
    
    // 通知监听器
    this.notifyListeners();
  }
  /**
   * 获取主题配置
   */
  getThemeConfig() {
    const themeConfigs = {
      light: {
        name: '浅色',
        icon: '',
        description: '清新明亮的浅色主题'
      },
      dark: {
        name: '深色',
        icon: '',
        description: '护眼舒适的深色主题'
      }
    };
    return themeConfigs[this.state.theme];
  }
  /**
   * 获取下一个主题配置
   */
  getNextThemeConfig() {
    const themes: ('light' | 'dark')[] = ['light', 'dark'];
    const currentIndex = themes.indexOf(this.state.theme);
    const nextIndex = (currentIndex + 1) % themes.length;
    const nextTheme = themes[nextIndex];
    const themeConfigs = {
      light: { name: '浅色', icon: '' },
      dark: { name: '深色', icon: '' }
    };
    return themeConfigs[nextTheme];
  }
  /**
   * 检查是否为深色主题
   */
  isDarkTheme(): boolean {
    return this.state.theme === 'dark';
  }
  /**
   * 检查是否为浅色主题
   */
  isLightTheme(): boolean {
    return this.state.theme === 'light';
  }
  /**
   * 设置UI渲染器
   */
  setUIRenderer(renderer: ModernUIRenderer): void {
    this.uiRenderer = renderer;
  }
  /**
   * 获取UI渲染器
   */
  getUIRenderer(): ModernUIRenderer {
    if (!this.uiRenderer) {
      throw new Error('UI渲染器未初始化');
    }
    return this.uiRenderer;
  }
}
