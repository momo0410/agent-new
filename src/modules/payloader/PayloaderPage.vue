<template>
  <div class="payloader-page">
    <PayloaderToolbar>
      <template #left>
        <div class="payloader-toolbar-left">
          <button 
            v-if="state.viewMode === 'detail'"
            class="payloader-back-btn"
            @click="goBack"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M15 18l-6-6 6-6"></path>
            </svg>
            返回
          </button>
          <template v-else>
            <div class="payloader-dropdowns">
              <div class="payloader-dropdown">
                <button 
                  class="payloader-dropdown-btn"
                  @click="toggleViewDropdown"
                >
                  {{ getViewLabel(state.currentView) }}
                  <svg class="payloader-dropdown-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M6 9l6 6 6-6"></path>
                  </svg>
                </button>
                <div v-if="showViewDropdown" class="payloader-dropdown-menu">
                  <button 
                    v-for="view in views" 
                    :key="view.id"
                    :class="['payloader-dropdown-item', { active: state.currentView === view.id }]"
                    @click="selectView(view.id)"
                  >
                    {{ view.label }}
                  </button>
                </div>
              </div>

              <div v-if="state.currentView !== 'tools'" class="payloader-dropdown">
                <button 
                  class="payloader-dropdown-btn"
                  @click="toggleCategoryDropdown"
                >
                  {{ getSelectedCategoryLabel() }}
                  <svg class="payloader-dropdown-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M6 9l6 6 6-6"></path>
                  </svg>
                </button>
                <div v-if="showCategoryDropdown" class="payloader-dropdown-menu payloader-dropdown-menu--large">
                  <button 
                    v-for="cat in categories" 
                    :key="cat.id"
                    :class="['payloader-dropdown-item', { active: state.selectedCategory === cat.id }]"
                    @click="selectCategoryWrapper(cat.id)"
                  >
                    {{ getText(cat.label) }}
                  </button>
                </div>
              </div>

              <button
                class="payloader-btn payloader-btn--tool"
                @click="selectView('tools')"
                :class="{ active: state.currentView === 'tools' }"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
                </svg>
                工具命令
              </button>

              <button
                class="payloader-btn payloader-btn--tool"
                @click="selectView('encoding')"
                :class="{ active: state.currentView === 'encoding' }"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="16 18 22 12 16 6"></polyline>
                  <polyline points="8 6 2 12 8 18"></polyline>
                </svg>
                编解码
              </button>
            </div>
          </template>
        </div>
      </template>
      <template #right>
        <div v-if="state.viewMode === 'list'" class="payloader-search-box">
          <svg class="payloader-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input 
            type="text" 
            class="payloader-search-input" 
            placeholder="搜索 payload... (Ctrl+F)"
            :value="state.searchQuery"
            @input="setSearchQuery(($event.target as HTMLInputElement).value)"
          />
        </div>
        <button
          v-if="state.viewMode === 'list'"
          class="payloader-btn payloader-btn--history"
          @click="showHistoryModal = true; loadHistory()"
          title="渗透历史"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 20v-6M6 20V10M18 20V4"></path>
          </svg>
          历史
        </button>
        <button
          v-if="state.viewMode === 'list'"
          :class="['payloader-btn', 'payloader-btn--pentest', { 'is-running': agentRunning }]"
          @click="handlePentestEntry"
          :title="agentRunning ? `${activeRunningCount} 个任务运行中` : '渗透测试'"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
            <path d="M2 17l10 5 10-5"></path>
            <path d="M2 12l10 5 10-5"></path>
          </svg>
          {{ agentRunning ? `任务 (${activeRunningCount})` : '渗透测试' }}
          <span v-if="agentRunning" class="payloader-btn-running-badge">
            <span class="payloader-btn-running-dot"></span>
            {{ activeRunningCount }}
          </span>
        </button>
        <button
          v-if="state.viewMode === 'list'"
          class="payloader-btn payloader-btn--tool"
          @click="openSkillsManager"
          title="skills管理"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 3l7 4v10l-7 4-7-4V7l7-4z"></path>
            <path d="M9 12l2 2 4-4"></path>
          </svg>
          skills管理
        </button>
        <button
          v-if="state.viewMode === 'list'"
          class="payloader-btn payloader-btn--tool"
          @click="openKnowledgeBaseManager"
          title="本地知识库管理"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 0 4 24V4.5A2.5 2.5 0 0 1 6.5 2z"></path>
          </svg>
          本地知识库管理
        </button>
        <button 
          v-if="state.viewMode === 'list'"
          class="page-refresh-btn payloader-refresh-btn" 
          @click="refresh" 
          :disabled="isLoading"
          title="刷新"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ 'spinning': isLoading }">
            <path d="M23 4v6h-6"></path>
            <path d="M1 20v-6h6"></path>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
          </svg>
          <span>刷新</span>
        </button>
      </template>
    </PayloaderToolbar>

    <PayloaderContent>
      <!-- Agent 启动确认弹窗 -->
      <div v-if="showPentestModal" class="payloader-modal-overlay" @click.self="closePentestModal">
        <div class="payloader-modal">
          <div class="payloader-modal-header">
            <h3>渗透测试</h3>
            <button class="payloader-modal-close" @click="closePentestModal">&times;</button>
          </div>
          <div class="payloader-modal-body">
            <p class="payloader-modal-desc">请输入要检测的目标 IP 地址或域名，系统会执行自动化安全验证流程。</p>
            <div class="payloader-modal-input-group">
              <label class="payloader-modal-label" for="payloader-pentest-target">目标 IP / 域名</label>
              <input
                id="payloader-pentest-target"
                v-model="pentestTarget"
                class="payloader-modal-input"
                type="text"
                placeholder="例如: 192.168.1.10 或 example.com"
                autocomplete="off"
                spellcheck="false"
                @keyup.enter="startHostAgent"
              />
              <p class="payloader-modal-helper">仅用于你已授权的目标资产。支持输入 IP 地址或域名。</p>
            </div>
            <div class="payloader-modal-input-group payloader-modal-input-group--mode">
              <label class="payloader-modal-label">执行模式</label>
              <div class="payloader-mode-toggle" role="radiogroup" aria-label="渗透任务执行模式">
                <button
                  type="button"
                  :class="['payloader-mode-toggle-btn', { active: pentestExecutionMode === 'serial' }]"
                  @click="setPentestExecutionMode('serial')"
                >
                  串行
                </button>
                <button
                  type="button"
                  :class="['payloader-mode-toggle-btn', { active: pentestExecutionMode === 'parallel' }]"
                  @click="setPentestExecutionMode('parallel')"
                >
                  并行
                </button>
              </div>
            </div>
            <div v-if="pentestModalError" class="payloader-modal-error">{{ pentestModalError }}</div>
          </div>
          <div class="payloader-modal-footer">
            <button class="payloader-btn payloader-btn--secondary" @click="closePentestModal">取消</button>
            <button
              class="payloader-btn payloader-btn--primary"
              :disabled="!normalizedPentestTarget"
              @click="startHostAgent"
            >
              {{ '开始检测' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Agent 结果弹窗 -->
      <div v-if="showResultModal" class="payloader-modal-overlay" @click.self="requestCloseResultModal">
        <div class="payloader-modal payloader-modal--result">
          <div class="payloader-modal-header">
            <div class="payloader-task-tabs">
              <button
                v-for="task in pentestTasks"
                :key="task.id"
                :class="['payloader-task-tab', { active: selectedTaskId === task.id, running: task.running, completed: !task.running && !task.error, failed: task.error }]"
                :title="`${task.target} (${task.running ? '运行中' : task.error ? '失败' : '已完成'})`"
                @click="selectedTaskId = task.id"
              >
                <span class="payloader-task-tab-dot" :class="{ running: task.running, completed: !task.running && !task.error, failed: task.error }"></span>
                <span class="payloader-task-tab-target">{{ task.target }}</span>
                <button
                  v-if="!task.running"
                  class="payloader-task-tab-close"
                  title="移除任务"
                  @click.stop="removeTask(task.id)"
                >&times;</button>
              </button>
              <button class="payloader-task-tab-add" title="新增探测任务" @click="closeResultModal(); openPentestModal()">+</button>
            </div>
            <div class="payloader-modal-header-actions">
              <button v-if="selectedTask" class="payloader-modal-header-btn" :disabled="!currentTaskId" @click="openLogModal()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                  <polyline points="14 2 14 8 20 8"></polyline>
                  <line x1="16" y1="13" x2="8" y2="13"></line>
                  <line x1="16" y1="17" x2="8" y2="17"></line>
                  <polyline points="10 9 9 9 8 9"></polyline>
                </svg>
                日志
              </button>
              <button class="payloader-modal-close" title="关闭" @click="requestCloseResultModal">&times;</button>
            </div>
          </div>
          <div class="payloader-modal-body payloader-modal-body--scroll">
            <!-- 选择任务 -->
            <div v-if="!selectedTask" class="payloader-agent-task-list">
              <p class="payloader-agent-task-list-hint" v-if="pentestTasks.length === 0">暂无任务，点击 <strong>+</strong> 启动新的渗透测试</p>
              <div v-for="task in pentestTasks" :key="task.id" class="payloader-agent-task-card" @click="selectedTaskId = task.id">
                <div class="payloader-agent-task-card-header">
                  <span class="payloader-agent-task-card-status" :class="{ running: task.running, completed: !task.running && !task.error, failed: task.error }">
                    {{ task.running ? '运行中' : task.error ? '失败' : '已完成' }}
                  </span>
                  <button v-if="!task.running" class="payloader-task-tab-close" @click.stop="removeTask(task.id)">&times;</button>
                </div>
                <div class="payloader-agent-task-card-target">{{ task.target }}</div>
                <div class="payloader-agent-task-card-meta">
                  <span>阶段: {{ getPhaseLabel(task.phase) }}</span>
                  <span v-if="task.findingsCount > 0">资产: {{ task.findingsCount }}</span>
                  <span v-if="task.vulnCount > 0">漏洞: {{ task.vulnCount }}</span>
                </div>
              </div>
            </div>

            <!-- 运行中 -->
            <div v-else-if="selectedTask?.running" class="payloader-agent-running">
              <div class="payloader-agent-running-header">
                <div class="payloader-agent-running-spinner"></div>
                <div class="payloader-agent-running-header-text">
                  <p class="payloader-agent-running-text">正在对 {{ selectedTask.target || '目标资产' }} 执行渗透测试...</p>
                  <p class="payloader-agent-running-sub">
                    <span class="payloader-agent-phase-badge">{{ getPhaseLabel(agentResult?.phase) }}</span>
                    <span v-if="agentRoundCount > 0" class="payloader-agent-round-info">第 {{ agentRoundCount }} 轮任务</span>
                    <span class="payloader-agent-pulse"></span>
                  </p>
                </div>
              </div>
              <div v-if="agentResult" class="payloader-agent-live-panel">
                <div class="payloader-agent-live-stats">
                  <div class="payloader-agent-live-stat">
                    <span class="payloader-agent-live-label">当前阶段</span>
                    <span class="payloader-agent-live-value">{{ getPhaseLabel(agentResult.phase) }}</span>
                  </div>
                  <div class="payloader-agent-live-stat">
                    <span class="payloader-agent-live-label">任务轮次</span>
                    <span class="payloader-agent-live-value">{{ agentRoundCount || 0 }} 轮</span>
                  </div>
                  <div class="payloader-agent-live-stat">
                    <span class="payloader-agent-live-label">资产发现</span>
                    <span class="payloader-agent-live-value">{{ agentResult.findings_count || 0 }} 项</span>
                  </div>
                  <div class="payloader-agent-live-stat">
                    <span class="payloader-agent-live-label">漏洞发现</span>
                    <span class="payloader-agent-live-value">{{ agentResult.vuln_count || 0 }} 项</span>
                  </div>
                  <div class="payloader-agent-live-stat payloader-agent-live-stat--token">
                    <span class="payloader-agent-live-label">Token 消耗</span>
                    <span class="payloader-agent-live-value">{{ currentTokenUsageDisplay }}</span>
                    <span class="payloader-agent-live-meta">{{ currentTokenUsageMeta }}</span>
                  </div>
                </div>
                <div v-if="currentActionSummary" class="payloader-agent-current-action">
                  <span class="payloader-agent-current-action-dot"></span>
                  <span class="payloader-agent-current-action-text">{{ currentActionSummary }}</span>
                  <span v-if="currentActionElapsed" class="payloader-agent-current-action-elapsed">{{ currentActionElapsed }}</span>
                </div>
                <pre v-if="currentPlanningStream" class="payloader-agent-planning-stream">{{ currentPlanningStream }}</pre>
                <div class="payloader-agent-live-log payloader-agent-live-log--compact">
                  <div class="payloader-agent-live-log-header">
                    <h4>执行摘要</h4>
                    <span>{{ compactRoundItems.length }} / {{ agentRoundCount || 0 }} 轮</span>
                  </div>
                  <div class="payloader-agent-log-hint">页面仅展示任务轮次概况，不显示具体动作、参数和原始输出。</div>
                  <div v-if="compactRoundItems.length > 0" class="payloader-agent-compact-list">
                    <div v-for="(round, idx) in compactRoundItems" :key="`${round.key}-${idx}`" class="payloader-agent-compact-item" :class="{ 'payloader-agent-action-running': round.hasRunning }">
                      <div class="payloader-agent-compact-top">
                        <span class="payloader-agent-action-tool" :class="{ 'payloader-agent-action-tool-active': round.hasRunning }">{{ round.title }}</span>
                        <span class="payloader-agent-action-time">{{ formatActionTime(round.time) }}</span>
                        <span v-if="round.hasRunning" class="payloader-agent-action-status-running">执行中</span>
                      </div>
                      <div class="payloader-agent-compact-line">
                        <span class="payloader-agent-action-label">概况</span>
                        <span class="payloader-agent-compact-text">{{ round.summary }}</span>
                      </div>
                      <div class="payloader-agent-compact-line">
                        <span class="payloader-agent-action-label">状态</span>
                        <span class="payloader-agent-compact-text">{{ round.statusSummary }}</span>
                      </div>
                    </div>
                  </div>
                  <div v-else class="payloader-agent-action-empty">AI 已启动，正在等待第一条执行记录...</div>
                </div>
              </div>
            </div>

            <!-- 错误 -->
            <div v-else-if="selectedTask?.error" class="payloader-agent-error">
              <div class="payloader-agent-error-icon">!</div>
              <h4 class="payloader-agent-error-title">{{ selectedTask.target }} 检测失败</h4>
              <p class="payloader-agent-error-desc">{{ selectedTask.error }}</p>
            </div>

            <!-- 结果 -->
            <div v-else-if="agentResult" class="payloader-agent-result">
              <!-- 状态栏 -->
              <div class="payloader-agent-summary">
                <div class="payloader-agent-summary-header">
                  <h3>阶段化渗透测试报告</h3>
                  <span :class="['payloader-agent-status', agentResult.status]">
                    {{ agentResult.status === 'completed' ? '已完成' : agentResult.status === 'failed' ? '失败' : '运行中' }}
                  </span>
                </div>
                <p class="payloader-agent-summary-text">
                  当前阶段：{{ getPhaseLabel(agentResult.final?.phase || agentResult.phase) }}，
                  已完成 {{ agentRoundCount || 0 }} 轮任务，
                  发现资产 {{ agentResult.findings_count || 0 }} 项，
                  发现漏洞 {{ agentResult.vuln_count || 0 }} 项。
                </p>
                <div class="payloader-agent-live-stats payloader-agent-live-stats--summary">
                  <div class="payloader-agent-live-stat">
                    <span class="payloader-agent-live-label">当前阶段</span>
                    <span class="payloader-agent-live-value">{{ getPhaseLabel(agentResult.final?.phase || agentResult.phase) }}</span>
                  </div>
                  <div class="payloader-agent-live-stat">
                    <span class="payloader-agent-live-label">任务轮次</span>
                    <span class="payloader-agent-live-value">{{ agentRoundCount || 0 }} 轮</span>
                  </div>
                  <div class="payloader-agent-live-stat">
                    <span class="payloader-agent-live-label">资产发现</span>
                    <span class="payloader-agent-live-value">{{ agentResult.findings_count || 0 }} 项</span>
                  </div>
                  <div class="payloader-agent-live-stat">
                    <span class="payloader-agent-live-label">漏洞发现</span>
                    <span class="payloader-agent-live-value">{{ agentResult.vuln_count || 0 }} 项</span>
                  </div>
                  <div class="payloader-agent-live-stat payloader-agent-live-stat--token">
                    <span class="payloader-agent-live-label">Token 消耗</span>
                    <span class="payloader-agent-live-value">{{ currentTokenUsageDisplay }}</span>
                    <span class="payloader-agent-live-meta">{{ currentTokenUsageMeta }}</span>
                  </div>
                </div>
              </div>

              <div v-if="agentResult.actions && agentResult.actions.length > 0" class="payloader-agent-section payloader-agent-live-log-section">
                <h4 class="payloader-agent-section-title">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M9 11l3 3L22 4"></path>
                    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
                  </svg>
                  AI 执行摘要
                </h4>
                <div class="payloader-agent-log-hint">页面仅展示最近任务轮次概况，不显示具体动作、参数和原始输出。</div>
                <div class="payloader-agent-compact-list">
                  <div v-for="(round, idx) in compactRoundItems" :key="`${round.key}-${idx}`" class="payloader-agent-compact-item">
                    <div class="payloader-agent-compact-top">
                      <span class="payloader-agent-action-tool">{{ round.title }}</span>
                      <span class="payloader-agent-action-time">{{ formatActionTime(round.time) }}</span>
                    </div>
                    <div class="payloader-agent-compact-line">
                      <span class="payloader-agent-action-label">概况</span>
                      <span class="payloader-agent-compact-text">{{ round.summary }}</span>
                    </div>
                    <div class="payloader-agent-compact-line">
                      <span class="payloader-agent-action-label">状态</span>
                      <span class="payloader-agent-compact-text">{{ round.statusSummary }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 目标画像 (remote_target 模式) -->
              <div v-if="agentResult.final?.target_profile" class="payloader-agent-section payloader-agent-target-profile">
                <h4 class="payloader-agent-section-title">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="2" y1="12" x2="22" y2="12"></line>
                    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
                  </svg>
                  目标画像
                </h4>
                <div class="payloader-target-profile-grid">
                  <div class="payloader-target-profile-item">
                    <span class="payloader-target-profile-label">目标 URL</span>
                    <span class="payloader-target-profile-value">{{ agentResult.final.target_profile.target_url }}</span>
                  </div>
                  <div class="payloader-target-profile-item">
                    <span class="payloader-target-profile-label">目标类型</span>
                    <span class="payloader-target-profile-value">{{ agentResult.final.target_profile.target_type }}</span>
                  </div>
                  <div v-if="agentResult.final.target_profile.classification" class="payloader-target-profile-item">
                    <span class="payloader-target-profile-label">分类置信度</span>
                    <span class="payloader-target-profile-value">{{ (agentResult.final.target_profile.classification.confidence * 100).toFixed(0) }}%</span>
                  </div>
                </div>
              </div>

              <!-- 阶段验证链 (remote_target 模式优先渲染) -->
              <div v-if="agentResult.final?.phase_results && agentResult.final.phase_results.length > 0" class="payloader-agent-section payloader-agent-phases">
                <h4 class="payloader-agent-section-title">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                    <path d="M2 17l10 5 10-5"></path>
                    <path d="M2 12l10 5 10-5"></path>
                  </svg>
                  阶段验证链
                </h4>
                <div class="payloader-phase-chain">
                  <div v-for="(phase, idx) in agentResult.final.phase_results" :key="phase.name" class="payloader-phase-node-wrapper">
                    <div :class="['payloader-phase-node', `payloader-phase-node--${phase.status}`]">
                      <div class="payloader-phase-node-header">
                        <span class="payloader-phase-step">PHASE {{ idx + 1 }}</span>
                        <span :class="['payloader-phase-status', `payloader-phase-status--${phase.status}`]">
                          {{ phase.status === 'completed' ? '✅ 完成' : phase.status === 'failed' ? '❌ 失败' : phase.status === 'partial' ? '⏳ 部分' : '⏭️ 跳过' }}
                        </span>
                      </div>
                      <h5 class="payloader-phase-node-title">{{ phase.label }}</h5>
                      <p class="payloader-phase-node-summary">{{ phase.summary }}</p>
                      <div class="payloader-phase-node-meta">
                        <span class="payloader-phase-evidence">证据: {{ phase.evidence_count }} 项</span>
                        <span v-if="phase.risk_conclusion" class="payloader-phase-risk">{{ phase.risk_conclusion }}</span>
                      </div>
                    </div>
                    <div v-if="idx < agentResult.final!.phase_results!.length - 1" class="payloader-phase-connector">
                      <div class="payloader-phase-arrow"></div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 验证链详情 -->
              <div v-if="agentResult.final?.validation_chain && agentResult.final.validation_chain.length > 0" class="payloader-agent-section payloader-agent-validation">
                <h4 class="payloader-agent-section-title">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                  </svg>
                  验证链结果
                </h4>
                <div class="payloader-validation-list">
                  <div v-for="(vc, idx) in agentResult.final.validation_chain" :key="idx" :class="['payloader-validation-item', vc.validated ? 'validated' : 'unvalidated']">
                    <span class="payloader-validation-icon">{{ vc.validated ? '✅' : '❌' }}</span>
                    <div class="payloader-validation-content">
                      <span class="payloader-validation-finding">{{ vc.finding }}</span>
                      <span class="payloader-validation-conclusion">{{ vc.conclusion }}</span>
                    </div>
                    <span :class="['payloader-validation-severity', vc.severity]">{{ vc.severity }}</span>
                  </div>
                </div>
              </div>

              <!-- 风险假设 -->
              <div v-if="agentResult.final?.risk_hypotheses && agentResult.final.risk_hypotheses.length > 0" class="payloader-agent-section payloader-agent-risk-hypotheses">
                <h4 class="payloader-agent-section-title">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                    <line x1="12" y1="9" x2="12" y2="13"></line>
                    <line x1="12" y1="17" x2="12.01" y2="17"></line>
                  </svg>
                  风险假设
                </h4>
                <div class="payloader-hypothesis-list">
                  <div v-for="(rh, idx) in agentResult.final.risk_hypotheses" :key="idx" class="payloader-hypothesis-item">
                    <span :class="['payloader-hypothesis-severity', rh.severity]">{{ rh.severity }}</span>
                    <span class="payloader-hypothesis-text">{{ rh.hypothesis }}</span>
                    <span class="payloader-hypothesis-confidence">置信度: {{ (rh.confidence * 100).toFixed(0) }}%</span>
                  </div>
                </div>
              </div>

              <!-- 渗透结果分析 (fallback: 如果没有 phase_results 则用旧逻辑) -->
              <div v-if="!agentResult.final?.phase_results?.length && agentResult.final && (agentResult.final.attack_type || agentResult.final.scan_results || agentResult.final.risks)" class="payloader-agent-section payloader-agent-analysis">
                <h4 class="payloader-agent-section-title">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                    <path d="M2 17l10 5 10-5"></path>
                    <path d="M2 12l10 5 10-5"></path>
                  </svg>
                  渗透测试结果分析
                </h4>
                
                <div v-if="agentResult.final.attack_type" class="payloader-agent-attack-type">
                  <div class="payloader-agent-analysis-label">攻击类型</div>
                  <div class="payloader-agent-analysis-value">
                    <span class="payloader-agent-attack-type-badge">{{ agentResult.final.attack_type }}</span>
                    <p v-if="agentResult.final.attack_description" class="payloader-agent-attack-desc">{{ agentResult.final.attack_description }}</p>
                  </div>
                </div>
                
                <div v-if="agentResult.final.scan_results" class="payloader-agent-scan-results">
                  <div class="payloader-agent-analysis-label">扫描发现</div>
                  <pre class="payloader-detail-code">{{ agentResult.final.scan_results }}</pre>
                </div>
                
                <div v-if="agentResult.final.risks && agentResult.final.risks.length > 0" class="payloader-agent-risks">
                  <div class="payloader-agent-analysis-label">发现风险</div>
                  <ul class="payloader-agent-risk-list">
                    <li v-for="(risk, idx) in agentResult.final.risks" :key="idx" class="payloader-agent-risk-item">
                      <span class="payloader-agent-risk-icon">⚠</span>
                      <span>{{ risk }}</span>
                    </li>
                  </ul>
                </div>
              </div>

              <!-- 安全防护建议 -->
              <div v-if="agentResult.final && (agentResult.final.recommendations || agentResult.final.commands)" class="payloader-agent-section payloader-agent-suggestions">
                <h4 class="payloader-agent-section-title">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
                  </svg>
                  安全防护建议
                </h4>
                
                <div v-if="agentResult.final.recommendations && agentResult.final.recommendations.length > 0" class="payloader-agent-recommendations">
                  <ul class="payloader-agent-suggestion-list">
                    <li v-for="(rec, idx) in agentResult.final.recommendations" :key="idx" class="payloader-agent-suggestion-item">
                      <span class="payloader-agent-suggestion-icon">✓</span>
                      <span>{{ rec }}</span>
                    </li>
                  </ul>
                </div>
                
                <div v-if="agentResult.final.commands && agentResult.final.commands.length > 0" class="payloader-agent-commands">
                  <div class="payloader-agent-analysis-label">相关命令</div>
                  <div v-for="(cmd, idx) in agentResult.final.commands" :key="idx" class="payloader-agent-command">
                    <pre class="payloader-detail-code">{{ cmd }}</pre>
                    <button class="payloader-btn payloader-btn--secondary payloader-btn--sm" @click.stop="handleCopy(cmd)">复制</button>
                  </div>
                </div>
              </div>

              <!-- 检测报告 -->
              <div v-if="agentReportView" class="payloader-agent-section payloader-agent-report-section payloader-agent-report-section--dashboard">
                <h4 class="payloader-agent-section-title">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                    <line x1="16" y1="13" x2="8" y2="13"></line>
                    <line x1="16" y1="17" x2="8" y2="17"></line>
                    <polyline points="10 9 9 9 8 9"></polyline>
                  </svg>
                  完整渗透测试报告
                </h4>
                <PentestReportDashboard
                  :view="agentReportView"
                  :html="agentReportHtml"
                  :context="agentReportContext"
                  :show-refresh="false"
                />
              </div>

              <!-- 使用的 Skills -->
              <div v-if="agentResult.skill_results && agentResult.skill_results.length > 0" class="payloader-agent-section payloader-agent-skills-section">
                <h4 class="payloader-agent-section-title">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
                  </svg>
                  使用的 Skills
                </h4>
                <div class="payloader-agent-skills-grid">
                  <div v-for="(skill, idx) in agentResult.skill_results" :key="idx" class="payloader-agent-skill-card">
                    <div class="payloader-agent-skill-header">
                      <span class="payloader-agent-skill-name">{{ skill.skill_name }}</span>
                      <span :class="['payloader-agent-skill-risk', skill.risk_level]">{{ skill.risk_level }}</span>
                    </div>
                    <p class="payloader-agent-skill-summary">{{ skill.summary }}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div v-if="selectedTask && !selectedTask.running" class="payloader-modal-footer">
            <button class="payloader-btn payloader-btn--secondary" @click="requestCloseResultModal">关闭</button>
            <button class="payloader-btn payloader-btn--primary" @click="pentestTarget = selectedTask?.target || ''; closeResultModal(); openPentestModal()">重新检测</button>
          </div>
        </div>
      </div>

      <div v-if="showCloseConfirmModal" class="payloader-modal-overlay" @click.self="cancelCloseConfirmation">
        <div class="payloader-modal payloader-modal--confirm">
          <div class="payloader-modal-header">
            <h3>确认关闭</h3>
            <button class="payloader-modal-close" title="关闭" @click="cancelCloseConfirmation">&times;</button>
          </div>
          <div class="payloader-modal-body">
            <p class="payloader-modal-desc">
              当前任务仍在运行。你可以关闭当前弹窗并让任务在后台继续，或者立即中断本次任务。
            </p>
          </div>
          <div class="payloader-modal-footer">
            <button class="payloader-btn payloader-btn--secondary" @click="continueTaskInBackground">后台继续运行</button>
            <button class="payloader-btn payloader-btn--danger" :disabled="!!stoppingTaskId" @click="interruptTaskAndClose">
              {{ stoppingTaskId ? '中断中...' : '中断任务' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 日志弹窗 -->
      <div v-if="showLogModal" class="payloader-modal-overlay payloader-log-overlay" @click.self="closeLogModal">
          <div class="payloader-modal payloader-modal--log">
          <div class="payloader-modal-header">
            <div class="payloader-log-header-main">
              <h3>任务日志</h3>
            </div>
            <div class="payloader-modal-header-actions">
              <button
                v-if="logData.length > 0"
                class="payloader-modal-header-btn payloader-log-report-action"
                type="button"
                @click="scrollLogDetailsIntoView"
              >
                查看轮次详情
              </button>
              <button class="payloader-modal-close" @click="closeLogModal">&times;</button>
            </div>
          </div>
          <div class="payloader-modal-body payloader-modal-body--scroll payloader-log-body">
            <div v-if="logLoading && logData.length === 0" class="payloader-log-empty">正在加载日志...</div>
            <div v-else-if="logError" class="payloader-log-empty payloader-log-empty--error">{{ logError }}</div>
            <template v-else>
              <section class="payloader-log-report-section payloader-log-report-section--dashboard">
                <PentestReportDashboard
                  :view="logReportView"
                  :html="renderedLogReportHtml"
                  :context="logReportContext"
                  :refreshing="logLoading"
                  @refresh="loadLogs(currentLogTaskId)"
                />
              </section>
              <div v-if="logData.length === 0" class="payloader-log-empty">
              {{ agentRunning ? 'AI 已决策，正在等待第一条执行日志落盘...' : '暂无日志数据' }}
              </div>
              <div v-else ref="logDetailsSectionRef" class="payloader-log-details-section">
                <div class="payloader-log-details-title">轮次执行详情</div>
                <div :class="['payloader-log-layout', { 'payloader-log-layout--with-terminal': !!selectedLogAction }]">
                <div class="payloader-log-rounds">
                  <div v-if="!selectedLogAction" class="payloader-log-terminal-inline-hint">
                    右侧实时终端过程默认收起。点击某条任务的“查看实时终端过程”后再展开显示。
                  </div>
                  <div
                    v-for="(round, roundIdx) in logRounds"
                    :key="round.key"
                    ref="logDetailRefs"
                    class="payloader-log-round-group"
                  >
                    <div class="payloader-log-round-header">
                      <span class="payloader-log-round">第 {{ round.round ?? roundIdx + 1 }} 轮任务</span>
                      <span class="payloader-log-round-count">{{ round.actions.length }} 个任务</span>
                      <span class="payloader-log-time">{{ formatActionTime(round.time) }}</span>
                    </div>
                    <div class="payloader-log-think">
                      <div class="payloader-log-think-label">🤖 AI 决策</div>
                      <pre class="payloader-log-think-content">{{ formatActionPayload(round.llm_decision, '[暂无决策记录]') }}</pre>
                    </div>
                    <div class="payloader-log-entry">
                      <div class="payloader-log-meta">
                        <span class="payloader-log-tool">{{ summarizeRoundTaskType(round.actions) }}</span>
                        <span :class="['payloader-log-status', `payloader-log-status--${round.statusClass}`]">
                          {{ round.statusText }}
                        </span>
                        <span class="payloader-log-time">{{ formatActionTime(round.time) }}</span>
                      </div>
                      <div class="payloader-log-args">
                        <div class="payloader-log-args-label">📋 轮次概况</div>
                        <pre class="payloader-log-code">{{ round.summary }}</pre>
                      </div>
                      <div v-if="round.surfaceSummary" class="payloader-log-args">
                        <div class="payloader-log-args-label">🧭 涉及范围</div>
                        <pre class="payloader-log-code">{{ round.surfaceSummary }}</pre>
                      </div>
                      <div class="payloader-log-stdout">
                        <div class="payloader-log-stdout-label">📌 执行状态</div>
                        <pre class="payloader-log-code">{{ round.statusSummary }}</pre>
                      </div>
                      <div class="payloader-log-action-list">
                        <div class="payloader-log-section-label">任务明细</div>
                        <div v-if="getRoundExecutionActions(round.actions).length === 0" class="payloader-log-action-empty">
                          本轮暂无实际工具执行，当前主要是 AI 规划或等待日志落盘。
                        </div>
                        <div
                          v-for="(action, actionIdx) in getRoundExecutionActions(round.actions)"
                          :key="action.id || `${round.key}-action-${actionIdx}`"
                          class="payloader-log-action-card"
                        >
                          <div class="payloader-log-action-header">
                            <div class="payloader-log-action-title-wrap">
                              <div class="payloader-log-action-title">
                                {{ action.task_label || action.purpose || action.tool }}
                              </div>
                              <div class="payloader-log-action-subtitle">
                                {{ describeAction(action) }}
                              </div>
                            </div>
                            <div class="payloader-log-action-badges">
                              <span :class="['payloader-log-status', `payloader-log-status--${getActionStatusClass(action)}`]">
                                {{ getLogStatusLabel(action.status) }}
                              </span>
                              <span v-if="action.returncode !== null" :class="['payloader-log-rc', action.returncode === 0 ? 'ok' : 'err']">
                                rc={{ action.returncode }}
                              </span>
                            </div>
                          </div>
                          <div class="payloader-log-action-grid">
                            <div class="payloader-log-action-field">
                              <span class="payloader-log-action-field-label">工具</span>
                              <span class="payloader-log-action-field-value">{{ action.tool }}</span>
                            </div>
                            <div v-if="action.surface" class="payloader-log-action-field">
                              <span class="payloader-log-action-field-label">攻击面</span>
                              <span class="payloader-log-action-field-value">{{ action.surface }}</span>
                            </div>
                            <div v-if="action.purpose" class="payloader-log-action-field payloader-log-action-field--wide">
                              <span class="payloader-log-action-field-label">目的</span>
                              <span class="payloader-log-action-field-value">{{ action.purpose }}</span>
                            </div>
                            <div class="payloader-log-action-field">
                              <span class="payloader-log-action-field-label">执行模式</span>
                              <span class="payloader-log-action-field-value">{{ formatExecutionMode(action.execution_mode) }}</span>
                            </div>
                            <div v-if="action.timeout_seconds" class="payloader-log-action-field">
                              <span class="payloader-log-action-field-label">超时预算</span>
                              <span class="payloader-log-action-field-value">{{ Math.round(action.timeout_seconds) }}s</span>
                            </div>
                            <div v-if="action.pid" class="payloader-log-action-field">
                              <span class="payloader-log-action-field-label">进程 PID</span>
                              <span class="payloader-log-action-field-value">{{ action.pid }}</span>
                            </div>
                            <div class="payloader-log-action-field payloader-log-action-field--wide">
                              <span class="payloader-log-action-field-label">执行结论</span>
                              <span class="payloader-log-action-field-value">{{ summarizeActionOutcome(action) }}</span>
                            </div>
                          </div>
                          <div class="payloader-log-action-toolbar">
                            <button
                              type="button"
                              class="payloader-log-action-terminal-btn"
                              @click="selectTerminalAction(action)"
                            >
                              {{ selectedLogActionId === action.id ? '收起实时终端过程' : '查看实时终端过程' }}
                            </button>
                          </div>
                          <details v-if="action.args" class="payloader-log-detail-block">
                            <summary>执行参数</summary>
                            <pre class="payloader-log-code">{{ formatActionPayload(action.args, '') }}</pre>
                          </details>
                          <details v-if="action.error" class="payloader-log-detail-block payloader-log-detail-block--error" open>
                            <summary>错误信息</summary>
                            <pre class="payloader-log-code">{{ formatActionPayload(action.error, '') }}</pre>
                          </details>
                          <details v-if="getPrimaryActionOutput(action)" class="payloader-log-detail-block">
                            <summary>结果摘要</summary>
                            <pre class="payloader-log-code">{{ getPrimaryActionOutput(action) }}</pre>
                          </details>
                          <details v-if="shouldShowRawOutput(action)" class="payloader-log-detail-block">
                            <summary>原始输出</summary>
                            <pre class="payloader-log-code">{{ getRawActionOutput(action) }}</pre>
                          </details>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                <aside v-if="selectedLogAction" class="payloader-log-terminal-panel">
                  <div class="payloader-log-terminal-header">
                    <div>
                      <div class="payloader-log-terminal-eyebrow">实时终端过程</div>
                      <h4>{{ selectedLogAction?.task_label || selectedLogAction?.purpose || selectedLogAction?.tool || '暂无选中任务' }}</h4>
                    </div>
                    <span v-if="selectedLogAction" :class="['payloader-log-status', `payloader-log-status--${getActionStatusClass(selectedLogAction)}`]">
                      {{ getLogStatusLabel(selectedLogAction.status) }}
                    </span>
                  </div>
                  <div v-if="selectedLogAction" class="payloader-log-terminal-meta">
                    <span>{{ formatExecutionMode(selectedLogAction.execution_mode) }}</span>
                    <span v-if="selectedLogAction.pid">PID {{ selectedLogAction.pid }}</span>
                    <span v-if="selectedLogAction.timeout_seconds">{{ Math.round(selectedLogAction.timeout_seconds) }}s</span>
                    <span>{{ formatActionTime(selectedLogAction.updated_at || selectedLogAction.time) }}</span>
                  </div>
                  <div v-if="selectedLogAction" class="payloader-log-terminal-body">
                    <pre class="payloader-log-terminal-output">{{ getTerminalPanelOutput(selectedLogAction) || '[当前尚无终端输出]' }}</pre>
                  </div>
                </aside>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>

      <!-- 历史弹窗 -->
      <div v-if="showHistoryModal" class="payloader-modal-overlay" @click.self="showHistoryModal = false">
        <div class="payloader-modal payloader-modal--history">
          <div class="payloader-modal-header">
            <h3>渗透历史 ({{ historyData.length }} 条)</h3>
            <button class="payloader-modal-close" @click="showHistoryModal = false">&times;</button>
          </div>
          <div class="payloader-modal-body payloader-modal-body--scroll">
            <div v-if="historyData.length === 0" class="payloader-log-empty">暂无历史记录</div>
            <div v-for="item in historyData" :key="item.task_id" class="payloader-history-item">
              <div class="payloader-history-main">
                <div class="payloader-history-target">{{ item.target }}</div>
                <div class="payloader-history-meta">
                  <span class="payloader-history-time">{{ item.start_time }}</span>
                  <span :class="['payloader-history-status', item.status]">{{ item.status }}</span>
                  <span class="payloader-history-phase">{{ getPhaseLabel(item.phase) }}</span>
                </div>
              </div>
              <div class="payloader-history-stats">
                <span class="payloader-history-stat">🔍 {{ item.findings_count }}</span>
                <span class="payloader-history-stat">⚠️ {{ item.vuln_count }}</span>
                <span class="payloader-history-stat">🛠 {{ item.actions_count }}</span>
              </div>
              <div class="payloader-history-actions">
                <button class="payloader-btn payloader-btn--secondary payloader-btn--sm" @click="viewHistoryLogs(item.task_id)">日志</button>
                <button class="payloader-btn payloader-btn--secondary payloader-btn--sm" @click="deleteHistory(item.task_id)">删除</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="isLoading" class="payloader-loading">
        <div class="payloader-loading-spinner"></div>
        <p class="payloader-loading-text">正在加载 Payload...</p>
      </div>

      <div v-else-if="error" class="payloader-error">
        <div class="payloader-error-icon">⚠️</div>
        <h3 class="payloader-error-title">加载失败</h3>
        <p class="payloader-error-description">{{ error }}</p>
        <button class="payloader-btn payloader-btn--primary" @click="refresh">
          重试
        </button>
      </div>

      <template v-else-if="state.viewMode === 'list'">
        <!-- 编解码工具 -->
        <EncodingTools v-if="state.currentView === 'encoding'" />

        <!-- 其他视图的列表 -->
        <template v-else>
          <div v-if="filteredItems.length === 0" class="payloader-empty">
          <div class="payloader-empty-icon">📦</div>
          <h3 class="payloader-empty-title">暂无内容</h3>
          <p class="payloader-empty-description">
            {{ state.searchQuery ? '没有找到匹配的内容' : '该分类下暂无内容' }}
          </p>
        </div>

        <div v-else class="payloader-cards-grid">
          <template v-if="state.currentView === 'tools'">
            <div 
              v-for="tool in filteredTools" 
              :key="tool.id"
              class="payloader-card"
              @click="openDetail(tool.id)"
            >
              <div class="payloader-card-header">
                <span class="payloader-card-category">{{ getText(tool.category) }}</span>
              </div>
              <h3 class="payloader-card-title">{{ getText(tool.name) }}</h3>
              <p class="payloader-card-desc">{{ getText(tool.description) }}</p>
              <div class="payloader-card-footer">
                <span class="payloader-card-count">{{ tool.commands.length }} 条命令</span>
              </div>
            </div>
          </template>

          <template v-else>
            <div 
              v-for="payload in filteredPayloadsList" 
              :key="payload.id"
              class="payloader-card"
              @click="openDetail(payload.id)"
            >
              <div class="payloader-card-header">
                <span class="payloader-card-category">{{ getText(payload.category) }}</span>
                <span v-if="payload.subCategory" class="payloader-card-subcategory">{{ getText(payload.subCategory) }}</span>
              </div>
              <h3 class="payloader-card-title">{{ getText(payload.name) }}</h3>
              <p class="payloader-card-desc">{{ getText(payload.description) }}</p>
              <div class="payloader-card-tags">
                <span v-for="tag in payload.tags.slice(0, 3)" :key="tag" class="payloader-card-tag">{{ tag }}</span>
                <span v-if="payload.tags.length > 3" class="payloader-card-tag">+{{ payload.tags.length - 3 }}</span>
              </div>
            </div>
          </template>
        </div>
        </template>
      </template>

      <template v-else-if="state.viewMode === 'detail'">
        <div class="payloader-detail">
          <template v-if="state.currentView === 'tools' && selectedTool">
            <div class="payloader-detail-header">
              <div class="payloader-detail-meta">
                <span class="payloader-detail-category">{{ getText(selectedTool.category) }}</span>
              </div>
              <h1 class="payloader-detail-title">{{ getText(selectedTool.name) }}</h1>
              <p class="payloader-detail-desc">{{ getText(selectedTool.description) }}</p>
            </div>
            
            <div v-if="selectedTool.installation" class="payloader-detail-section">
              <h3 class="payloader-detail-section-title">安装方式</h3>
              <pre class="payloader-detail-code">{{ selectedTool.installation }}</pre>
            </div>

            <div class="payloader-detail-section">
              <h3 class="payloader-detail-section-title">命令列表</h3>
              <div class="payloader-detail-commands">
                <div v-for="(cmd, idx) in selectedTool.commands" :key="idx" class="payloader-detail-command">
                  <div class="payloader-detail-command-header">
                    <h4 class="payloader-detail-command-title">{{ getText(cmd.name) }}</h4>
                    <button class="payloader-btn payloader-btn--secondary payloader-btn--sm" @click.stop="handleCopy(cmd.command)">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                      </svg>
                      复制
                    </button>
                  </div>
                  <pre class="payloader-detail-code">{{ cmd.command }}</pre>
                  <p v-if="cmd.description" class="payloader-detail-command-desc">{{ getText(cmd.description) }}</p>
                </div>
              </div>
            </div>
          </template>

          <template v-else-if="selectedPayload">
            <div class="payloader-detail-header">
              <div class="payloader-detail-meta">
                <span class="payloader-detail-category">{{ getText(selectedPayload.category) }}</span>
                <span v-if="selectedPayload.subCategory" class="payloader-detail-subcategory">{{ getText(selectedPayload.subCategory) }}</span>
              </div>
              <h1 class="payloader-detail-title">{{ getText(selectedPayload.name) }}</h1>
              <p class="payloader-detail-desc">{{ getText(selectedPayload.description) }}</p>
              <div class="payloader-detail-tags">
                <span v-for="tag in selectedPayload.tags" :key="tag" class="payloader-detail-tag">{{ tag }}</span>
              </div>
            </div>

            <div v-if="selectedPayload.prerequisites && selectedPayload.prerequisites.length > 0" class="payloader-detail-section">
              <h3 class="payloader-detail-section-title">前提条件</h3>
              <ul class="payloader-detail-list">
                <li v-for="(prereq, idx) in selectedPayload.prerequisites" :key="idx">{{ getText(prereq) }}</li>
              </ul>
            </div>

            <!-- 标签切换 -->
            <div class="payloader-section-tabs">
              <button
                :class="['payloader-section-tab', { active: activeSection === 'execution' }]"
                @click="activeSection = 'execution'"
              >
                执行步骤
              </button>
              <button
                :class="['payloader-section-tab', { active: activeSection === 'chain' }]"
                @click="activeSection = 'chain'"
              >
                攻击链
              </button>
              <button
                :class="['payloader-section-tab', { active: activeSection === 'analysis' }]"
                @click="activeSection = 'analysis'"
              >
                分析
              </button>
              <button
                v-if="selectedPayload.tutorial"
                :class="['payloader-section-tab', { active: activeSection === 'tutorial' }]"
                @click="activeSection = 'tutorial'"
              >
                教程
              </button>
            </div>

            <!-- 执行步骤 -->
            <div v-if="activeSection === 'execution'" class="payloader-detail-section">
              <div class="payloader-detail-executions">
                <div v-for="(exec, idx) in selectedPayload.execution" :key="idx" class="payloader-detail-execution">
                  <div class="payloader-detail-execution-header">
                    <h4 class="payloader-detail-execution-title">{{ getText(exec.title) }}</h4>
                    <button class="payloader-btn payloader-btn--secondary payloader-btn--sm" @click.stop="handleCopy(exec.command)">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                      </svg>
                      复制
                    </button>
                  </div>
                  <pre class="payloader-detail-code">{{ exec.command }}</pre>
                  <div v-if="exec.description" class="payloader-detail-execution-desc">{{ getText(exec.description) }}</div>
                </div>
              </div>
            </div>

            <!-- 攻击链可视化 -->
            <div v-if="activeSection === 'chain'" class="payloader-detail-section">
              <div class="payloader-chain-header">
                <h3>攻击链可视化</h3>
                <p>展示完整的攻击流程和步骤之间的关联关系</p>
              </div>
              <div class="payloader-chain-visualization">
                <div v-for="(exec, idx) in selectedPayload.execution" :key="idx" class="payloader-chain-node-wrapper">
                  <div :class="['payloader-chain-node', { first: idx === 0, last: idx === selectedPayload.execution.length - 1 }]">
                    <div class="payloader-chain-node-header">
                      <span class="payloader-chain-step">STEP {{ idx + 1 }}</span>
                      <span v-if="exec.platform" :class="['payloader-chain-platform', exec.platform]">
                        {{ exec.platform === 'all' ? '🌐' : exec.platform === 'windows' ? '🪟' : '🐧' }}
                      </span>
                    </div>
                    <h4 class="payloader-chain-node-title">{{ getText(exec.title) }}</h4>
                    <p v-if="exec.description" class="payloader-chain-node-desc">{{ getText(exec.description) }}</p>
                    <div class="payloader-chain-command-preview">
                      <code>{{ exec.command.substring(0, 80) }}{{ exec.command.length > 80 ? '...' : '' }}</code>
                    </div>
                    <div class="payloader-chain-node-actions">
                      <button class="payloader-chain-copy-btn" @click.stop="handleCopy(exec.command)">📋</button>
                    </div>
                  </div>
                  <div v-if="idx < selectedPayload.execution.length - 1" class="payloader-chain-connector">
                    <div class="payloader-chain-arrow"></div>
                    <div class="payloader-chain-arrowhead"></div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 分析部分 -->
            <div v-if="activeSection === 'analysis'" class="payloader-detail-section">
              <div class="payloader-analysis-card">
                <h3>分析说明</h3>
                <p>{{ selectedPayload.analysis ? getText(selectedPayload.analysis) : '暂无分析内容' }}</p>
              </div>

              <div v-if="selectedPayload.opsecTips && selectedPayload.opsecTips.length > 0" class="payloader-analysis-card warning">
                <h3>OPSEC 提示</h3>
                <ul>
                  <li v-for="(tip, idx) in selectedPayload.opsecTips" :key="idx">{{ getText(tip) }}</li>
                </ul>
              </div>

              <div v-if="selectedPayload.references && selectedPayload.references.length > 0" class="payloader-analysis-card">
                <h3>参考链接</h3>
                <ul class="payloader-references-list">
                  <li v-for="(ref, idx) in selectedPayload.references" :key="idx">
                    <a :href="ref" target="_blank" rel="noopener noreferrer">{{ ref }}</a>
                  </li>
                </ul>
              </div>
            </div>

            <!-- 教程部分 -->
            <div v-if="activeSection === 'tutorial' && selectedPayload.tutorial" class="payloader-detail-section">
              <div class="payloader-detail-tutorial">
                <div class="payloader-detail-tutorial-item">
                  <h4>概述</h4>
                  <p>{{ getText(selectedPayload.tutorial.overview) }}</p>
                </div>
                <div class="payloader-detail-tutorial-item">
                  <h4>漏洞原理</h4>
                  <p>{{ getText(selectedPayload.tutorial.vulnerability) }}</p>
                </div>
                <div class="payloader-detail-tutorial-item">
                  <h4>利用方式</h4>
                  <p>{{ getText(selectedPayload.tutorial.exploitation) }}</p>
                </div>
                <div class="payloader-detail-tutorial-item">
                  <h4>修复方案</h4>
                  <p>{{ getText(selectedPayload.tutorial.mitigation) }}</p>
                </div>
              </div>
            </div>

            <!-- WAF 绕过 -->
            <div v-if="selectedPayload.wafBypass && selectedPayload.wafBypass.length > 0" class="payloader-detail-section">
              <h3 class="payloader-detail-section-title">WAF 绕过</h3>
              <div class="payloader-detail-executions">
                <div v-for="(bypass, idx) in selectedPayload.wafBypass" :key="idx" class="payloader-detail-execution">
                  <div class="payloader-detail-execution-header">
                    <h4 class="payloader-detail-execution-title">{{ getText(bypass.title) }}</h4>
                    <button class="payloader-btn payloader-btn--secondary payloader-btn--sm" @click.stop="handleCopy(bypass.command)">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                      </svg>
                      复制
                    </button>
                  </div>
                  <pre class="payloader-detail-code">{{ bypass.command }}</pre>
                </div>
              </div>
            </div>
          </template>
        </div>
      </template>
    </PayloaderContent>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, watch, onMounted, onUnmounted } from 'vue';
  import { marked } from 'marked';
  import PayloaderToolbar from './components/PayloaderToolbar.vue';
import PayloaderContent from './components/PayloaderContent.vue';
import EncodingTools from './components/EncodingTools.vue';
import PentestReportDashboard from './components/PentestReportDashboard.vue';
import {
  resolveReportView,
  type PentestReportView,
} from './pentestReportView';
import { usePayloader } from './composables/usePayloaderState';
import type { PayloadItem, ToolCommand, I18nText } from './types';
import { aiService } from '../ai/aiService';

const { 
  state, 
  filteredPayloads, 
  categories, 
  isLoading, 
  error,
  refresh, 
  selectCategory, 
  setSearchQuery,
  setCurrentView,
  setSelectedItemId,
  copyPayload
} = usePayloader();

const showViewDropdown = ref(false);
const showCategoryDropdown = ref(false);
const activeSection = ref<'execution' | 'chain' | 'analysis' | 'tutorial'>('execution');

const views = [
  { id: 'web', label: 'Web 渗透' },
  { id: 'intranet', label: '内网渗透' }
];

const filteredItems = computed(() => {
  if (state.currentView === 'tools') {
    let result = state.toolCommands as readonly ToolCommand[];
    if (state.searchQuery) {
      const query = state.searchQuery.toLowerCase();
      result = result.filter(t => {
        const name = getText(t.name).toLowerCase();
        const desc = getText(t.description).toLowerCase();
        const cmds = t.commands.map(c => c.command).join('\n').toLowerCase();
        return name.includes(query) || desc.includes(query) || cmds.includes(query);
      });
    }
    return result;
  } else {
    return filteredPayloads.value as readonly PayloadItem[];
  }
});

const filteredTools = computed<ToolCommand[]>(() => {
  if (state.currentView !== 'tools') return [];
  let result = state.toolCommands;
  if (state.searchQuery) {
    const query = state.searchQuery.toLowerCase();
    result = result.filter(t => {
      const name = getText(t.name).toLowerCase();
      const desc = getText(t.description).toLowerCase();
      const cmds = t.commands.map(c => c.command).join('\n').toLowerCase();
      return name.includes(query) || desc.includes(query) || cmds.includes(query);
    });
  }
  return result as ToolCommand[];
});

const filteredPayloadsList = computed<PayloadItem[]>(() => {
  if (state.currentView === 'tools') return [];
  return filteredPayloads.value as PayloadItem[];
});

const selectedPayload = computed<PayloadItem | null>(() => {
  if (!state.selectedItemId || state.currentView === 'tools') return null;
  const all = [...state.webPayloads, ...state.intranetPayloads];
  const found = all.find(p => p.id === state.selectedItemId);
  if (!found) return null;
  
  // Helper to deep-spread PayloadExecution arrays
  const mapExecutions = (arr: readonly { title: any; command: string; syntaxBreakdown?: readonly any[]; description?: any; platform?: any; requiresAdmin?: boolean }[] | undefined) => {
    if (!arr) return undefined;
    return arr.map(e => ({
      title: e.title,
      command: e.command,
      syntaxBreakdown: e.syntaxBreakdown ? [...e.syntaxBreakdown] : undefined,
      description: e.description,
      platform: e.platform,
      requiresAdmin: e.requiresAdmin,
    }));
  };

  return {
    id: found.id,
    name: found.name,
    description: found.description,
    category: found.category,
    subCategory: found.subCategory,
    tags: Array.isArray(found.tags) ? [...found.tags] : [],
    prerequisites: found.prerequisites ? [...found.prerequisites] : undefined,
    execution: mapExecutions(found.execution)!,
    analysis: found.analysis,
    opsecTips: found.opsecTips ? [...found.opsecTips] : undefined,
    wafBypass: mapExecutions(found.wafBypass),
    edrBypass: mapExecutions(found.edrBypass),
    references: found.references ? [...found.references] : undefined,
    tutorial: found.tutorial,
  };
});

const selectedTool = computed<ToolCommand | null>(() => {
  if (!state.selectedItemId || state.currentView !== 'tools') return null;
  const found = state.toolCommands.find(t => t.id === state.selectedItemId);
  if (!found) return null;
  
  return {
    id: found.id,
    name: found.name,
    description: found.description,
    category: found.category,
    commands: found.commands.map(c => ({
      name: c.name,
      command: c.command,
      description: c.description,
      syntaxBreakdown: c.syntaxBreakdown ? [...c.syntaxBreakdown] : undefined,
      examples: c.examples ? [...c.examples] : undefined,
      platform: c.platform,
    })),
    installation: found.installation,
    references: found.references ? [...found.references] : undefined,
  };
});

function getViewLabel(view: string): string {
  const viewItem = views.find(v => v.id === view);
  return viewItem?.label || 'Web 渗透';
}

function getSelectedCategoryLabel(): string {
  if (state.selectedCategory === 'all') {
    return '全部';
  }
  const cat = categories.value.find(c => c.id === state.selectedCategory);
  return cat ? getText(cat.label) : '全部';
}

function getText(text: I18nText, lang: 'zh' | 'en' = 'zh'): string {
  if (typeof text === 'string') return text;
  return text[lang];
}

function toggleViewDropdown() {
  showViewDropdown.value = !showViewDropdown.value;
  showCategoryDropdown.value = false;
}

function toggleCategoryDropdown() {
  showCategoryDropdown.value = !showCategoryDropdown.value;
  showViewDropdown.value = false;
}

function selectView(viewId: string) {
  setCurrentView(viewId as any);
  showViewDropdown.value = false;
}

function selectCategoryWrapper(categoryId: string) {
  selectCategory(categoryId);
  showCategoryDropdown.value = false;
}

function goBack() {
  setSelectedItemId(null);
}

function openDetail(id: string) {
  setSelectedItemId(id);
}

const handleCopy = async (code: string) => {
  await copyPayload(code);
};

 // ==================== 安全检测 Agent ====================
const showPentestModal = ref(false);
const showResultModal = ref(false);
const showCloseConfirmModal = ref(false);

interface PentestTask {
  id: string;
  taskId: string;
  target: string;
  running: boolean;
  phase: string;
  findingsCount: number;
  vulnCount: number;
  actionsCount: number;
  actions: any[];
  targets: string[];
  timer: ReturnType<typeof setInterval> | null;
  result: any;
  error: string;
  executionMode: PentestExecutionMode;
  startedAt: number;
}
const pentestTasks = ref<PentestTask[]>([]);
const selectedTaskId = ref<string>('');
const stoppingTaskId = ref<string>('');

const agentRunning = computed(() => pentestTasks.value.some(t => t.running));
const activeRunningCount = computed(() => pentestTasks.value.filter(t => t.running).length);

const selectedTask = computed(() => pentestTasks.value.find(t => t.id === selectedTaskId.value) || null);
const agentResult = computed(() => selectedTask.value?.result || null);
const currentTaskId = computed(() => selectedTask.value?.taskId || '');

const pentestTarget = ref<string>('');
type PentestExecutionMode = 'serial' | 'parallel';
const PENTEST_EXECUTION_MODE_STORAGE_KEY = 'LERT-pentest-execution-mode';
const pentestExecutionMode = ref<PentestExecutionMode>(loadPentestExecutionMode());
const pentestModalError = ref('');
const normalizedPentestTarget = computed(() => String(pentestTarget.value || '').trim());

function generateTaskId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

let taskPollTimers = new Map<string, ReturnType<typeof setInterval>>();

function loadPentestExecutionMode(): PentestExecutionMode {
  try {
    const cached = localStorage.getItem(PENTEST_EXECUTION_MODE_STORAGE_KEY);
    return cached === 'parallel' ? 'parallel' : 'serial';
  } catch {
    return 'serial';
  }
}

function setPentestExecutionMode(mode: PentestExecutionMode) {
  pentestExecutionMode.value = mode;
  try {
    localStorage.setItem(PENTEST_EXECUTION_MODE_STORAGE_KEY, mode);
  } catch {
    // ignore persistence errors
  }
}

function getAIConfig() {
  try {
    const raw = localStorage.getItem('LERT-ai-config');
    if (!raw) return null;
    const cfg = JSON.parse(raw);
    return {
      apiKey: cfg.apiKey || '',
      model: cfg.model || 'gpt-4o-mini',
      baseUrl: cfg.baseUrl || 'https://api.openai.com/v1',
      provider: cfg.provider || 'openai',
      temperature: cfg.temperature ?? 0.3,
    };
  } catch {
    return null;
  }
}

function openPentestModal() {
  pentestModalError.value = '';
  showPentestModal.value = true;
}

function handlePentestEntry() {
  pentestModalError.value = '';
  if (pentestTasks.value.length > 0) {
    showResultModal.value = true;
    if (!selectedTaskId.value && pentestTasks.value.length > 0) {
      selectedTaskId.value = pentestTasks.value[pentestTasks.value.length - 1].id;
    }
    return;
  }
  openPentestModal();
}

function openSkillsManager() {
  (window as any).showSkillsModal?.();
}

function openKnowledgeBaseManager() {
  (window as any).showKnowledgeBaseModal?.();
}

function closePentestModal() {
  pentestModalError.value = '';
  showPentestModal.value = false;
}

function closeResultModal() {
  showCloseConfirmModal.value = false;
  showResultModal.value = false;
  selectedTaskId.value = '';
}

function requestCloseResultModal() {
  if (selectedTask.value?.running) {
    showCloseConfirmModal.value = true;
    return;
  }
  closeResultModal();
}

function cancelCloseConfirmation() {
  showCloseConfirmModal.value = false;
}

function continueTaskInBackground() {
  closeResultModal();
}

function stopTaskTimer(taskId: string) {
  const timer = taskPollTimers.get(taskId);
  if (timer) {
    clearInterval(timer);
    taskPollTimers.delete(taskId);
  }
}

function removeTask(taskId: string) {
  const task = pentestTasks.value.find(t => t.id === taskId);
  if (!task) return;
  stopTaskTimer(taskId);
  pentestTasks.value = pentestTasks.value.filter(t => t.id !== taskId);
  if (selectedTaskId.value === taskId) {
    selectedTaskId.value = pentestTasks.value.length > 0 ? pentestTasks.value[pentestTasks.value.length - 1].id : '';
  }
}

async function interruptTaskAndClose() {
  const task = selectedTask.value;
  if (!task || !task.running || stoppingTaskId.value) {
    closeResultModal();
    return;
  }

  stoppingTaskId.value = task.id;
  try {
    const pythonApi = (await import('../../config/python-api.config')).default;
    await pythonApi.pentestStop(task.taskId);
    stopTaskTimer(task.id);
    updateTaskInList(task.id, { running: false });

    showCloseConfirmModal.value = false;

    updateTaskResult(task.id, {
      status: 'failed',
      final: {
        report: '<h1>正在生成阶段性总结报告</h1><p>任务已中断，正在根据当前阶段已获取的信息整理总结，请稍候。</p>',
        phase: task.phase,
      },
      phase: task.phase,
    });

    (window as any).showNotification?.('任务已中断，正在生成总结报告', 'success');

    const summary = await buildInterruptedPentestSummary(task.taskId, task.target);
    updateTaskResult(task.id, {
      status: 'failed',
      final: {
        report: summary.report,
        view: summary.view,
        phase: summary.phase,
      },
      phase: summary.phase,
      targets: task.targets,
      findings_count: summary.findingsCount,
      vuln_count: summary.vulnCount,
      actions_count: summary.actionsCount,
      actions: summary.actions,
      token_usage: summary.tokenUsage || {},
    });
  } catch (err: any) {
    (window as any).showNotification?.(err?.message || '中断任务失败', 'error');
  } finally {
    stoppingTaskId.value = '';
  }
}

function getPhaseLabel(phase: string | undefined) {
  switch (phase) {
    case 'init':    return '初始化';
    case 'recon':   return '侦察与信息收集';
    case 'web':     return 'Web 漏洞发现';
    case 'exploit': return '漏洞利用';
    case 'post':    return '后渗透与证据收集';
    case 'lateral': return '横向移动与扩展';
    case 'done':    return '已完成';
    default:        return phase || '运行中';
  }
}

function updateTaskInList(taskId: string, updates: Partial<PentestTask>) {
  const tasks = pentestTasks.value;
  for (let i = 0; i < tasks.length; i++) {
    if (tasks[i].id === taskId) {
      tasks[i] = { ...tasks[i], ...updates };
      break;
    }
  }
}

function updateTaskResult(taskId: string, result: any) {
  updateTaskInList(taskId, { result });
}

function countTaskRounds(actions: Array<Record<string, any>> | undefined | null) {
  const list = Array.isArray(actions) ? actions : [];
  if (list.length === 0) return 0;

  const rounds = new Set<number>();
  list.forEach((item) => {
    if (typeof item?.round === 'number' && Number.isFinite(item.round)) {
      rounds.add(item.round);
    }
  });
  if (rounds.size > 0) {
    return rounds.size;
  }

  const llmRounds = list.filter((item) => String(item?.tool || '').trim() === '_llm_wait').length;
  if (llmRounds > 0) {
    return llmRounds;
  }

  const actionable = list.filter((item) => String(item?.tool || '').trim() !== '_llm_wait');
  return actionable.length > 0 ? 1 : 0;
}

function summarizeRoundTaskType(actions: PentestLogEntry[]) {
  const surfaces = Array.from(new Set(
    actions
      .map((item) => String(item.surface || '').trim())
      .filter(Boolean)
  )).slice(0, 3);

  if (surfaces.length > 0) {
    return `任务范围：${surfaces.join(' / ')}`;
  }
  return '任务轮次概要';
}

function buildRoundSummary(actions: PentestLogEntry[]) {
  const total = actions.length;
  const running = actions.filter((item) => item.status === 'running').length;
  const failed = actions.filter((item) =>
    item.status === 'failed' || !!item.error || (typeof item.returncode === 'number' && item.returncode !== 0)
  ).length;
  const completed = Math.max(0, total - running - failed);
  const capabilityCount = Array.from(new Set(actions.flatMap((item) => item.capabilities || []))).length;

  return [
    `本轮共编排 ${total} 个任务`,
    completed > 0 ? `${completed} 个已完成` : '',
    running > 0 ? `${running} 个进行中` : '',
    failed > 0 ? `${failed} 个需复核` : '',
    capabilityCount > 0 ? `覆盖 ${capabilityCount} 类能力` : '',
  ].filter(Boolean).join('，');
}

function buildRoundStatusSummary(actions: PentestLogEntry[]) {
  const running = actions.filter((item) => item.status === 'running').length;
  const failed = actions.filter((item) =>
    item.status === 'failed' || !!item.error || (typeof item.returncode === 'number' && item.returncode !== 0)
  ).length;

  if (running > 0) {
    return `本轮仍在推进，当前有 ${running} 个任务执行中。`;
  }
  if (failed > 0) {
    return `本轮已结束，其中 ${failed} 个任务结果异常，建议结合报告继续复核。`;
  }
  return '本轮任务已完成，详细过程已收敛为轮次总结。';
}

function buildRoundSurfaceSummary(actions: PentestLogEntry[]) {
  const surfaces = Array.from(new Set(
    actions
      .map((item) => String(item.surface || '').trim())
      .filter(Boolean)
  ));
  const capabilities = Array.from(new Set(actions.flatMap((item) => item.capabilities || [])));
  const parts: string[] = [];
  if (surfaces.length > 0) {
    parts.push(`涉及面：${surfaces.slice(0, 4).join('、')}`);
  }
  if (capabilities.length > 0) {
    parts.push(`能力域：${capabilities.slice(0, 4).join('、')}`);
  }
  return parts.join('；');
}

function getRoundStatusClass(actions: PentestLogEntry[]) {
  if (actions.some((item) => item.status === 'running')) return 'running';
  if (actions.some((item) => item.status === 'failed' || !!item.error || (typeof item.returncode === 'number' && item.returncode !== 0))) return 'failed';
  return 'completed';
}

function getRoundStatusText(actions: PentestLogEntry[]) {
  const statusClass = getRoundStatusClass(actions);
  if (statusClass === 'running') return '执行中';
  if (statusClass === 'failed') return '待复核';
  return '已完成';
}

const currentActionSummary = computed(() => {
  if (!agentResult.value?.actions?.length) return '';
  const latest = agentResult.value.actions[agentResult.value.actions.length - 1];
  if (!latest) return '';
  if (latest.tool === '_llm_wait') {
    return 'AI 正在分析当前态势，规划下一轮任务...';
  }
  if (latest.status === 'running') {
    return '当前轮次任务正在执行中';
  }
  return '';
});

function normalizeTokenUsageBucket(input: any) {
  if (!input || typeof input !== 'object') {
    return null;
  }
  const prompt = Number(input.prompt_tokens ?? 0) || 0;
  const completion = Number(input.completion_tokens ?? 0) || 0;
  const total = Number(input.total_tokens ?? (prompt + completion)) || 0;
  const calls = Number(input.calls ?? 0) || 0;
  if (prompt <= 0 && completion <= 0 && total <= 0 && calls <= 0) {
    return null;
  }
  return { prompt, completion, total, calls };
}

function formatTokenCount(value: number) {
  const normalized = Number(value || 0);
  if (!Number.isFinite(normalized) || normalized <= 0) {
    return '--';
  }
  return normalized.toLocaleString('zh-CN');
}

const currentTokenUsage = computed(() => {
  const usageMap = agentResult.value?.token_usage;
  if (!usageMap || typeof usageMap !== 'object') {
    return null;
  }
  const pentest = normalizeTokenUsageBucket(usageMap.pentest_llm);
  const report = normalizeTokenUsageBucket(usageMap.report_ai);
  const total = (pentest?.total || 0) + (report?.total || 0);
  const calls = (pentest?.calls || 0) + (report?.calls || 0);
  if (!pentest && !report && total <= 0 && calls <= 0) {
    return null;
  }
  return { pentest, report, total, calls };
});

const currentTokenUsageDisplay = computed(() => {
  if (!currentTokenUsage.value) {
    return '--';
  }
  return `${formatTokenCount(currentTokenUsage.value.total)} tokens`;
});

const currentTokenUsageMeta = computed(() => {
  if (!currentTokenUsage.value) {
    return '等待上游返回 usage';
  }
  const parts: string[] = [];
  if (currentTokenUsage.value.pentest) {
    parts.push(`主流程 ${formatTokenCount(currentTokenUsage.value.pentest.total)}`);
  }
  if (currentTokenUsage.value.report) {
    parts.push(`报告 ${formatTokenCount(currentTokenUsage.value.report.total)}`);
  }
  if (parts.length === 0 && currentTokenUsage.value.calls > 0) {
    parts.push(`${currentTokenUsage.value.calls} 次调用`);
  }
  return parts.join(' / ') || '等待上游返回 usage';
});

const currentPlanningStream = computed(() => {
  if (!agentResult.value?.actions?.length) return '';
  const latest = agentResult.value.actions[agentResult.value.actions.length - 1];
  if (!latest || latest.tool !== '_llm_wait') {
    return '';
  }
  return formatActionPayload(latest.result || latest.full_stdout, '');
});

const currentActionElapsed = ref('');
let elapsedTimer: ReturnType<typeof setInterval> | null = null;

const compactRoundItems = computed<PentestLogRound[]>(() => {
  const actions = (Array.isArray(agentResult.value?.actions) ? agentResult.value.actions : [])
    .map((item: any) => normalizeLogEntry(item));
  if (actions.length === 0) {
    return [];
  }

  const grouped = new Map<string, PentestLogRound>();
  actions.forEach((action: PentestLogEntry, index: number) => {
    const round = typeof (action as any).round === 'number' ? (action as any).round : null;
    const key = round !== null ? `round-${round}` : `single-${index}`;
    if (!grouped.has(key)) {
      grouped.set(key, {
        key,
        round,
        time: action.time,
        llm_decision: action.llm_decision,
        actions: [],
        summary: '',
        statusSummary: '',
        surfaceSummary: '',
        statusClass: 'completed',
        statusText: '已完成',
        hasRunning: false,
        title: `第 ${round ?? grouped.size + 1} 轮任务`,
      });
    }
    const group = grouped.get(key)!;
    if (!group.time && action.time) {
      group.time = action.time;
    }
    if (!group.llm_decision && action.llm_decision) {
      group.llm_decision = action.llm_decision;
    }
    group.actions.push(action);
  });

  return Array.from(grouped.values())
    .map((group, index) => {
      group.summary = buildRoundSummary(group.actions);
      group.statusSummary = buildRoundStatusSummary(group.actions);
      group.surfaceSummary = buildRoundSurfaceSummary(group.actions);
      group.statusClass = getRoundStatusClass(group.actions);
      group.statusText = getRoundStatusText(group.actions);
      group.hasRunning = group.statusClass === 'running';
      group.title = `第 ${group.round ?? index + 1} 轮任务`;
      return group;
    })
    .slice(-3)
    .reverse();
});

const agentRoundCount = computed(() => countTaskRounds(agentResult.value?.actions));

watch([() => agentResult.value?.actions, agentRunning], () => {
  if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; }
  if (!agentRunning.value || !agentResult.value?.actions?.length) {
    currentActionElapsed.value = '';
    return;
  }
  const latest = agentResult.value.actions[agentResult.value.actions.length - 1];
  if (!latest || latest.status !== 'running') {
    currentActionElapsed.value = '';
    return;
  }
  const startTime = new Date(latest.time).getTime();
  if (Number.isNaN(startTime)) {
    currentActionElapsed.value = '';
    return;
  }
  const updateElapsed = () => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    if (elapsed < 60) {
      currentActionElapsed.value = `${elapsed}s`;
    } else {
      const min = Math.floor(elapsed / 60);
      const sec = elapsed % 60;
      currentActionElapsed.value = `${min}m${sec}s`;
    }
  };
  updateElapsed();
  elapsedTimer = setInterval(updateElapsed, 1000);
}, { deep: true });

function formatActionTime(value: string | undefined) {
  if (!value) {
    return '刚刚';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

// 移除 ANSI 转义码（终端颜色代码）
function stripAnsiEscapeCodes(text: string): string {
  // 匹配 ANSI 转义序列: ESC [ ... m 或 ESC [ ... ; ... m 等
  return text.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
    // 匹配其他常见 ANSI 转义序列
    .replace(/\x1b\([0-9a-zA-Z]/g, '')
    .replace(/\x1b\)[0-9a-zA-Z]/g, '')
    .replace(/\x1b[0-9]/g, '');
}

function formatActionPayload(value: unknown, fallback: string) {
  if (value === null || value === undefined) {
    return fallback;
  }

  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return stripAnsiEscapeCodes(String(value));
    }
  }

  const rawText = String(value).trim();
  if (!rawText) {
    return fallback;
  }

  // 先移除 ANSI 转义码
  const text = stripAnsiEscapeCodes(rawText);
  if (!text) {
    return fallback;
  }

  if (text.startsWith('{') || text.startsWith('[')) {
    try {
      return JSON.stringify(JSON.parse(text), null, 2);
    } catch {
      return text;
    }
  }

  return text;
}

function summarizeActionPayload(value: unknown, fallback: string, maxLength = 120) {
  const formatted = formatActionPayload(value, fallback)
    .replace(/\s+/g, ' ')
    .trim();

  if (!formatted) {
    return fallback;
  }

  if (formatted.length <= maxLength) {
    return formatted;
  }

  return `${formatted.slice(0, maxLength).trimEnd()}...`;
}

function escapeReportHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatReportInline(text: string) {
  return escapeReportHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

function reportH1(title: string) {
  return `<h1>${escapeReportHtml(title)}</h1>`;
}

function reportH2(title: string) {
  return `<h2>${escapeReportHtml(title)}</h2>`;
}

function reportH3(title: string) {
  return `<h3>${escapeReportHtml(title)}</h3>`;
}

function reportP(text: string) {
  return `<p>${formatReportInline(text)}</p>`;
}

function reportLiHtml(html: string) {
  return `<li>${html}</li>`;
}

function reportUl(items: string[]) {
  if (!items.length) {
    return '<ul><li>暂无。</li></ul>';
  }
  return `<ul>${items.join('')}</ul>`;
}

function reportOl(items: string[]) {
  if (!items.length) {
    return '<ol><li>暂无。</li></ol>';
  }
  return `<ol>${items.join('')}</ol>`;
}

function reportStrongLi(label: string, value: string) {
  return reportLiHtml(`<strong>${escapeReportHtml(label)}：</strong> ${formatReportInline(value)}`);
}

function buildReportListItemHtml(label: string, value: unknown, fallback: string, maxLength = 140) {
  return reportStrongLi(label, summarizeReportValue(value, fallback, maxLength));
}

function reportOlText(items: string[]) {
  return reportOl(items.map((item) => reportLiHtml(formatReportInline(item))));
}

function summarizeReportValue(value: unknown, fallback: string, maxLength = 120) {
  const raw = stripAnsiEscapeCodes(formatActionPayload(value, fallback))
    .replace(/\s+/g, ' ')
    .trim();

  if (!raw) {
    return fallback;
  }

  let summary = raw;
  const jsonLike = raw.startsWith('[') || raw.startsWith('{');
  if (jsonLike) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        const preview = parsed.slice(0, 3).map((item) => {
          if (item && typeof item === 'object') {
            const record = item as Record<string, unknown>;
            const port = record.port ? `${record.port}` : '';
            const service = record.service ? `${record.service}` : '';
            const url = record.url ? `${record.url}` : '';
            const techs = Array.isArray(record.technologies) ? record.technologies.slice(0, 3).join(', ') : '';
            const pieces = [port && `端口 ${port}`, service, url, techs].filter(Boolean);
            return pieces.join(' / ');
          }
          return String(item);
        }).filter(Boolean);
        summary = preview.join('；');
        if (parsed.length > preview.length) {
          summary += ` 等 ${parsed.length} 项`;
        }
      } else if (parsed && typeof parsed === 'object') {
        const entries = Object.entries(parsed as Record<string, unknown>)
          .slice(0, 4)
          .map(([key, item]) => `${key}: ${String(item)}`);
        summary = entries.join('；');
      }
    } catch {
      summary = raw;
    }
  }

  summary = summary
    .replace(/^\s*[-*]\s*/, '')
    .replace(/\s*[\r\n]+\s*/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();

  if (summary.length <= maxLength) {
    return summary;
  }

  return `${summary.slice(0, maxLength).trimEnd()}...`;
}

const REPORT_ALLOWED_TAGS = new Set([
  'article', 'section', 'div', 'span', 'p', 'br', 'hr',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'strong', 'em', 'b', 'i', 'u',
  'ul', 'ol', 'li',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'pre', 'code', 'blockquote',
  'a',
]);
const REPORT_BLOCKED_TAGS = new Set([
  'script', 'style', 'iframe', 'object', 'embed', 'link', 'meta', 'base',
  'form', 'input', 'button', 'textarea', 'select', 'option', 'svg', 'math',
]);
const REPORT_ALLOWED_ATTRIBUTES: Record<string, Set<string>> = {
  a: new Set(['href', 'target', 'rel']),
  code: new Set(['class']),
};

function isLikelyHtmlReport(content: string) {
  return /<\s*(article|section|div|span|p|br|hr|h1|h2|h3|h4|h5|h6|strong|em|ul|ol|li|table|thead|tbody|tr|th|td|pre|code|blockquote|a)\b/i.test(content);
}

function sanitizeReportHtml(html: string): string {
  const normalized = String(html || '').replace(/\r\n/g, '\n').trim();
  if (!normalized) {
    return '';
  }

  if (typeof DOMParser === 'undefined') {
    return escapeReportHtml(normalized).replace(/\n/g, '<br>');
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(normalized, 'text/html');

  const sanitizeNode = (parent: Node) => {
    for (const child of Array.from(parent.childNodes)) {
      if (child.nodeType === Node.COMMENT_NODE) {
        child.parentNode?.removeChild(child);
        continue;
      }

      if (child.nodeType !== Node.ELEMENT_NODE) {
        continue;
      }

      const element = child as HTMLElement;
      const tag = element.tagName.toLowerCase();

      if (REPORT_BLOCKED_TAGS.has(tag)) {
        element.remove();
        continue;
      }

      sanitizeNode(element);

      if (!REPORT_ALLOWED_TAGS.has(tag)) {
        const fragment = doc.createDocumentFragment();
        while (element.firstChild) {
          fragment.appendChild(element.firstChild);
        }
        element.replaceWith(fragment);
        continue;
      }

      const allowedAttributes = REPORT_ALLOWED_ATTRIBUTES[tag] || new Set<string>();
      for (const attr of Array.from(element.attributes)) {
        const name = attr.name.toLowerCase();
        const value = attr.value.trim();

        if (name.startsWith('on') || name === 'style' || !allowedAttributes.has(name)) {
          element.removeAttribute(attr.name);
          continue;
        }

        if (tag === 'a' && name === 'href' && !/^(https?:|mailto:|tel:|#)/i.test(value)) {
          element.removeAttribute(attr.name);
          continue;
        }

        if (tag === 'a' && name === 'target' && value !== '_blank') {
          element.removeAttribute(attr.name);
          continue;
        }

        if (tag === 'code' && name === 'class' && !/^language-[a-z0-9_-]+$/i.test(value)) {
          element.removeAttribute(attr.name);
        }
      }

      if (tag === 'a' && element.getAttribute('href')) {
        element.setAttribute('rel', 'noopener noreferrer');
        if (!element.getAttribute('target')) {
          element.setAttribute('target', '_blank');
        }
      }
    }
  };

  sanitizeNode(doc.body);
  return doc.body.innerHTML;
}

function wrapReportTables(html: string): string {
  if (!/<table\b/i.test(html) || typeof DOMParser === 'undefined') {
    return html;
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');

  for (const table of Array.from(doc.body.querySelectorAll('table'))) {
    if (table.parentElement?.classList.contains('report-table-wrap')) {
      continue;
    }
    const wrapper = doc.createElement('div');
    wrapper.className = 'report-table-wrap';
    table.parentNode?.insertBefore(wrapper, table);
    wrapper.appendChild(table);
  }

  return doc.body.innerHTML;
}

function extractReportPlainText(report: string): string {
  const normalized = String(report || '').replace(/\r\n/g, '\n');
  if (!normalized.trim()) {
    return '';
  }

  if (isLikelyHtmlReport(normalized)) {
    if (typeof DOMParser !== 'undefined') {
      const parser = new DOMParser();
      const doc = parser.parseFromString(sanitizeReportHtml(normalized), 'text/html');
      return String(doc.body.textContent || '')
        .replace(/\u00a0/g, ' ')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
    }
    return normalized.replace(/<[^>]+>/g, ' ');
  }

  return normalized
    .replace(/```[\s\S]*?```/g, (block) => block.replace(/```[a-z]*\n?/gi, '').replace(/```/g, ''))
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/^\s*[-*+]\s*/gm, '')
    .replace(/^\s*\d+\.\s*/gm, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[(.*?)\]\((.*?)\)/g, '$1')
    .replace(/\|/g, ' ')
    .trim();
}

function renderReportContent(content: string): string {
  const normalized = String(content || '').replace(/\r\n/g, '\n').trim();
  if (!normalized) {
    return '';
  }

  if (isLikelyHtmlReport(normalized)) {
    return wrapReportTables(sanitizeReportHtml(normalized));
  }

  try {
    marked.setOptions({
      gfm: true,
      breaks: true,
    });
    return wrapReportTables(sanitizeReportHtml(String(marked.parse(normalized))));
  } catch {
    return wrapReportTables(escapeReportHtml(normalized).replace(/\n/g, '<br>'));
  }
}

function buildFallbackPentestReport(params: {
  phase: string;
  target?: string;
  findingsCount?: number;
  vulnCount?: number;
  actionsCount?: number;
  error?: string;
  actions?: Array<{ tool?: string; time?: string; result?: string; status?: string }>;
}) {
  const target = params.target || normalizedPentestTarget.value || '未知目标';
  const vulnCount = params.vulnCount || 0;
  const findingsCount = params.findingsCount || 0;
  const riskLevel = getPentestRiskLevel(vulnCount, 0);
  const phaseLabel = getPhaseLabel(params.phase);
  const progressText = params.error
    ? `本次渗透测试在 ${phaseLabel} 阶段结束，原因：${params.error}`
    : `本次渗透测试在 ${phaseLabel} 阶段结束。`;

  return [
    reportH1('渗透测试报告'),
    reportH2('面向管理层的执行摘要'),
    reportOlText([
      `当前任务在 ${phaseLabel} 阶段结束，已识别 ${findingsCount} 项资产与 ${vulnCount} 项风险线索，当前总体风险等级按现有结果评估为 ${riskLevel}。`,
      '该阶段性报告基于当前已落盘结果整理，可用于企业侧先行开展暴露面收敛、补丁核查和访问控制加固。',
      '若后续正式报告已生成，应以正式报告中的漏洞清单、影响分析、攻击路径与分级整改建议为准。',
    ]),
    reportH2('当前进展'),
    reportP(progressText),
    reportH2('概览'),
    reportUl([
      reportStrongLi('目标', target),
      reportStrongLi('风险等级', riskLevel),
      reportStrongLi('任务轮次', `${countTaskRounds(params.actions as Array<Record<string, any>> | undefined) || 0} 轮`),
      reportStrongLi('发现资产', `${findingsCount} 项`),
      reportStrongLi('发现风险项', `${vulnCount} 项`),
    ]),
    reportH2('企业处置建议'),
    reportUl([
      reportLiHtml(formatReportInline('立即对目标资产开展暴露面收敛，限制互联网访问、临时下线高危服务或增加访问控制白名单。')),
      reportLiHtml(formatReportInline('对外网暴露服务执行补丁、版本与配置核查，优先验证远程命令执行、未授权访问、弱认证和敏感信息泄露相关风险。')),
      reportLiHtml(formatReportInline('对高权限账号、服务账号和共享凭据执行轮换，核查 SSH、数据库、FTP、Web 管理口等关键入口的认证与最小权限策略。')),
      reportLiHtml(formatReportInline('由应用负责人、系统负责人和安全负责人联合完成复测闭环，并保留日志、会话、命令回显等证据用于事件追踪。')),
    ]),
    reportH2('说明'),
    reportUl([
      reportLiHtml(formatReportInline('当前为阶段性兜底报告，详细漏洞证据与整改优先级请结合正式报告或任务日志中的完整输出执行。')),
    ]),
  ].join('\n');
}

function extractPotentialVulnerabilityHints(report: string, vulnCount: number): string[] {
  const lines = extractReportPlainText(report)
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  const matched = lines.filter((line) => /漏洞|风险|可利用|exploit|cve/i.test(line)).slice(0, 5);
  if (matched.length > 0) {
    return matched;
  }
  if (vulnCount > 0) {
    return [`已发现 ${vulnCount} 项潜在漏洞，建议结合执行日志继续验证利用条件。`];
  }
  return [];
}

function inferFindingSeverity(text: string) {
  const normalized = String(text || '').toLowerCase();
  if (/cve|rce|命令执行|远程执行|未授权|认证绕过|权限提升|提权|敏感信息泄露|高危|critical/.test(normalized)) {
    return '高';
  }
  if (/弱口令|匿名访问|过期|暴露|风险|漏洞|warning|medium|中危/.test(normalized)) {
    return '中';
  }
  return '待确认';
}

function inferFindingImpact(text: string) {
  const normalized = String(text || '').toLowerCase();
  if (/未授权|认证绕过|匿名访问/.test(normalized)) {
    return '可能导致未授权访问，攻击者可在缺乏有效身份验证的情况下接触目标服务或数据。';
  }
  if (/命令执行|rce|远程执行|shell/.test(normalized)) {
    return '一旦利用成功，可能导致目标主机被远程控制，进而扩大横向移动和数据泄露风险。';
  }
  if (/敏感信息|泄露|exposure|暴露/.test(normalized)) {
    return '可能导致敏感配置、账户信息或业务数据外泄，增加后续攻击和合规风险。';
  }
  if (/弱口令|口令|密码/.test(normalized)) {
    return '可能降低身份认证强度，增加暴力破解、撞库和横向移动的成功率。';
  }
  return '该风险可能扩大攻击面，建议结合资产重要性、暴露范围和利用条件进一步确认业务影响。';
}

function inferFindingRecommendation(text: string) {
  const normalized = String(text || '').toLowerCase();
  if (/匿名访问|ftp-anon|anonymous/.test(normalized)) {
    return '关闭匿名访问能力，核查历史访问日志，并仅为必要账号授予最小权限。';
  }
  if (/弱口令|口令|密码/.test(normalized)) {
    return '立即轮换相关账号口令，启用强密码策略，并补充多因素认证或访问来源限制。';
  }
  if (/sslv2|tls|证书|加密/.test(normalized)) {
    return '禁用过时加密协议和弱加密套件，统一升级到受支持的 TLS 配置并重新验证兼容性。';
  }
  if (/未授权|认证绕过|匿名访问/.test(normalized)) {
    return '补充身份认证与访问控制校验，限制来源范围，并对高风险接口增加审计与告警。';
  }
  if (/命令执行|rce|远程执行|shell/.test(normalized)) {
    return '优先修复可利用入口，限制执行权限，隔离高危服务，并补充主机层检测与告警。';
  }
  if (/泄露|敏感信息|暴露/.test(normalized)) {
    return '清理暴露信息，检查访问控制与脱敏策略，并排查相关凭据是否需要轮换。';
  }
  return '结合对应服务配置、补丁版本和访问控制策略进行加固，并在修复后安排复测。';
}

function buildFindingDetails(report: string, vulnCount: number) {
  const lines = extractReportPlainText(report)
    .split('\n')
    .map((line) => line.replace(/^[-*\d.\s]+/, '').trim())
    .filter((line) => line.length > 0);

  const candidates = Array.from(new Set(
    lines.filter((line) => /漏洞|风险|可利用|exploit|cve|未授权|匿名访问|弱口令|泄露|命令执行|提权|绕过/i.test(line))
  )).slice(0, Math.min(Math.max(vulnCount, 1), 8));

  if (candidates.length > 0) {
    return candidates.map((item, index) => ({
      title: `风险项 ${index + 1}`,
      summary: item,
      severity: inferFindingSeverity(item),
      impact: inferFindingImpact(item),
      recommendation: inferFindingRecommendation(item),
    }));
  }

  if (vulnCount > 0) {
    return Array.from({ length: vulnCount }).slice(0, 5).map((_, index) => ({
      title: `风险项 ${index + 1}`,
      summary: `已识别第 ${index + 1} 项待复核风险，建议结合执行日志确认具体漏洞位置、利用条件与影响范围。`,
      severity: '待确认',
      impact: '当前已发现异常迹象，但仍需结合原始输出与业务上下文确认最终影响。',
      recommendation: '补充人工复核、证据留存与复测验证，确认是否具备实际可利用性。',
    }));
  }

  return [];
}

function buildGeneralRemediations(findings: Array<{ recommendation: string }>, failedLogs: PentestLogEntry[]) {
  const recommendations = Array.from(new Set(findings.map((item) => item.recommendation).filter(Boolean)));
  if (failedLogs.length > 0) {
    recommendations.push('针对失败或中断的探测步骤补充人工复核，避免因工具依赖、权限或网络条件导致漏报。');
  }
  recommendations.push('修复完成后重新执行渗透测试，确认风险项已关闭且未引入新的暴露面。');
  return recommendations.slice(0, 6);
}

function buildAssetSummaryHtml(target: string, logs: PentestLogEntry[], findingsCount: number, vulnCount: number) {
  const actionableLogs = logs.filter((log) => !String(log.tool || '').startsWith('_'));
  const surfaces = Array.from(new Set(
    actionableLogs.map((log) => summarizeActionPayload(log.surface, '', 40)).filter(Boolean)
  )).slice(0, 6);
  const tools = Array.from(new Set(
    actionableLogs.map((log) => summarizeActionPayload(log.tool, '', 40)).filter(Boolean)
  )).slice(0, 8);

  const corpus = actionableLogs
    .map((log) => [
      summarizeActionPayload(log.args, '', 240),
      summarizeActionPayload(log.result, '', 240),
      summarizeActionPayload(log.full_stdout, '', 240),
    ].filter(Boolean).join(' '))
    .join(' ');

  const portMatches = Array.from(new Set((corpus.match(/\b\d{1,5}\/tcp\b|\b\d{1,5}\/udp\b|\bport\s+\d{1,5}\b/gi) || [])
    .map((item) => item.replace(/^port\s+/i, '').toLowerCase())))
    .slice(0, 10);

  const serviceMatches = Array.from(new Set((corpus.match(/\b(ssh|ftp|http|https|mysql|postgresql|postgres|redis|smb|rpcbind|telnet|smtp|vnc|ajp13|distccd|java-rmi|nginx|apache|tomcat)\b/gi) || [])
    .map((item) => item.toLowerCase())))
    .slice(0, 10);

  return [
    reportStrongLi('目标资产', target || '未知目标'),
    reportStrongLi('资产发现概况', `共识别 ${findingsCount || 0} 项资产线索，关联 ${vulnCount || 0} 项风险。`),
    reportStrongLi(
      '涉及攻击面',
      surfaces.length > 0 ? surfaces.join('、') : '当前以基础探测结果为主，建议结合日志继续细化。',
    ),
    reportStrongLi(
      '关键端口/入口',
      portMatches.length > 0 ? portMatches.join('、') : '当前报告未提取到明确端口信息，可从执行日志继续确认。',
    ),
    reportStrongLi(
      '关联服务',
      serviceMatches.length > 0 ? serviceMatches.join('、') : '当前报告未提取到明确服务名称，可结合原始输出补充。',
    ),
    reportStrongLi(
      '证据来源工具',
      tools.length > 0 ? tools.join('、') : '暂无可用工具证据摘要。',
    ),
  ];
}

function buildRemediationPlanHtml(findings: Array<{ title: string; summary: string; severity: string; recommendation: string }>) {
  const prioritized = findings.length > 0 ? findings : [{
    title: '通用整改项',
    summary: '当前未抽取到明确风险项名称，建议先依据完整日志补齐风险与资产映射。',
    severity: '待确认',
    recommendation: '补充人工复核、风险确认和整改闭环验证。',
  }];

  return prioritized.slice(0, 6).map((item, index) => {
    const priority = item.severity === '高' ? 'P1（优先立即处置）' : item.severity === '中' ? 'P2（优先安排修复）' : 'P3（需人工确认后处置）';
    const verification = item.severity === '高'
      ? '修复后立即复测对应入口，并确认未再出现未授权访问、远程执行或敏感信息暴露。'
      : item.severity === '中'
        ? '修复后对相关服务、配置和访问控制进行抽样复测，确认风险已收敛。'
        : '完成配置核查与证据复核后，再执行针对性复测确认整改效果。';

    return [
      reportH3(`整改项 ${index + 1}：${item.title}`),
      reportUl([
        reportStrongLi('对应风险', item.summary),
        reportStrongLi('整改优先级', priority),
        reportStrongLi('修复动作', item.recommendation),
        reportStrongLi('复测要求', verification),
        reportStrongLi('交付建议', '保留修复前后配置差异、执行截图与复测结果，纳入整改闭环记录。'),
      ]),
    ].join('\n');
  }).join('\n');
}

function getPentestRiskLevel(vulnCount: number, failedCount: number) {
  if (vulnCount >= 3) return '高';
  if (vulnCount >= 1) return '中';
  if (failedCount > 0) return '待确认';
  return '低';
}

function buildUserFacingPentestReport(params: {
  phase: string;
  target?: string;
  findingsCount?: number;
  vulnCount?: number;
  actionsCount?: number;
  error?: string;
  backendReport?: string;
  logs?: PentestLogEntry[];
}) {
  const logs = params.logs || [];
  const actionableLogs = logs.filter((log) => !String(log.tool || '').startsWith('_'));
  const completedLogs = actionableLogs.filter((log) => (log.status || 'completed') !== 'failed' && !log.error);
  const failedLogs = actionableLogs.filter((log) => (log.status || 'completed') === 'failed' || !!log.error || (typeof log.returncode === 'number' && log.returncode !== 0));

  const workedOn = Array.from(new Set(actionableLogs.map((log) => {
    const purpose = summarizeActionPayload(log.purpose, '', 100);
    return purpose || `${log.tool} ${summarizeActionPayload(log.args, '', 70)}`.trim();
  }).filter(Boolean))).slice(0, 6);

  const successItems = completedLogs.slice(0, 6).map((log) =>
    buildReportListItemHtml(log.tool, log.result || log.full_stdout || log.purpose, '执行完成', 150)
  );
  const failureItems = failedLogs.slice(0, 6).map((log) =>
    buildReportListItemHtml(log.tool, log.error || log.result || log.full_stdout, '执行失败', 150)
  );
  const decisionItems = Array.from(new Set(
    logs
      .map((log) => summarizeReportValue(log.llm_decision, '', 220))
      .filter(Boolean)
  )).slice(0, 4);
  const target = params.target || normalizedPentestTarget.value || '未知目标';
  const vulnHints = extractPotentialVulnerabilityHints(params.backendReport || '', params.vulnCount || 0);
  const findingDetails = buildFindingDetails(params.backendReport || '', params.vulnCount || 0);
  const remediationItems = buildGeneralRemediations(findingDetails, failedLogs);
  const assetSummary = buildAssetSummaryHtml(target, actionableLogs, params.findingsCount || 0, params.vulnCount || 0);
  const remediationPlan = buildRemediationPlanHtml(findingDetails);
  const riskLevel = getPentestRiskLevel(params.vulnCount || 0, failedLogs.length);
  const phaseLabel = getPhaseLabel(params.phase);
  const workedOnText = workedOn.length > 0 ? workedOn.join('；') : '已进行基础环境检查与探测';
  const statusSummary = params.error
    ? `本次渗透测试在 **${phaseLabel}** 阶段结束。结束原因：${params.error}`
    : `本次渗透测试已在 **${phaseLabel}** 阶段结束，当前结果可用于继续复核、修复和留痕。`;
  const overallConclusion = `本次渗透测试围绕目标 **${target}** 完成了 ${workedOnText} 等工作。综合已确认风险、失败项和可用证据，当前目标整体风险等级评估为 **${riskLevel}**。${params.vulnCount ? '建议优先处理已识别风险，并在修复后安排复测。' : '当前未发现明确高风险漏洞，但仍建议结合业务场景继续复核。'}`;

  return [
    reportH1('渗透测试报告'),
    reportH2('执行总结'),
    reportP(statusSummary),
    reportH2('概览'),
    reportUl([
      reportStrongLi('目标', target),
      reportStrongLi('结束阶段', phaseLabel),
      reportStrongLi('风险等级', riskLevel),
      reportStrongLi('任务轮次', `${countTaskRounds(actionableLogs as Array<Record<string, any>>) || 0} 轮`),
      reportStrongLi('成功项', `${completedLogs.length} 项`),
      reportStrongLi('失败项', `${failedLogs.length} 项`),
      reportStrongLi('发现资产', `${params.findingsCount || 0} 项`),
      reportStrongLi('发现风险项', `${params.vulnCount || 0} 项`),
    ]),
    reportH2('总体结论'),
    reportP(overallConclusion),
    reportH2('关键结果'),
    reportUl(successItems.length > 0 ? successItems : [reportLiHtml(formatReportInline('暂无明确成功结果'))]),
    reportH2('失败与阻塞'),
    reportUl(failureItems.length > 0 ? failureItems : [reportLiHtml(formatReportInline('暂无明确失败项'))]),
    reportH2('风险摘要'),
    reportUl(
      vulnHints.length > 0
        ? vulnHints.map((item) => reportLiHtml(formatReportInline(item)))
        : [reportLiHtml(formatReportInline('暂未发现明确可直接利用的漏洞，建议结合日志继续验证。'))],
    ),
    reportH2('漏洞资产总结'),
    reportUl(assetSummary),
    reportH2('风险明细'),
  ...(findingDetails.length > 0
      ? findingDetails.flatMap((item) => [
          reportH3(`${item.title}（${item.severity}）`),
          reportUl([
            reportStrongLi('发现内容', item.summary),
            reportStrongLi('影响分析', item.impact),
            reportStrongLi('处置建议', item.recommendation),
          ]),
        ])
      : [
          reportUl([
            reportLiHtml(formatReportInline('当前未提取到可单独成项的风险明细，建议结合完整日志与原始输出继续复核。')),
          ]),
        ]),
    reportH2('修复建议'),
    reportUl(
      remediationItems.length > 0
        ? remediationItems.map((item) => reportLiHtml(formatReportInline(item)))
        : [reportLiHtml(formatReportInline('暂无补充修复建议'))],
    ),
    reportH2('漏洞修复整改报告'),
    remediationPlan,
    reportH2('复测建议'),
    reportUl([
      reportLiHtml(formatReportInline('修复完成后针对已识别风险项逐一复测，确认利用路径、弱配置或暴露面已被关闭。')),
      reportLiHtml(formatReportInline('对失败或未完成的探测步骤安排补测，避免因环境因素导致风险遗漏。')),
      reportLiHtml(formatReportInline('保留本次执行日志、关键截图和原始输出，作为后续整改闭环与审计留痕依据。')),
    ]),
    reportH2('AI 决策摘要'),
    decisionItems.length > 0
      ? reportOlText(decisionItems)
      : reportOlText(['暂无 AI 决策记录']),
    reportH2('说明'),
    reportUl([
      reportLiHtml(formatReportInline('页面展示的是面向阅读的渗透测试报告，详细参数、原始输出和完整过程请查看右上角“日志”。')),
    ]),
  ].join('\n');
}

async function resolvePentestFinalReport(params: {
  taskId: string;
  phase: string;
  target?: string;
  findingsCount?: number;
  vulnCount?: number;
  actionsCount?: number;
  error?: string;
  actions?: Array<{ tool?: string; time?: string; result?: string; status?: string }>;
}) {
  let backendReport = '';
  let finalPhase = params.phase;
  let normalizedLogs: PentestLogEntry[] = [];
  let tokenUsage: Record<string, any> = {};
  let reportResponse: { view?: unknown } | null = null;

  try {
    const pythonApi = (await import('../../config/python-api.config')).default;
    const [report, logs] = await Promise.all([
      pythonApi.pentestGetReport(params.taskId).catch(() => null),
      pythonApi.pentestLogs(params.taskId).catch(() => null),
    ]);
    reportResponse = report;
    backendReport = String(report?.report || '').trim();
    finalPhase = report?.phase || params.phase;
    tokenUsage = report?.token_usage || {};
    normalizedLogs = (logs?.actions || []).map((item: any) => normalizeLogEntry(item));
  } catch {
    // ignore and use fallback
  }

  const clientReport = buildUserFacingPentestReport({
    ...params,
    phase: finalPhase,
    backendReport,
    logs: normalizedLogs,
  }) || buildFallbackPentestReport(params);
  const reportHtml = backendReport || clientReport;
  const reportView = resolveReportView({
    view: reportResponse?.view,
    html: reportHtml,
    context: {
      taskId: params.taskId,
      phaseLabel: getPhaseLabel(finalPhase),
    },
  });

  return {
    report: reportHtml,
    view: reportView,
    phase: finalPhase,
    tokenUsage,
  };
}

async function buildInterruptedPentestSummary(taskId: string, target: string = '') {
  const pythonApi = (await import('../../config/python-api.config')).default;

  const [statusResult, logResult] = await Promise.allSettled([
    pythonApi.pentestStatus(taskId),
    pythonApi.pentestLogs(taskId),
  ]);

  const status = statusResult.status === 'fulfilled' ? statusResult.value : null;
  const rawLogs = logResult.status === 'fulfilled' ? (logResult.value.actions || []) : [];
  const normalizedLogs = rawLogs.map((item: any) => normalizeLogEntry(item));

  const phase = status?.phase || logPhase.value || agentResult.value?.phase || 'init';
  const findingsCount = status?.findings_count ?? agentResult.value?.findings_count ?? 0;
  const vulnCount = status?.vuln_count ?? agentResult.value?.vuln_count ?? 0;
  const actionsCount = status?.actions_count ?? agentResult.value?.actions_count ?? normalizedLogs.length ?? 0;
  const actions = Array.isArray(status?.actions) ? status!.actions : (agentResult.value?.actions || []);
  const resolvedTarget = target || selectedTask.value?.target || '';
  const tokenUsage = status?.token_usage || agentResult.value?.token_usage || {};

  const fallbackReport = buildUserFacingPentestReport({
    phase,
    target: resolvedTarget,
    findingsCount,
    vulnCount,
    actionsCount,
    error: '任务已由用户手动中断，以下为中断前的阶段性结果。',
    logs: normalizedLogs,
  }) || buildFallbackPentestReport({
    phase,
    target: resolvedTarget,
    findingsCount,
    vulnCount,
    actionsCount,
    error: '任务已由用户手动中断，以下为中断前的阶段性结果。',
    actions,
  });

  if (!aiService.isConfigured()) {
    return {
      report: fallbackReport,
      phase,
      findingsCount,
      vulnCount,
      actionsCount,
      actions,
      tokenUsage,
    };
  }

  const recentLogs = normalizedLogs.slice(-8).map((log, index) => [
    `${index + 1}. 工具: ${log.tool}`,
    `   时间: ${log.time || '未知'}`,
    `   状态: ${getLogStatusLabel(log.status)}`,
    `   目的: ${summarizeActionPayload(log.purpose, '暂无目的说明', 120)}`,
    `   参数: ${summarizeActionPayload(log.args, '无参数', 140)}`,
    `   输出: ${summarizeActionPayload(log.full_stdout || log.result || log.error, '暂无输出', 180)}`,
  ].join('\n')).join('\n\n');

  const llmDecisions = Array.from(
    new Set(
      normalizedLogs
        .map((log) => summarizeActionPayload(log.llm_decision, '', 260))
        .filter((item) => item && item !== '...')
    )
  ).slice(-3).join('\n\n');

  try {
    const report = await aiService.chatStream([
      {
        role: 'system',
        content: '你是一名面向企业客户的渗透测试报告助手。任务已被用户手动中断，请严格基于当前阶段已确认的信息生成中文 HTML 报告片段。仅输出 HTML（使用 h1/h2/h3、p、ul/ol/li、table、strong、blockquote、pre/code 等标签），不要输出 Markdown，不要用 ```html 代码块包裹。报告必须正式、客观，并给出企业侧可执行的漏洞解决方案。必须包含：1. 面向管理层的执行摘要 2. 当前阶段与进展 3. 已确认风险/异常 4. 对企业的分级修复建议（立即/24小时内/一周内/长期）5. 未完成项与下一步建议。不要虚构不存在的结果，不要输出内部调试口吻。',
      },
      {
        role: 'user',
        content: `目标: ${normalizedPentestTarget.value || '未知目标'}
任务ID: ${taskId}
中断时阶段: ${getPhaseLabel(phase)}
任务轮次: ${countTaskRounds(normalizedLogs as Array<Record<string, any>>) || 0}
发现资产: ${findingsCount}
发现漏洞: ${vulnCount}

AI 决策摘要:
${llmDecisions || '暂无 AI 决策记录'}

最近执行日志:
${recentLogs || '暂无执行日志'}

请输出一份阶段性总结报告，明确哪些信息已经确认、企业当前应立即采取哪些措施，以及后续仍需补充的验证工作。`,
      },
    ]);

    const aiUsage = aiService.getLastUsage();
    if (aiUsage && aiUsage.total_tokens > 0) {
      try {
        await pythonApi.pentestRecordTokenUsage({
          task_id: taskId,
          category: 'report_ai',
          prompt_tokens: aiUsage.prompt_tokens,
          completion_tokens: aiUsage.completion_tokens,
          total_tokens: aiUsage.total_tokens,
          model: aiService.getConfig()?.model || '',
          provider: aiService.getConfig()?.provider || '',
        });
      } catch (error) {
        console.warn('写入 report_ai token_usage 失败:', error);
      }
    }
    const baseReport = report?.trim() || fallbackReport;
    const reportWithUsage = aiUsage && aiUsage.total_tokens > 0
      ? `${baseReport}${reportH2('Token 消耗统计')}${reportUl([
          reportStrongLi(
            'AI 解析报告',
            `prompt ${aiUsage.prompt_tokens} / completion ${aiUsage.completion_tokens} / total ${aiUsage.total_tokens}`,
          ),
        ])}`
      : baseReport;

    const reportView = resolveReportView({
      html: reportWithUsage,
      context: {
        taskId,
        phaseLabel: getPhaseLabel(phase),
      },
    });

    return {
      report: reportWithUsage,
      view: reportView,
      phase,
      findingsCount,
      vulnCount,
      actionsCount,
      actions,
      tokenUsage: aiUsage && aiUsage.total_tokens > 0
        ? {
            ...tokenUsage,
            report_ai: {
              ...(tokenUsage?.report_ai || {}),
              prompt_tokens: aiUsage.prompt_tokens,
              completion_tokens: aiUsage.completion_tokens,
              total_tokens: aiUsage.total_tokens,
            },
          }
        : tokenUsage,
    };
  } catch {
    return {
      report: fallbackReport,
      view: resolveReportView({
        html: fallbackReport,
        context: {
          taskId,
          phaseLabel: getPhaseLabel(phase),
        },
      }),
      phase,
      findingsCount,
      vulnCount,
      actionsCount,
      actions,
      tokenUsage,
    };
  }
}

async function startHostAgent() {
  const aiConfig = getAIConfig();
  if (!aiConfig || !aiConfig.apiKey) {
    pentestModalError.value = 'AI 服务未配置，请先在设置中完成 AI 模型配置';
    (window as any).showNotification?.('AI 服务未配置，请先在设置中完成 AI 模型配置', 'warning');
    (window as any).openAISettingsMenu?.();
    return;
  }

  const normalizedTarget = normalizedPentestTarget.value;
  if (!normalizedTarget) {
    pentestModalError.value = '请输入目标 IP 地址或域名';
    return;
  }

  pentestModalError.value = '';
  showPentestModal.value = false;
  showResultModal.value = true;

  const taskId = generateTaskId();
  const newTask: PentestTask = {
    id: taskId,
    taskId: '',
    target: normalizedTarget,
    running: true,
    phase: 'init',
    findingsCount: 0,
    vulnCount: 0,
    actionsCount: 0,
    actions: [],
    targets: [],
    timer: null,
    result: null,
    error: '',
    executionMode: pentestExecutionMode.value,
    startedAt: Date.now(),
  };
  pentestTasks.value = [...pentestTasks.value, newTask];
  selectedTaskId.value = taskId;

  try {
    const pythonApi = (await import('../../config/python-api.config')).default;
    const startRes = await pythonApi.pentestStart({
      target: normalizedTarget,
      max_rounds: 30,
      dry_run: false,
      execution_mode: pentestExecutionMode.value,
      api_key: aiConfig.apiKey,
      model: aiConfig.model,
      base_url: aiConfig.baseUrl,
      provider: aiConfig.provider,
      temperature: aiConfig.temperature,
    });

    if (!startRes.success) {
      updateTaskInList(taskId, { running: false, error: startRes.message });
      return;
    }

    updateTaskInList(taskId, { taskId: startRes.task_id, running: true });
    const timer = setInterval(() => pollStatusForTask(taskId), 2000);
    taskPollTimers.set(taskId, timer);
  } catch (err: any) {
    updateTaskInList(taskId, { running: false, error: err?.message || '启动渗透任务失败' });
  }
}

async function restoreRunningPentestTask() {
  try {
    const pythonApi = (await import('../../config/python-api.config')).default;
    const historyRes = await pythonApi.pentestHistory();
    const runningTasks = (historyRes.history || []).filter((item: any) => item?.status === 'running');

    for (const running of runningTasks) {
      if (!running?.task_id) continue;

      const status = await pythonApi.pentestStatus(running.task_id);
      if (!status?.running) continue;

      const existingTask = pentestTasks.value.find(t => t.taskId === running.task_id);
      if (existingTask) continue;

      const taskId = generateTaskId();
      const newTask: PentestTask = {
        id: taskId,
        taskId: running.task_id,
        target: running.target || status.targets?.[0] || '',
        running: true,
        phase: status.phase,
        findingsCount: status.findings_count || 0,
        vulnCount: status.vuln_count || 0,
        actionsCount: status.actions_count || 0,
        actions: status.actions || [],
        targets: status.targets || [],
        timer: null,
        result: {
          status: 'running',
          phase: status.phase,
          targets: status.targets,
          findings_count: status.findings_count,
          vuln_count: status.vuln_count,
          actions_count: status.actions_count,
          actions: status.actions,
          token_usage: status.token_usage || {},
        },
        error: '',
        executionMode: 'serial',
        startedAt: Date.now(),
      };
      pentestTasks.value = [...pentestTasks.value, newTask];
      if (!selectedTaskId.value) {
        selectedTaskId.value = taskId;
      }
      const timer = setInterval(() => pollStatusForTask(taskId), 2000);
      taskPollTimers.set(taskId, timer);
    }
  } catch (err) {
    console.error('恢复后台渗透任务失败:', err);
  }
}

async function pollStatusForTask(taskId: string) {
  const task = pentestTasks.value.find(t => t.id === taskId);
  if (!task || !task.taskId) return;
  try {
    const pythonApi = (await import('../../config/python-api.config')).default;
    const status = await pythonApi.pentestStatus(task.taskId);

    if (!status.running) {
      stopTaskTimer(taskId);
      updateTaskInList(taskId, {
        running: false,
        phase: status.phase,
        findingsCount: status.findings_count || 0,
        vulnCount: status.vuln_count || 0,
        actionsCount: status.actions_count || 0,
        actions: status.actions || [],
        targets: status.targets || [],
      });

      const report = await resolvePentestFinalReport({
        taskId: task.taskId,
        phase: status.phase,
        target: task.target,
        findingsCount: status.findings_count,
        vulnCount: status.vuln_count,
        actionsCount: status.actions_count,
        error: status.error,
        actions: status.actions,
      });

      updateTaskResult(taskId, {
        status: !status.error && status.phase === 'done' ? 'completed' : 'failed',
        final: { report: report.report, view: report.view, phase: report.phase },
        phase: status.phase,
        targets: status.targets,
        findings_count: status.findings_count,
        vuln_count: status.vuln_count,
        actions_count: status.actions_count,
        actions: status.actions,
        token_usage: report.tokenUsage || status.token_usage || {},
      });
    } else {
      updateTaskResult(taskId, {
        status: 'running',
        phase: status.phase,
        targets: status.targets,
        findings_count: status.findings_count,
        vuln_count: status.vuln_count,
        actions_count: status.actions_count,
        actions: status.actions,
        token_usage: status.token_usage || {},
      });
      updateTaskInList(taskId, {
        phase: status.phase,
        findingsCount: status.findings_count || 0,
        vulnCount: status.vuln_count || 0,
        actionsCount: status.actions_count || 0,
        actions: status.actions || [],
        targets: status.targets || [],
      });
    }
  } catch (err: any) {
    stopTaskTimer(taskId);
    updateTaskInList(taskId, { running: false, error: err?.message || '查询状态失败' });
  }
}

// ==================== 日志查看 ====================
const showLogModal = ref(false);
type PentestLogEntry = {
  id?: string;
  tool: string;
  args: string;
  time: string;
  result: string;
  full_stdout: string;
  llm_decision: string;
  returncode: number | null;
  error: string;
  status?: string;
  updated_at?: string;
  surface?: string;
  purpose?: string;
  round?: number;
  task_label?: string;
  ports?: number[];
  capabilities?: string[];
  execution_mode?: string;
  pid?: number | null;
  timeout_seconds?: number | null;
  streaming?: boolean;
};

type PentestLogRound = {
  key: string;
  round: number | null;
  time: string;
  llm_decision: string;
  actions: PentestLogEntry[];
  summary: string;
  statusSummary: string;
  surfaceSummary: string;
  statusClass: string;
  statusText: string;
  hasRunning: boolean;
  title: string;
};

const logData = ref<PentestLogEntry[]>([]);
const logLoading = ref(false);
const logError = ref('');
const logPhase = ref<string>('init');
const currentLogTaskId = ref('');
const logReport = ref('');
const logReportView = ref<PentestReportView | null>(null);
const logDetailRefs = ref<HTMLElement[]>([]);
const logDetailsSectionRef = ref<HTMLElement | null>(null);
const selectedLogActionId = ref('');

let logTimer: ReturnType<typeof setInterval> | null = null;

function getLogStatusLabel(status: string | undefined) {
  switch (status) {
    case 'running':
      return '执行中';
    case 'failed':
      return '失败';
    case 'dry_run':
      return '演练';
    default:
      return '已完成';
  }
}

function getActionStatusClass(action: PentestLogEntry) {
  if (action.status === 'running') return 'running';
  if (action.status === 'dry_run') return 'dry_run';
  if (action.status === 'failed' || !!action.error || (typeof action.returncode === 'number' && action.returncode !== 0)) {
    return 'failed';
  }
  return 'completed';
}

function getRoundExecutionActions(actions: PentestLogEntry[]) {
  return actions.filter((action) => action.tool !== '_llm_wait');
}

function describeAction(action: PentestLogEntry) {
  const parts = [action.surface, action.purpose].filter(Boolean);
  if (parts.length > 0) {
    return parts.join(' · ');
  }
  if (action.args) {
    return summarizeActionPayload(action.args, '无参数', 140);
  }
  return '未记录额外说明';
}

function summarizeActionOutcome(action: PentestLogEntry) {
  if (action.status === 'running') {
    return '任务仍在执行，结果尚未最终落盘。';
  }
  if (action.error) {
    return summarizeActionPayload(action.error, '执行失败', 180);
  }
  if (typeof action.returncode === 'number' && action.returncode !== 0) {
    const output = getPrimaryActionOutput(action) || getRawActionOutput(action);
    const detail = summarizeActionPayload(output, '命令返回非 0', 180);
    return '命令返回码 ' + action.returncode + '。' + detail;
  }
  const output = getPrimaryActionOutput(action);
  if (output) {
    return summarizeActionPayload(output, '已完成', 180);
  }
  if (action.status === 'dry_run') {
    return '本次为演练任务，未实际下发工具。';
  }
  return '任务已完成，但当前日志未记录更多结果内容。';
}

function getPrimaryActionOutput(action: PentestLogEntry) {
  return formatActionPayload(action.result, '').trim();
}

function getRawActionOutput(action: PentestLogEntry) {
  return formatActionPayload(action.full_stdout, '').trim();
}

function shouldShowRawOutput(action: PentestLogEntry) {
  const primary = getPrimaryActionOutput(action);
  const raw = getRawActionOutput(action);
  return !!raw && raw !== primary;
}

function formatExecutionMode(mode: string | undefined) {
  switch ((mode || "").toLowerCase()) {
    case "pty":
      return "PTY 实时流";
    case "pipe":
      return "管道流";
    default:
      return "标准执行";
  }
}

function getTerminalPanelOutput(action: PentestLogEntry | undefined) {
  if (!action) return "";
  return getRawActionOutput(action) || getPrimaryActionOutput(action) || formatActionPayload(action.error, "");
}

function selectTerminalAction(action: PentestLogEntry) {
  const nextId = action.id || "";
  selectedLogActionId.value = selectedLogActionId.value === nextId ? "" : nextId;
}

function syncSelectedTerminalAction() {
  const allActions = logData.value.filter((item) => item.tool !== "_llm_wait");
  if (selectedLogActionId.value) {
    const stillExists = allActions.some((item) => item.id === selectedLogActionId.value);
    if (stillExists) {
      return;
    }
  }
  selectedLogActionId.value = "";
}

function normalizeLogEntry(log: Record<string, unknown>) {
  return {
    id: typeof log.id === 'string' ? log.id : undefined,
    tool: String(log.tool || 'unknown'),
    args: String(log.args || ''),
    time: String(log.time || ''),
    result: stripAnsiEscapeCodes(String(log.result || '')),
    full_stdout: stripAnsiEscapeCodes(String(log.full_stdout || '')),
    llm_decision: stripAnsiEscapeCodes(String(log.llm_decision || '')),
    returncode: typeof log.returncode === 'number' ? log.returncode : null,
    error: stripAnsiEscapeCodes(String(log.error || '')),
    status: typeof log.status === 'string' ? log.status : 'completed',
    updated_at: typeof log.updated_at === 'string' ? log.updated_at : undefined,
    surface: typeof log.surface === 'string' ? log.surface : '',
    purpose: stripAnsiEscapeCodes(typeof log.purpose === 'string' ? log.purpose : ''),
    round: typeof log.round === 'number' ? log.round : undefined,
    task_label: typeof log.task_label === 'string' ? log.task_label : '',
    execution_mode: typeof log.execution_mode === 'string' ? log.execution_mode : '',
    pid: typeof log.pid === 'number' ? log.pid : null,
    timeout_seconds: typeof log.timeout_seconds === 'number' ? log.timeout_seconds : null,
    streaming: typeof log.streaming === 'boolean' ? log.streaming : false,
  };
}

const selectedLogAction = computed<PentestLogEntry | undefined>(() => {
  if (!selectedLogActionId.value) {
    return undefined;
  }
  return logData.value.find((item) => item.id === selectedLogActionId.value);
});

const logRounds = computed<PentestLogRound[]>(() => {
  const groups: PentestLogRound[] = [];
  const groupIndex = new Map<string, number>();

  logData.value.forEach((log, index) => {
    const streamingDecision = log.tool === '_llm_wait'
      ? formatActionPayload(log.result || log.full_stdout, log.llm_decision)
      : log.llm_decision;
    const round = typeof log.round === 'number' ? log.round : null;
    const key = round !== null ? `round-${round}` : `single-${log.id || index}`;
    let group = groupIndex.has(key) ? groups[groupIndex.get(key)!] : undefined;

    if (!group) {
      group = {
        key,
        round,
        time: log.time,
        llm_decision: streamingDecision,
        actions: [],
        summary: '',
        statusSummary: '',
        surfaceSummary: '',
        statusClass: 'completed',
        statusText: '已完成',
        hasRunning: false,
        title: `第 ${round ?? groups.length + 1} 轮任务`,
      };
      groupIndex.set(key, groups.length);
      groups.push(group);
    }

    if (!group.llm_decision && streamingDecision) {
      group.llm_decision = streamingDecision;
    }
    if (!group.time && log.time) {
      group.time = log.time;
    }
    group.actions.push(log);
  });

  return groups.map((group, index) => {
    group.summary = buildRoundSummary(group.actions);
    group.statusSummary = buildRoundStatusSummary(group.actions);
    group.surfaceSummary = buildRoundSurfaceSummary(group.actions);
    group.statusClass = getRoundStatusClass(group.actions);
    group.statusText = getRoundStatusText(group.actions);
    group.hasRunning = group.statusClass === 'running';
    group.title = `第 ${group.round ?? index + 1} 轮任务`;
    return group;
  });
});

const logTaskStatusLabel = computed(() => {
  const task = pentestTasks.value.find((item) => item.taskId === currentLogTaskId.value);
  if (task?.running) {
    return '运行中';
  }
  if (task?.error) {
    return '已失败';
  }
  if (logPhase.value === 'done') {
    return '已完成';
  }
  if (currentLogTaskId.value === currentTaskId.value && agentRunning.value) {
    return '运行中';
  }
  return getPhaseLabel(logPhase.value);
});

const logReportContext = computed(() => ({
  taskId: currentLogTaskId.value,
  phaseLabel: getPhaseLabel(logPhase.value),
  statusLabel: logTaskStatusLabel.value,
  logRounds: logRounds.value.length,
  logActions: logData.value.length,
}));

const renderedLogReportHtml = computed(() => renderReportContent(logReport.value));

const agentReportContext = computed(() => ({
  taskId: currentTaskId.value,
  phaseLabel: getPhaseLabel(agentResult.value?.final?.phase || agentResult.value?.phase || 'init'),
}));

const agentReportHtml = computed(() => renderReportContent(String(agentResult.value?.final?.report || '')));

const agentReportView = computed(() => {
  const finalResult = agentResult.value?.final;
  if (!finalResult?.report && !finalResult?.view) {
    return null;
  }
  return resolveReportView({
    view: finalResult.view,
    html: String(finalResult.report || ''),
    context: agentReportContext.value,
  });
});

function applyReportView(
  target: { value: PentestReportView | null },
  params: { view?: unknown; html?: string; context?: { taskId?: string; phaseLabel?: string; logRounds?: number; logActions?: number } },
) {
  target.value = resolveReportView({
    view: params.view,
    html: params.html,
    context: params.context,
  });
}

function stopLogPolling() {
  if (logTimer) {
    clearInterval(logTimer);
    logTimer = null;
  }
}

function syncLogPolling() {
  stopLogPolling();

  if (!showLogModal.value || !currentLogTaskId.value) {
    return;
  }

  if (currentLogTaskId.value === currentTaskId.value && agentRunning.value) {
    logTimer = setInterval(() => {
      void loadLogs(currentLogTaskId.value, true);
    }, 400);
  }
}

async function openLogModal(taskId?: string) {
  const tid = taskId || currentTaskId.value;
  showLogModal.value = true;
  logError.value = '';
  logDetailRefs.value = [];

  if (!tid) {
    logData.value = [];
    logReport.value = '';
    logReportView.value = null;
    logPhase.value = 'init';
    logError.value = '当前任务尚未生成日志，请稍后再试。';
    return;
  }

  if (currentLogTaskId.value !== tid) {
    logData.value = [];
    logReport.value = '';
    logReportView.value = null;
  }
  currentLogTaskId.value = tid;
  await loadLogs(tid);
}

function closeLogModal() {
  stopLogPolling();
  showLogModal.value = false;
  selectedLogActionId.value = "";
}

async function loadLogs(taskId?: string, silent = false) {
  const tid = taskId || currentLogTaskId.value || currentTaskId.value;
  if (!tid) return;

  currentLogTaskId.value = tid;
  if (!silent) {
    logLoading.value = true;
  }
  logError.value = '';
  try {
    const pythonApi = (await import('../../config/python-api.config')).default;
    const [logRes, reportRes] = await Promise.all([
      pythonApi.pentestLogs(tid),
      pythonApi.pentestGetReport(tid).catch(() => null),
    ]);
    logPhase.value = logRes.phase || reportRes?.phase || 'init';
    logData.value = (logRes.actions || []).map(normalizeLogEntry);
    syncSelectedTerminalAction();
    const fallbackReport = tid === currentTaskId.value
      ? String(agentResult.value?.final?.report || '').trim()
      : '';
    const reportHtml = String(reportRes?.report || fallbackReport).trim();
    logReport.value = reportHtml;
    applyReportView(logReportView, {
      view: reportRes?.view,
      html: reportHtml,
      context: {
        taskId: tid,
        phaseLabel: getPhaseLabel(logPhase.value),
        logRounds: logRounds.value.length,
        logActions: logData.value.length,
      },
    });
  } catch (err: any) {
    console.error('加载日志失败:', err);
    logError.value = err?.message || '加载日志失败';
  } finally {
    logLoading.value = false;
    syncLogPolling();
  }
}

watch(logData, () => {
  syncSelectedTerminalAction();
}, { deep: true });

function scrollLogDetailsIntoView() {
  const section = logDetailsSectionRef.value;
  if (section) {
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  const firstDetail = logDetailRefs.value[0];
  if (!firstDetail) {
    return;
  }
  firstDetail.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ==================== 历史记录 ====================
const showHistoryModal = ref(false);
const historyData = ref<Array<{
  task_id: string;
  target: string;
  start_time: string;
  status: string;
  phase: string;
  findings_count: number;
  vuln_count: number;
  actions_count: number;
}>>([]);

async function loadHistory() {
  try {
    const pythonApi = (await import('../../config/python-api.config')).default;
    const res = await pythonApi.pentestHistory();
    historyData.value = res.history || [];
  } catch (err: any) {
    console.error('加载历史失败:', err);
  }
}

async function viewHistoryLogs(taskId: string) {
  showHistoryModal.value = false;
  await openLogModal(taskId);
}

async function deleteHistory(taskId: string) {
  try {
    const pythonApi = (await import('../../config/python-api.config')).default;
    await pythonApi.pentestDeleteHistory(taskId);
    await loadHistory();
  } catch (err: any) {
    console.error('删除历史失败:', err);
  }
}

document.addEventListener('click', (e) => {
  const target = e.target as HTMLElement;
  if (!target.closest('.payloader-dropdown')) {
    showViewDropdown.value = false;
    showCategoryDropdown.value = false;
  }
});

onUnmounted(() => {
  taskPollTimers.forEach((timer) => clearInterval(timer));
  taskPollTimers.clear();
  stopLogPolling();
});

onMounted(() => {
  void restoreRunningPentestTask();
});
</script>

<style scoped>
.payloader-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
}

.payloader-toolbar-left {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.payloader-back-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 8px 16px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
  position: fixed;
  top: calc(3% + 16px);
  left: calc(10% + 16px);
  z-index: 1000;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.payloader-back-btn:hover {
  background: var(--bg-tertiary);
  border-color: var(--primary-color);
}

.payloader-dropdowns {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
}

.payloader-dropdown {
  position: relative;
}

.payloader-dropdown-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 8px 16px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.payloader-dropdown-btn:hover {
  background: var(--bg-tertiary);
  border-color: var(--primary-color);
}

.payloader-dropdown-arrow {
  transition: transform 0.2s ease;
}

.payloader-dropdown-menu {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 4px;
  min-width: 160px;
  max-height: 300px;
  overflow-y: auto;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 1000;
}

.payloader-dropdown-menu--large {
  min-width: 200px;
}

.payloader-dropdown-item {
  display: block;
  width: 100%;
  padding: 10px 16px;
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: all 0.15s ease;
}

.payloader-dropdown-item:hover {
  background: var(--bg-tertiary);
}

.payloader-dropdown-item.active {
  background: var(--primary-color);
  color: var(--text-white);
}

.payloader-search-box {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  background: var(--bg-secondary);
}

.payloader-search-icon {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.payloader-search-input {
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 13px;
  width: 200px;
  outline: none;
}

.payloader-search-input::placeholder {
  color: var(--text-secondary);
}

.payloader-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--spacing-lg);
  padding: var(--spacing-lg);
}

.payloader-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  padding: var(--spacing-lg);
  cursor: pointer;
  transition: all 0.2s ease;
}

.payloader-card:hover {
  border-color: var(--primary-color);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.payloader-card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
}

.payloader-card-category {
  font-size: 11px;
  color: var(--primary-color);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.payloader-card-subcategory {
  font-size: 10px;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
}

.payloader-card-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-sm) 0;
}

.payloader-card-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0 0 var(--spacing-md) 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.payloader-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.payloader-card-count {
  font-size: 12px;
  color: var(--text-tertiary);
}

.payloader-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.payloader-card-tag {
  font-size: 10px;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
}

.payloader-detail {
  padding: var(--spacing-lg);
  max-width: 1200px;
  margin: 0 auto;
}

.payloader-detail-header {
  margin-bottom: var(--spacing-xl);
  padding-bottom: var(--spacing-lg);
  border-bottom: 1px solid var(--border-color);
}

.payloader-detail-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.payloader-detail-category {
  font-size: 12px;
  color: var(--primary-color);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.payloader-detail-subcategory {
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 4px;
}

.payloader-detail-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-sm) 0;
}

.payloader-detail-desc {
  font-size: 15px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0 0 var(--spacing-md) 0;
}

.payloader-detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.payloader-detail-tag {
  font-size: 12px;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 4px 10px;
  border-radius: 6px;
}

.payloader-detail-section {
  margin-bottom: var(--spacing-xl);
}

.payloader-detail-section-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-md) 0;
}

