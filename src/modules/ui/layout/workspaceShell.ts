import type { AppPage } from '../pageTypes';

export function renderWorkspaceShell(content: string, headerContent: string = ''): string {
  return `
    <div class="main-workspace">
      <div class="workspace-brand" aria-label="安御智测">
        <div class="workspace-brand-logo">
          <img src="/logo.png" alt="安御智测 Logo" />
        </div>
        <div class="workspace-brand-name">安御智测</div>
      </div>
      ${headerContent}
      <div class="workspace-content page-transition" id="workspace-content">
        ${content}
      </div>
    </div>
  `;
}

export function renderPageContainer(pageId: AppPage, content: string, isVisible: boolean): string {
  const display = isVisible ? 'flex' : 'none';
  return `
    <div class="page-container" id="page-${pageId}" style="display:${display}">
      ${content}
    </div>
  `;
}
