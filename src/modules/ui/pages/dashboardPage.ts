import type { SystemInfo } from '../../ssh/sshManager';
import type { DashboardRenderer } from '../dashboardRenderer';
import type { AppState } from '../pageTypes';

export interface DashboardPageContext {
  dashboardRenderer: DashboardRenderer;
  systemInfo?: SystemInfo;
  theme: AppState['theme'];
}

export function renderDashboardPage(context: DashboardPageContext): string {
  const theme = context.theme || 'dark';
  return `
    <div class="dashboard-page-root">
      ${context.dashboardRenderer.renderDashboard(context.systemInfo, theme)}
    </div>
  `;
}