.payloader-detail-list {
  margin: 0;
  padding-left: var(--spacing-lg);
  color: var(--text-secondary);
  line-height: 1.8;
}

.payloader-detail-list li {
  margin-bottom: var(--spacing-xs);
}

/* 标签切换样式 */
.payloader-section-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: var(--spacing-lg);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--border-color);
}

.payloader-section-tab {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  padding: 10px 20px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.payloader-section-tab:hover {
  border-color: var(--primary-color);
  color: var(--text-primary);
}

.payloader-section-tab.active {
  background: rgba(0, 240, 255, 0.1);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.payloader-detail-commands,
.payloader-detail-executions {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.payloader-detail-command,
.payloader-detail-execution {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  padding: var(--spacing-lg);
}

.payloader-detail-command-header,
.payloader-detail-execution-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-sm);
}

.payloader-detail-command-title,
.payloader-detail-execution-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.payloader-detail-command-desc,
.payloader-detail-execution-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin: var(--spacing-sm) 0 0 0;
}

.payloader-detail-code {
  background: var(--bg-tertiary);
  padding: var(--spacing-md);
  border-radius: var(--border-radius);
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-primary);
  overflow-x: auto;
  border: 1px solid var(--border-color);
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

/* 攻击链可视化样式 */
.payloader-chain-header {
  margin-bottom: var(--spacing-lg);
}

.payloader-chain-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--primary-color);
  margin: 0 0 6px 0;
}

.payloader-chain-header p {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0;
}

.payloader-chain-visualization {
  display: flex;
  flex-direction: column;
  gap: 0;
  position: relative;
}

.payloader-chain-node-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.payloader-chain-node {
  width: 100%;
  max-width: 600px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 20px;
  position: relative;
  transition: all 0.2s ease;
}

.payloader-chain-node:hover {
  border-color: var(--primary-color);
  transform: translateY(-2px);
}

.payloader-chain-node.first {
  border-color: var(--success-color, #00ff88);
}

.payloader-chain-node.last {
  border-color: var(--danger-color, #ff0055);
}

.payloader-chain-node-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.payloader-chain-step {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 2px;
  padding: 3px 10px;
  border-radius: 4px;
  background: rgba(0, 240, 255, 0.1);
  color: var(--primary-color);
  border: 1px solid rgba(0, 240, 255, 0.3);
}

.payloader-chain-node.first .payloader-chain-step {
  background: rgba(0, 255, 136, 0.15);
  color: var(--success-color, #00ff88);
  border-color: var(--success-color, #00ff88);
}

.payloader-chain-node.last .payloader-chain-step {
  background: rgba(255, 0, 85, 0.15);
  color: var(--danger-color, #ff0055);
  border-color: var(--danger-color, #ff0055);
}

.payloader-chain-platform {
  font-size: 14px;
}

.payloader-chain-node-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 6px 0;
  color: var(--text-primary);
}

.payloader-chain-node-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0 0 10px 0;
  line-height: 1.5;
}

.payloader-chain-command-preview {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 10px;
}

.payloader-chain-command-preview code {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--primary-color);
  word-break: break-all;
}

.payloader-chain-node-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}

.payloader-chain-copy-btn {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  width: 30px;
  height: 30px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.payloader-chain-copy-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.payloader-chain-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0 10px;
  min-height: 42px;
}

.payloader-chain-arrow {
  width: 2px;
  height: 24px;
  background: linear-gradient(180deg, var(--primary-color), var(--accent-color, #a855f7));
  border-radius: 999px;
}

.payloader-chain-arrowhead {
  width: 10px;
  height: 10px;
  margin-top: -1px;
  border-right: 2px solid var(--accent-color, #a855f7);
  border-bottom: 2px solid var(--accent-color, #a855f7);
  transform: rotate(45deg);
}

/* 分析卡片样式 */
.payloader-analysis-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: var(--spacing-md);
}

.payloader-analysis-card.warning {
  background: rgba(255, 102, 0, 0.05);
  border-color: rgba(255, 102, 0, 0.3);
}

.payloader-analysis-card h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 12px 0;
  color: var(--primary-color);
}

.payloader-analysis-card p {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
  margin: 0;
}

.payloader-analysis-card ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.payloader-analysis-card li {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 8px 0;
  padding-left: 20px;
  position: relative;
}

.payloader-analysis-card.warning li::before {
  content: '⚠';
  position: absolute;
  left: 0;
}

.payloader-references-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.payloader-references-list li {
  padding: 8px 0;
}

.payloader-references-list a {
  color: var(--primary-color);
  font-size: 13px;
  text-decoration: none;
}

.payloader-references-list a:hover {
  color: var(--accent-color, #a855f7);
  text-decoration: underline;
}

.payloader-detail-tutorial {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.payloader-detail-tutorial-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  padding: var(--spacing-lg);
}

.payloader-detail-tutorial-item h4 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-sm) 0;
}

.payloader-detail-tutorial-item p {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 0;
}

/* ── 基础按钮 ── */
.payloader-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 20px;
  background: var(--bg-secondary, #1e1e2e);
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.1));
  border-radius: 10px;
  color: var(--text-primary, #e4e4e7);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
  line-height: 1;
}

.payloader-btn:hover:not(:disabled) {
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.08));
  border-color: var(--primary-color, #3b82f6);
  color: var(--primary-color, #3b82f6);
}

.payloader-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.payloader-btn--primary {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
  border-color: #2563eb;
  color: #fff;
}

.payloader-btn--primary:hover:not(:disabled) {
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  border-color: #1d4ed8;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.28);
  color: #fff;
}

.payloader-btn--secondary {
  background: var(--bg-secondary, #1e1e2e);
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.1));
  color: var(--text-primary, #e4e4e7);
}

.payloader-btn--secondary:hover:not(:disabled) {
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.08));
  border-color: var(--border-color, rgba(255, 255, 255, 0.2));
  color: var(--text-primary, #e4e4e7);
}

.payloader-btn--danger {
  background: linear-gradient(135deg, #ef4444, #dc2626);
  border-color: #dc2626;
  color: #fff;
}

.payloader-btn--danger:hover:not(:disabled) {
  background: linear-gradient(135deg, #dc2626, #b91c1c);
  border-color: #b91c1c;
  box-shadow: 0 4px 12px rgba(220, 38, 38, 0.28);
  color: #fff;
}

.payloader-btn--sm {
  padding: 6px 12px;
  font-size: 12px;
}

.payloader-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl);
  color: var(--text-secondary);
}

.payloader-loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border-color);
  border-top-color: var(--primary-color);
  border-radius: 50%;
  animation: payloader-spin 1s linear infinite;
  margin-bottom: var(--spacing-md);
}

@keyframes payloader-spin {
  to { transform: rotate(360deg); }
}

.payloader-loading-text {
  font-size: 14px;
}

.payloader-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl);
  text-align: center;
}

.payloader-error-icon {
  font-size: 48px;
  margin-bottom: var(--spacing-md);
}

.payloader-error-title {
  margin: 0 0 var(--spacing-sm) 0;
  font-size: 18px;
  color: var(--text-primary);
}

.payloader-error-description {
  margin: 0 0 var(--spacing-lg) 0;
  font-size: 14px;
  color: var(--text-secondary);
  max-width: 300px;
}

.payloader-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl);
  text-align: center;
}

.payloader-empty-icon {
  font-size: 48px;
  margin-bottom: var(--spacing-md);
}

.payloader-empty-title {
  margin: 0 0 var(--spacing-sm) 0;
  font-size: 18px;
  color: var(--text-primary);
}

.payloader-empty-description {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
  max-width: 300px;
}

.spinning {
  animation: payloader-spin 1s linear infinite;
}

/* Agent 按钮样式 */
.payloader-detail-actions {
  display: flex;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-md);
}

.payloader-btn--agent {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.payloader-btn--agent:hover:not(:disabled) {
  background: var(--bg-tertiary);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.payloader-btn--agent:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.payloader-btn--pentest {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #e74c3c, #c0392b);
  border: 1px solid #c0392b;
  border-radius: var(--border-radius);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.payloader-btn--pentest:hover:not(:disabled) {
  background: linear-gradient(135deg, #c0392b, #a93226);
  border-color: #a93226;
  box-shadow: 0 2px 8px rgba(231, 76, 60, 0.3);
}

.payloader-btn--pentest.is-running {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.18), rgba(16, 185, 129, 0.18));
  border-color: rgba(59, 130, 246, 0.35);
  color: var(--text-primary);
  box-shadow: 0 10px 24px rgba(59, 130, 246, 0.16);
}

.payloader-btn--pentest.is-running:hover:not(:disabled) {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.24), rgba(16, 185, 129, 0.24));
  border-color: rgba(59, 130, 246, 0.45);
  box-shadow: 0 14px 32px rgba(59, 130, 246, 0.2);
}

.payloader-btn-running-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.14);
  color: var(--primary-color);
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
}

.payloader-btn-running-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.14);
  animation: payloader-running-pulse 1.6s ease-in-out infinite;
}

.payloader-btn--pentest:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.payloader-agent-planning-stream {
  margin: 0 0 16px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid var(--border-color);
  background: linear-gradient(180deg, rgba(59, 130, 246, 0.08), rgba(59, 130, 246, 0.03));
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 220px;
  overflow: auto;
}

@keyframes payloader-running-pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.18);
    opacity: 0.78;
  }
}

/* 工具和编解码按钮样式 */
.payloader-btn--tool {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.payloader-btn--tool:hover {
  background: var(--bg-tertiary);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.payloader-btn--tool.active {
  background: var(--bg-tertiary);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.payloader-refresh-btn {
  min-height: 44px;
  white-space: nowrap;
}

/* Agent 运行中 */
.payloader-agent-running {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-xl);
  gap: var(--spacing-md);
}

.payloader-agent-running-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border-color);
  border-top-color: var(--primary-color);
  border-right-color: rgba(168, 85, 247, 0.8);
  border-radius: 50%;
  animation: payloader-spin 0.8s linear infinite;
  flex-shrink: 0;
}

.payloader-agent-running-header {
  display: flex;
  align-items: center;
  gap: 16px;
}

.payloader-agent-running-header-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.payloader-agent-phase-badge {
  display: inline-block;
  padding: 2px 8px;
  background: rgba(168, 85, 247, 0.15);
  color: var(--primary-color);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.payloader-agent-round-info {
  font-size: 12px;
  color: var(--text-secondary);
  margin-left: 8px;
}

.payloader-agent-pulse {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  margin-left: 8px;
  animation: payloader-pulse 1.5s ease-in-out infinite;
}

@keyframes payloader-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.8); }
}

.payloader-agent-current-action {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(168, 85, 247, 0.08);
  border: 1px solid rgba(168, 85, 247, 0.2);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-primary);
}

.payloader-agent-current-action-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary-color);
  animation: payloader-pulse 1.5s ease-in-out infinite;
  flex-shrink: 0;
}

.payloader-agent-current-action-text {
  flex: 1;
}

.payloader-agent-current-action-elapsed {
  color: var(--text-secondary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.payloader-agent-action-running {
  border-color: rgba(168, 85, 247, 0.3);
  background: rgba(168, 85, 247, 0.04);
}

.payloader-agent-action-tool-active {
  color: var(--primary-color);
  font-weight: 600;
}

.payloader-agent-action-status-running {
  font-size: 11px;
  color: #22c55e;
  background: rgba(34, 197, 94, 0.1);
  padding: 1px 6px;
  border-radius: 4px;
  margin-left: 6px;
}

.payloader-agent-running-text {
  font-size: 14px;
  color: var(--primary-color);
  font-weight: 500;
}

.payloader-agent-running-sub {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

.payloader-agent-live-panel {
  width: 100%;
  max-width: 760px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 8px;
}

.payloader-agent-live-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
}

.payloader-agent-live-stats--summary {
  margin-top: 16px;
}

.payloader-agent-live-stat {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.payloader-agent-live-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.payloader-agent-live-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.payloader-agent-live-meta {
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-secondary);
  word-break: break-word;
}

.payloader-agent-live-stat--token {
  background: linear-gradient(180deg, rgba(59, 130, 246, 0.06), rgba(168, 85, 247, 0.04));
  border-color: rgba(59, 130, 246, 0.16);
}

.payloader-agent-live-log {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 16px;
}

.payloader-agent-live-log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.payloader-agent-live-log-header h4 {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
}

.payloader-agent-live-log-header span {
  font-size: 12px;
  color: var(--text-secondary);
}

.payloader-agent-live-log-section {
  padding-top: 16px;
}

.payloader-agent-live-log--compact {
  gap: 10px;
}

.payloader-agent-log-hint {
  margin-bottom: 12px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.payloader-agent-compact-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.payloader-agent-compact-item {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 12px;
}

.payloader-agent-compact-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.payloader-agent-compact-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.payloader-agent-compact-line + .payloader-agent-compact-line {
  margin-top: 6px;
}

.payloader-agent-compact-text {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-primary);
  word-break: break-word;
}

.payloader-agent-action-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.payloader-agent-action-item {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 12px;
  box-shadow: var(--shadow-sm);
}

.payloader-agent-action-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.payloader-agent-action-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.payloader-agent-action-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.payloader-agent-action-tool {
  font-size: 13px;
  font-weight: 700;
  color: var(--primary-color);
}

.payloader-agent-action-time {
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.payloader-agent-action-args {
  margin: 0 0 10px;
  padding: 10px 12px;
  border: 1px solid rgba(66, 153, 225, 0.18);
  border-radius: 8px;
  background: rgba(66, 153, 225, 0.08);
  color: var(--text-primary);
  font-size: 13px;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
}

.payloader-agent-action-result {
  margin: 0;
  padding: 12px 14px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 13px;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow-y: auto;
  overflow-x: auto;
}

.payloader-agent-action-empty {
  font-size: 12px;
  color: var(--text-secondary);
  padding: 12px 0 4px;
}

[data-theme="light"] .payloader-agent-action-result {
  background: #f8fbff;
  border-color: rgba(66, 153, 225, 0.18);
}

[data-theme="dark"] .payloader-agent-action-args {
  background: rgba(66, 153, 225, 0.12);
  border-color: rgba(96, 165, 250, 0.28);
}

[data-theme="dark"] .payloader-agent-action-result {
  background: rgba(15, 23, 42, 0.72);
  border-color: rgba(148, 163, 184, 0.28);
}

/* Agent 错误 */
.payloader-agent-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-lg);
  text-align: center;
  background: rgba(255, 0, 85, 0.05);
  border: 1px solid rgba(255, 0, 85, 0.3);
  border-radius: 8px;
}

.payloader-agent-error-icon {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: rgba(255, 0, 85, 0.15);
  color: var(--danger-color, #ff0055);
  font-size: 16px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--spacing-sm);
}

.payloader-agent-error-title {
  font-size: 15px;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-sm) 0;
}

.payloader-agent-error-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-md) 0;
}

/* Agent 结果 */
.payloader-agent-result {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

/* 渗透攻击类型 */
.payloader-agent-attack-type {
  margin-bottom: var(--spacing-md);
}

.payloader-agent-attack-type-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  padding: 16px;
  background: linear-gradient(135deg, rgba(255, 0, 85, 0.05), rgba(255, 102, 0, 0.05));
  border: 1px solid rgba(255, 0, 85, 0.2);
  border-radius: 8px;
}

.payloader-agent-attack-type-badge {
  display: inline-block;
  padding: 6px 16px;
  background: linear-gradient(135deg, rgba(255, 0, 85, 0.15), rgba(255, 102, 0, 0.15));
  border: 1px solid rgba(255, 0, 85, 0.3);
  border-radius: 20px;
  color: var(--danger-color, #ff0055);
  font-size: 14px;
  font-weight: 600;
  text-align: center;
}

.payloader-agent-attack-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
}

/* 扫描结果 */
.payloader-agent-scan-results {
  margin-bottom: var(--spacing-md);
}

.payloader-agent-summary {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
}

.payloader-agent-summary-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-sm);
}

.payloader-agent-summary-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--primary-color);
  margin: 0;
}

.payloader-agent-status {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 4px;
  text-transform: uppercase;
}

.payloader-agent-status.completed {
  background: rgba(0, 255, 136, 0.15);
  color: var(--success-color, #00ff88);
}

.payloader-agent-status.failed {
  background: rgba(255, 0, 85, 0.15);
  color: var(--danger-color, #ff0055);
}

.payloader-agent-status.running {
  background: rgba(0, 240, 255, 0.15);
  color: var(--primary-color);
}

.payloader-agent-summary-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
  margin: 0;
}

/* Agent section */
.payloader-agent-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
}

.payloader-agent-section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--primary-color);
  margin: 0 0 var(--spacing-md) 0;
}

/* Agent steps */
.payloader-agent-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.payloader-agent-step {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
}

.payloader-agent-step-status {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}

.payloader-agent-step-status.completed {
  background: rgba(0, 255, 136, 0.15);
  color: var(--success-color, #00ff88);
}

.payloader-agent-step-status.failed {
  background: rgba(255, 0, 85, 0.15);
  color: var(--danger-color, #ff0055);
}

.payloader-agent-step-status.running {
  background: rgba(0, 240, 255, 0.15);
  color: var(--primary-color);
}

.payloader-agent-step-status.pending,
.payloader-agent-step-status.skipped {
  background: var(--bg-secondary);
  color: var(--text-tertiary);
}

.payloader-agent-step-title {
  font-size: 13px;
  color: var(--text-primary);
}

/* Agent traces */
.payloader-agent-traces {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.payloader-agent-trace {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
}

.payloader-agent-trace-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: 6px;
}

.payloader-agent-trace-tool {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary-color);
}

.payloader-agent-trace-status {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 3px;
  text-transform: uppercase;
}

.payloader-agent-trace-status.completed {
  background: rgba(0, 255, 136, 0.15);
  color: var(--success-color, #00ff88);
}

.payloader-agent-trace-status.failed {
  background: rgba(255, 0, 85, 0.15);
  color: var(--danger-color, #ff0055);
}

.payloader-agent-trace-duration {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-left: auto;
}

.payloader-agent-trace-summary,
.payloader-agent-trace-output {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 4px 0 0 0;
  word-break: break-all;
}

.payloader-agent-trace-error {
  font-size: 12px;
  color: var(--danger-color, #ff0055);
  margin: 4px 0 0 0;
}

/* Agent risks/recommendations/commands */
.payloader-agent-risks,
.payloader-agent-recommendations,
.payloader-agent-commands {
  margin-bottom: var(--spacing-md);
}

.payloader-agent-risks ul,
.payloader-agent-recommendations ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.payloader-agent-risks li {
  font-size: 13px;
  color: var(--danger-color, #ff0055);
  padding: 6px 0;
  padding-left: 20px;
  position: relative;
}

.payloader-agent-risks li::before {
  content: '!';
  position: absolute;
  left: 0;
  font-weight: 700;
}

.payloader-agent-recommendations li {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 6px 0;
  padding-left: 20px;
  position: relative;
  line-height: 1.6;
}

.payloader-agent-recommendations li::before {
  content: '>';
  position: absolute;
  left: 0;
  color: var(--primary-color);
  font-weight: 700;
}

.payloader-agent-command {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
}

.payloader-agent-command pre {
  flex: 1;
  margin: 0;
}

/* Agent skill results */
.payloader-agent-skill-result {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 8px;
}

.payloader-agent-skill-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: 6px;
}

.payloader-agent-skill-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.payloader-agent-skill-risk {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}

.payloader-agent-skill-risk.critical,
.payloader-agent-skill-risk.high {
  background: rgba(255, 0, 85, 0.15);
  color: var(--danger-color, #ff0055);
}

.payloader-agent-skill-risk.medium {
  background: rgba(255, 165, 0, 0.15);
  color: #ffa500;
}

.payloader-agent-skill-risk.low,
.payloader-agent-skill-risk.info {
  background: rgba(0, 255, 136, 0.15);
  color: var(--success-color, #00ff88);
}

.payloader-agent-report-section .payloader-agent-report-content {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
}
.payloader-agent-report-content p { margin: 0 0 10px; }
.payloader-agent-report-content h1 { font-size: 1.4em; font-weight: 600; margin: 16px 0 8px; color: var(--text-primary); }
.payloader-agent-report-content h2 { font-size: 1.2em; font-weight: 600; margin: 14px 0 6px; color: var(--text-primary); border-bottom: 1px solid var(--border-color); padding-bottom: 4px; }
.payloader-agent-report-content h3 { font-size: 1.1em; font-weight: 600; margin: 10px 0 4px; color: var(--text-primary); }
.payloader-agent-report-content strong { color: var(--text-primary); }
.payloader-agent-report-content code { background: var(--bg-secondary); padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.9em; }
.payloader-agent-report-content pre { margin: 10px 0; padding: 12px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; overflow-x: auto; white-space: pre-wrap; }
.payloader-agent-report-content pre code { display: block; padding: 0; background: transparent; border-radius: 0; }
.payloader-agent-report-content ul,
.payloader-agent-report-content ol { margin: 8px 0 12px 18px; padding: 0; }
.payloader-agent-report-content li { margin: 4px 0; padding-left: 4px; }
.payloader-agent-report-content hr { border: none; border-top: 1px solid var(--border-color); margin: 12px 0; }
.payloader-agent-report-content .report-table-wrap {
  width: 100%;
  overflow-x: auto;
  margin: 12px 0 16px;
  -webkit-overflow-scrolling: touch;
}
.payloader-agent-report-content table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  white-space: normal;
}
.payloader-agent-report-content thead {
  background: var(--bg-secondary);
}
.payloader-agent-report-content th,
.payloader-agent-report-content td {
  border: 1px solid var(--border-color);
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
  word-break: break-word;
  min-width: 96px;
}
.payloader-agent-report-content th {
  color: var(--text-primary);
  font-weight: 600;
}
.payloader-agent-report-content blockquote {
  margin: 12px 0;
  padding: 8px 12px;
  border-left: 3px solid var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
  color: var(--text-secondary);
}

.payloader-agent-skill-summary {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 渗透结果分析区块 */
.payloader-agent-analysis {
  background: rgba(255, 87, 34, 0.05);
  border: 1px solid rgba(255, 87, 34, 0.2);
  border-radius: 8px;
}

.payloader-agent-section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.payloader-agent-section-title svg {
  flex-shrink: 0;
}

.payloader-agent-analysis-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-tertiary);
  margin-bottom: 6px;
}

.payloader-agent-analysis-value {
  margin-bottom: 16px;
}

.payloader-agent-attack-type-badge {
  display: inline-block;
  background: linear-gradient(135deg, #ff5722, #ff9800);
  color: #fff;
  padding: 4px 14px;
  border-radius: 16px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.payloader-agent-attack-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-top: 8px;
}

.payloader-agent-scan-results {
  margin-bottom: 16px;
}

.payloader-agent-scan-results .payloader-detail-code {
  max-height: 200px;
  overflow-y: auto;
}

.payloader-agent-risks {
  margin-bottom: 0;
}

.payloader-agent-risk-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.payloader-agent-risk-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  background: rgba(255, 87, 34, 0.08);
  padding: 10px 12px;
  border-radius: 6px;
  border-left: 3px solid #ff5722;
}

.payloader-agent-risk-icon {
  flex-shrink: 0;
  font-size: 14px;
}

/* 安全防护建议区块 */
.payloader-agent-suggestions {
  background: rgba(76, 175, 80, 0.05);
  border: 1px solid rgba(76, 175, 80, 0.2);
  border-radius: 8px;
}

.payloader-agent-recommendations {
  margin-bottom: 16px;
}

.payloader-agent-suggestion-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.payloader-agent-suggestion-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  background: rgba(76, 175, 80, 0.08);
  padding: 10px 12px;
  border-radius: 6px;
  border-left: 3px solid #4caf50;
}

.payloader-agent-suggestion-icon {
  flex-shrink: 0;
  font-size: 14px;
  color: #4caf50;
  font-weight: bold;
}

.payloader-agent-commands {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.payloader-agent-command {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.payloader-agent-command .payloader-detail-code {
  flex: 1;
  margin: 0;
}

.payloader-agent-command .payloader-btn--sm {
  flex-shrink: 0;
  margin-top: 4px;
}

/* 使用的 Skills 区块 */
.payloader-agent-skills-section {
  background: rgba(103, 58, 183, 0.05);
  border: 1px solid rgba(103, 58, 183, 0.2);
  border-radius: 8px;
}

.payloader-agent-skills-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.payloader-agent-skill-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px;
  transition: all 0.2s ease;
}

.payloader-agent-skill-card:hover {
  border-color: var(--primary-color);
  transform: translateY(-1px);
}

.payloader-agent-skill-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.payloader-agent-skill-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.payloader-agent-skill-risk {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 2px 8px;
  border-radius: 10px;
}

.payloader-agent-skill-risk.critical,
.payloader-agent-skill-risk.high {
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
}

.payloader-agent-skill-risk.medium {
  background: rgba(255, 152, 0, 0.2);
  color: #ff9800;
}

.payloader-agent-skill-risk.low,
.payloader-agent-skill-risk.info {
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
}

.payloader-agent-skill-summary {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Agent empty */
.payloader-agent-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl);
}

.payloader-agent-empty p {
  font-size: 14px;
  color: var(--text-tertiary);
}

/* Agent 面板（列表模式） */
.payloader-agent-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  padding: var(--spacing-lg);
  margin: var(--spacing-lg);
}

.payloader-agent-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--border-color);
}

.payloader-agent-panel-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--primary-color);
  margin: 0;
}

/* Agent URL 弹窗 */
.payloader-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px) scale(0.95); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.payloader-modal {
  background: var(--bg-secondary, #1e1e2e);
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.1));
  border-radius: 16px;
  width: 520px;
  max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(59, 130, 246, 0.1);
  animation: slideUp 0.3s ease;
}

.payloader-modal--confirm {
  width: 460px;
}

.payloader-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-color, rgba(255, 255, 255, 0.06));
}

.payloader-task-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
}

.payloader-task-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.05));
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.06));
  border-radius: 8px;
  color: var(--text-secondary, #a1a1aa);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
  max-width: 200px;
}

.payloader-task-tab:hover {
  background: var(--bg-secondary, rgba(255, 255, 255, 0.08));
  color: var(--text-primary, #e4e4e7);
}

.payloader-task-tab.active {
  background: rgba(59, 130, 246, 0.12);
  border-color: rgba(59, 130, 246, 0.3);
  color: var(--primary-color, #60a5fa);
}

.payloader-task-tab-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--text-secondary, #a1a1aa);
}

.payloader-task-tab-dot.running {
  background: #22c55e;
  animation: payloader-pulse 1.5s ease-in-out infinite;
}

.payloader-task-tab-dot.completed {
  background: #3b82f6;
}

.payloader-task-tab-dot.failed {
  background: #ef4444;
}

@keyframes payloader-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.payloader-task-tab-target {
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono, monospace);
  font-size: 11px;
}

.payloader-task-tab-close {
  width: 16px;
  height: 16px;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  opacity: 0.6;
  transition: all 0.15s;
}

.payloader-task-tab-close:hover {
  opacity: 1;
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.payloader-task-tab-add {
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px dashed var(--border-color, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary, #a1a1aa);
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.15s;
}

.payloader-task-tab-add:hover {
  border-color: var(--primary-color, #60a5fa);
  color: var(--primary-color, #60a5fa);
}

.payloader-agent-task-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 0;
}

.payloader-agent-task-list-hint {
  text-align: center;
  color: var(--text-secondary, #a1a1aa);
  font-size: 14px;
  padding: 32px 0;
}

.payloader-agent-task-card {
  padding: 12px 16px;
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.03));
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.06));
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s;
}

.payloader-agent-task-card:hover {
  border-color: var(--primary-color, #60a5fa);
  background: rgba(59, 130, 246, 0.05);
}

.payloader-agent-task-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.payloader-agent-task-card-status {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.payloader-agent-task-card-status.running {
  background: rgba(34, 197, 94, 0.12);
  color: #22c55e;
}

.payloader-agent-task-card-status.completed {
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
}

.payloader-agent-task-card-status.failed {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
}

.payloader-agent-task-card-target {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #e4e4e7);
  font-family: var(--font-mono, monospace);
  margin-bottom: 4px;
}

.payloader-agent-task-card-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-secondary, #a1a1aa);
}

.payloader-modal-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #e4e4e7);
  margin: 0;
}

.payloader-modal-close {
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  border-radius: 8px;
  color: var(--text-secondary, #a1a1aa);
  font-size: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.payloader-modal-close:hover {
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.05));
  color: var(--text-primary, #e4e4e7);
}

.payloader-btn--danger {
  background: linear-gradient(135deg, #ef4444, #dc2626);
  border-color: #dc2626;
  color: #fff;
}

.payloader-btn--danger:hover:not(:disabled) {
  background: linear-gradient(135deg, #dc2626, #b91c1c);
  border-color: #b91c1c;
  box-shadow: 0 4px 12px rgba(220, 38, 38, 0.28);
}

.payloader-modal-body {
  padding: 20px 24px;
}

.payloader-modal-desc {
  font-size: 14px;
  color: var(--text-secondary, #a1a1aa);
  line-height: 1.6;
  margin: 0 0 20px;
}

.payloader-modal-input-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.payloader-modal-input-group--mode {
  margin-top: 14px;
}

.payloader-modal-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #e4e4e7);
}

.payloader-modal-input {
  width: 100%;
  padding: 12px 16px;
  background: var(--bg-primary, #12121a);
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.1));
  border-radius: 10px;
  color: var(--text-primary, #e4e4e7);
  font-size: 14px;
  font-family: var(--font-mono, 'Fira Code', 'Consolas', monospace);
  outline: none;
  transition: all 0.2s;
  box-sizing: border-box;
}

.payloader-modal-input:focus {
  border-color: var(--primary-color, #3b82f6);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

.payloader-modal-input::placeholder {
  color: var(--text-tertiary, #71717a);
}

.payloader-modal-helper {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary, #a1a1aa);
}

.payloader-mode-toggle {
  display: flex;
  width: 100%;
  border-radius: 10px;
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.1));
  background: var(--bg-primary, #12121a);
  overflow: hidden;
}

.payloader-mode-toggle-btn {
  flex: 1;
  padding: 10px 12px;
  border: none;
  background: transparent;
  color: var(--text-secondary, #a1a1aa);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.payloader-mode-toggle-btn:not(.active):hover {
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.04));
  color: var(--text-primary, #e4e4e7);
}

.payloader-mode-toggle-btn.active {
  background: var(--primary-color, #3b82f6);
  color: #fff;
}

.payloader-modal-error {
  margin-top: 12px;
  padding: 10px 14px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 8px;
  font-size: 13px;
  color: #f87171;
}

.payloader-modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px 20px;
  border-top: 1px solid var(--border-color, rgba(255, 255, 255, 0.06));
}

/* 结果弹窗特有样式 */
.payloader-modal--result {
  width: 680px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
}

.payloader-modal-body--scroll {
  overflow-y: auto;
  max-height: calc(85vh - 140px);
}

.payloader-agent-running-sub {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

/* ── 目标画像样式 ── */
.payloader-target-profile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.payloader-target-profile-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.payloader-target-profile-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-tertiary);
}

.payloader-target-profile-value {
  font-size: 13px;
  color: var(--text-primary);
  font-family: var(--font-mono);
  word-break: break-all;
}

/* ── 阶段验证链样式 ── */
.payloader-phase-chain {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.payloader-phase-node-wrapper {
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.payloader-phase-node {
  padding: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  transition: all 0.2s ease;
}

.payloader-phase-node:hover {
  border-color: var(--primary-color);
  transform: translateY(-1px);
}

.payloader-phase-node--completed {
  border-left: 3px solid var(--success-color, #00ff88);
}

.payloader-phase-node--failed {
  border-left: 3px solid var(--danger-color, #ff0055);
}

.payloader-phase-node--partial {
  border-left: 3px solid #ffa500;
}

.payloader-phase-node--skipped {
  border-left: 3px solid var(--text-tertiary);
  opacity: 0.7;
}

.payloader-phase-node-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.payloader-phase-step {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 2px;
  padding: 3px 10px;
  border-radius: 4px;
  background: rgba(0, 240, 255, 0.1);
  color: var(--primary-color);
  border: 1px solid rgba(0, 240, 255, 0.3);
}

.payloader-phase-status {
  font-size: 12px;
  font-weight: 500;
}

.payloader-phase-node-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 6px 0;
}

.payloader-phase-node-summary {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0 0 8px 0;
}

.payloader-phase-node-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11px;
}

.payloader-phase-evidence {
  color: var(--text-tertiary);
}

.payloader-phase-risk {
  color: var(--danger-color, #ff0055);
  font-weight: 500;
}

.payloader-phase-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 0;
}

.payloader-phase-arrow {
  width: 2px;
  height: 16px;
  background: linear-gradient(180deg, var(--primary-color), var(--accent-color, #a855f7));
}

/* ── 验证链样式 ── */
.payloader-validation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.payloader-validation-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 6px;
  border-left: 3px solid;
}

.payloader-validation-item.validated {
  background: rgba(0, 255, 136, 0.05);
  border-left-color: var(--success-color, #00ff88);
}

.payloader-validation-item.unvalidated {
  background: rgba(255, 0, 85, 0.05);
  border-left-color: var(--danger-color, #ff0055);
}

.payloader-validation-icon {
  flex-shrink: 0;
  font-size: 14px;
}

.payloader-validation-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.payloader-validation-finding {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.payloader-validation-conclusion {
  font-size: 11px;
  color: var(--text-secondary);
}

.payloader-validation-severity {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 2px 8px;
  border-radius: 10px;
}

.payloader-validation-severity.critical,
.payloader-validation-severity.high {
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
}

.payloader-validation-severity.medium {
  background: rgba(255, 152, 0, 0.2);
  color: #ff9800;
}

.payloader-validation-severity.low,
.payloader-validation-severity.info {
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
}

/* ── 风险假设样式 ── */
.payloader-hypothesis-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.payloader-hypothesis-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: rgba(255, 152, 0, 0.05);
  border: 1px solid rgba(255, 152, 0, 0.2);
  border-radius: 6px;
}

.payloader-hypothesis-severity {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 2px 8px;
  border-radius: 10px;
  flex-shrink: 0;
}

.payloader-hypothesis-severity.critical,
.payloader-hypothesis-severity.high {
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
}

.payloader-hypothesis-severity.medium {
  background: rgba(255, 152, 0, 0.2);
  color: #ff9800;
}

.payloader-hypothesis-severity.low {
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
}

.payloader-hypothesis-text {
  flex: 1;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.payloader-hypothesis-confidence {
  font-size: 11px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

/* ── Agent 阶段概览（确认弹窗中） ── */
.payloader-agent-phases-overview {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
}

.payloader-agent-phase-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  border-left: 3px solid var(--primary-color);
}

.payloader-agent-phase-num {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(0, 240, 255, 0.2), rgba(168, 85, 247, 0.2));
  border: 1px solid var(--primary-color);
  color: var(--primary-color);
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}

.payloader-agent-phase-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

/* ── 日志模态框 ── */
.payloader-modal--log {
  width: 92vw;
  max-width: 1440px;
  height: 88vh;
  display: flex;
  flex-direction: column;
}

.payloader-modal-header--log {
  padding: 12px 18px;
  border-bottom: 1px solid #e5e7eb;
  background: #fff;
}

.payloader-modal-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.payloader-log-header-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.payloader-log-header-sub {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-all;
}

.payloader-modal-header-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.payloader-modal-header-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.payloader-modal-header-btn:hover {
  background: var(--primary-color);
  color: #fff;
  border-color: var(--primary-color);
}

.payloader-modal-header-btn:disabled:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-color: var(--border-color);
}

.payloader-log-body {
  flex: 1;
  overflow-y: auto;
  background: #f3f4f6;
  padding: 16px 18px 20px;
}

.payloader-log-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.payloader-log-layout--with-terminal {
  grid-template-columns: minmax(0, 1.6fr) minmax(320px, 0.9fr);
}

.payloader-log-rounds {
  min-width: 0;
}

.payloader-log-terminal-inline-hint {
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px dashed var(--border-color);
  border-radius: 10px;
  background: rgba(59, 130, 246, 0.04);
  color: var(--text-secondary);
  font-size: 13px;
}

.payloader-log-terminal-panel {
  position: sticky;
  top: 0;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-secondary);
  min-height: 320px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.payloader-log-terminal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--border-color);
  background: rgba(59, 130, 246, 0.05);
}

.payloader-log-terminal-eyebrow {
  font-size: 11px;
  font-weight: 700;
  color: var(--primary-color);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-bottom: 4px;
}

.payloader-log-terminal-header h4 {
  margin: 0;
  font-size: 15px;
  line-height: 1.4;
  color: var(--text-primary);
}

.payloader-log-terminal-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  padding: 10px 16px;
  color: var(--text-secondary);
  font-size: 12px;
  border-bottom: 1px solid var(--border-color);
}

.payloader-log-terminal-body {
  flex: 1;
  min-height: 0;
  background: #0b1220;
}

.payloader-log-terminal-output {
  margin: 0;
  padding: 14px 16px;
  min-height: 100%;
  max-height: 68vh;
  overflow: auto;
  color: #dbeafe;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.payloader-log-terminal-empty {
  padding: 18px 16px;
  color: var(--text-secondary);
  font-size: 13px;
}

.payloader-log-report-section {
  margin-bottom: 18px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-secondary);
  padding: 16px 18px;
}

.payloader-log-report-section--dashboard,
.payloader-agent-report-section--dashboard {
  border: none;
  background: transparent;
  padding: 0 0 18px;
}

.payloader-log-details-section {
  margin-top: 4px;
  padding-top: 18px;
  border-top: 1px solid #e5e7eb;
}

.payloader-log-details-title {
  margin: 0 0 14px;
  font-size: 15px;
  font-weight: 700;
  color: #2563eb;
}

.payloader-agent-report-section--dashboard .payloader-agent-section-title {
  margin-bottom: 12px;
}

.payloader-log-report-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.payloader-log-report-eyebrow {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary-color);
  text-transform: uppercase;
  letter-spacing: 0.4px;
  margin-bottom: 4px;
}

.payloader-log-report-header h4 {
  margin: 0;
  font-size: 18px;
  line-height: 1.3;
  color: var(--text-primary);
}

.payloader-log-report-action {
  align-self: center;
}


.payloader-log-empty {
  text-align: center;
  color: var(--text-secondary);
  padding: 40px 0;
}

.payloader-log-empty--error {
  color: var(--error-color);
}

.payloader-log-round-group {
  margin-bottom: 18px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  overflow: hidden;
  background: var(--bg-secondary);
}

.payloader-log-round-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: linear-gradient(90deg, rgba(59, 130, 246, 0.12), rgba(16, 185, 129, 0.08));
  border-bottom: 1px solid var(--border-color);
  font-size: 12px;
}

.payloader-log-round-count {
  color: var(--text-secondary);
  font-weight: 600;
}

.payloader-log-entry {
  margin: 0 12px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-secondary);
}

.payloader-log-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-primary);
  border-bottom: 1px solid var(--border-color);
  font-size: 12px;
}

.payloader-log-round {
  color: var(--primary-color);
  font-weight: 700;
  font-size: 13px;
}

.payloader-log-tool {
  color: var(--accent-color, var(--primary-color));
  font-weight: 600;
  font-size: 13px;
}

.payloader-log-task {
  color: var(--primary-color);
  font-weight: 700;
  font-size: 12px;
}

.payloader-log-surface {
  color: var(--text-secondary);
  font-size: 12px;
  max-width: 320px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.payloader-log-status {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.payloader-log-status--running {
  background: rgba(66, 153, 225, 0.15);
  color: var(--primary-color);
}

.payloader-log-status--completed {
  background: rgba(72, 187, 120, 0.15);
  color: var(--success-color);
}

.payloader-log-status--failed {
  background: rgba(245, 101, 101, 0.15);
  color: var(--error-color);
}

.payloader-log-status--dry_run {
  background: rgba(237, 137, 54, 0.15);
  color: var(--warning-color);
}

.payloader-log-time {
  color: var(--text-secondary);
  margin-left: auto;
}

.payloader-log-rc {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.payloader-log-rc.ok {
  background: var(--success-color, #238636);
  color: #fff;
}

.payloader-log-rc.err {
  background: var(--error-color, #da3633);
  color: #fff;
}

.payloader-log-think,
.payloader-log-args,
.payloader-log-stdout,
.payloader-log-error {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-color);
}

.payloader-log-round-group > .payloader-log-think {
  background: rgba(59, 130, 246, 0.03);
}

.payloader-log-think-label,
.payloader-log-args-label,
.payloader-log-stdout-label,
.payloader-log-error-label {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.payloader-log-think-label { color: var(--primary-color); }
.payloader-log-args-label { color: var(--info-color, var(--primary-color)); }
.payloader-log-stdout-label { color: var(--success-color, #3fb950); }
.payloader-log-error-label { color: var(--error-color, #f85149); }

.payloader-log-think-content {
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
}

.payloader-log-code {
  margin: 0;
  padding: 10px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
  max-height: 300px;
  overflow-y: auto;
}

.payloader-log-action-list {
  padding: 12px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.payloader-log-section-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.payloader-log-action-empty {
  padding: 12px;
  border: 1px dashed var(--border-color);
  border-radius: 8px;
  color: var(--text-secondary);
  background: var(--bg-primary);
  font-size: 13px;
}

.payloader-log-action-card {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  padding: 12px;
}

.payloader-log-action-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}


.payloader-log-action-title-wrap {
  min-width: 0;
  flex: 1;
}

.payloader-log-action-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  word-break: break-word;
}

.payloader-log-action-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  word-break: break-word;
}

.payloader-log-action-badges {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.payloader-log-action-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}

.payloader-log-action-terminal-btn {
  padding: 7px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.payloader-log-action-terminal-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  background: rgba(59, 130, 246, 0.08);
}

.payloader-log-action-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}

.payloader-log-action-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
  border-radius: 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  min-width: 0;
}


.payloader-log-action-field--wide {
  grid-column: 1 / -1;
}


.payloader-log-action-field-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}


.payloader-log-action-field-value {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.5;
  word-break: break-word;
}

.payloader-log-detail-block {
  margin-top: 10px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  overflow: hidden;
}


.payloader-log-detail-block summary {
  cursor: pointer;
  padding: 10px 12px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
  list-style: none;
  user-select: none;
}



.payloader-log-detail-block summary::-webkit-details-marker {
  display: none;
}



.payloader-log-detail-block summary::before {
  content: '▶';
  display: inline-block;
  margin-right: 8px;
  font-size: 10px;
  transition: transform 0.15s ease;
}


.payloader-log-detail-block[open] summary::before {
  transform: rotate(90deg);
}

.payloader-log-detail-block .payloader-log-code {
  margin: 0 12px 12px;
}

.payloader-log-detail-block--error summary {
  color: var(--error-color);
}

@media (max-width: 1180px) {
  .payloader-log-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .payloader-log-terminal-panel {
    position: static;
  }
}

@media (max-width: 900px) {
  .payloader-log-action-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
/* ── 历史按钮 ── */
.payloader-btn--history {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.payloader-btn--history:hover {
  background: var(--bg-tertiary);
  border-color: var(--primary-color);
  color: var(--primary-color);
}

/* ── 历史弹窗 ── */
.payloader-modal--history {
  width: 600px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
}

.payloader-history-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px;
  border-bottom: 1px solid var(--border-color);
  transition: background 0.15s ease;
}

.payloader-history-item:hover {
  background: var(--bg-tertiary);
}

.payloader-history-main {
  flex: 1;
  min-width: 0;
}

.payloader-history-target {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.payloader-history-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}

.payloader-history-time {
  color: var(--text-secondary);
}

.payloader-history-status {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.payloader-history-status.running {
  background: #e6a23c33;
  color: #e6a23c;
}

.payloader-history-status.done {
  background: #67c23a33;
  color: #67c23a;
}

.payloader-history-status.stopped {
  background: #f56c6c33;
  color: #f56c6c;
}

.payloader-history-phase {
  color: var(--text-secondary);
}

.payloader-history-stats {
  display: flex;
  gap: 12px;
  font-size: 13px;
  color: var(--text-secondary);
}

.payloader-history-actions {
  display: flex;
  gap: 6px;
}

.payloader-btn--sm {
  padding: 4px 10px;
  font-size: 12px;
}
</style>
