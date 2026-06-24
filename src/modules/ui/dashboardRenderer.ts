/**
 * 系统信息仪表盘渲染器
 * 负责渲染系统监控信息和统计数据
 */

import type { SystemInfo } from '../ssh/sshManager';
import { sshConnectionManager } from '../remote/sshConnectionManager';
import { SystemDetector } from '../utils/systemDetector';
import {
  LinkOne,
  Dashboard as DashboardIcon,
  Refresh
} from '@icon-park/svg';

type DashboardLiveSnapshot = {
  cpuUsage: number;
  memUsage: number;
  diskUsage: number;
  load1: number;
  load5: number;
  load15: number;
  loadPercent: number;
  downloadRate: number;
  uploadRate: number;
  latencyMs: number | null;
};

export class DashboardRenderer {
  private static readonly HISTORY_MAX = 20;

  private cpuHistory: number[] = [];
  private memoryHistory: number[] = [];
  private diskHistory: number[] = [];
  private downloadHistory: number[] = [];
  private uploadHistory: number[] = [];
  private latencyHistory: number[] = [];
  private lastTrafficSample: { time: number; rxBytes: number; txBytes: number } | null = null;
  private lastSnapshotTime = -1;
  private lastSnapshot: DashboardLiveSnapshot | null = null;

  private systemMetaCache: {
    os: string;
    kernel: string;
    arch: string;
    virtualization: string;
    timezone: string;
  } | null = null;

  constructor() {
    (window as any).dashboardRendererInstance = this;
  }

  /**
   * 渲染系统信息仪表盘
   */
  renderDashboard(systemInfo?: SystemInfo, _theme: string = 'dark'): string {
    const isConnected = sshConnectionManager.isConnected();

    if (!isConnected) {
      return this.renderEmptyDashboard();
    }
    if (!systemInfo) {
      return this.renderConnectedButNoData();
    }

    setTimeout(() => {
      this.detectAndShowSystemType();
      this.loadSystemMeta();
    }, 100);

    const snapshot = this.getLiveSnapshot(systemInfo);
    const loadAvg = systemInfo.loadAverage || ['0', '0', '0'];
    const meta = this.systemMetaCache || { os: '检测中...' };

    return `
      <div class="dashboard-v3">
        <div class="dash-v3-header">
          <div class="dash-v3-header-left">
            <div class="dash-v3-logo">${DashboardIcon({ theme: 'filled', size: '22', fill: 'currentColor' })}</div>
            <div class="dash-v3-title-group">
              <h2 class="dash-v3-title">系统监控</h2>
              <span id="dashboard-last-update" class="dash-v3-subtitle">最后更新: ${this.formatTime(systemInfo.lastUpdate)}</span>
            </div>
            <div class="dash-v3-system-status">
              <span class="dash-v3-status-dot"></span>
              <div class="dash-v3-system-status-copy">
                <span class="dash-v3-system-status-text">已检测到系统:</span>
                <strong id="dashboard-os-value" title="${meta.os}">${meta.os}</strong>
              </div>
            </div>
          </div>
          <div class="dash-v3-header-right">
            <div class="dash-v3-refresh-stack">
              <button class="dash-v3-refresh-btn" onclick="window.loadSystemDetailedInfo(true)">
                ${Refresh({ theme: 'outline', size: '14', fill: 'currentColor' })}
                <span>刷新数据</span>
              </button>
              <div class="dash-v3-auto-refresh">
                <span>自动刷新: <strong>5秒</strong></span>
              </div>
            </div>
          </div>
        </div>

        <div class="dash-v3-info-bar">
          <div class="dash-v3-info-col">
            <div class="dash-v3-info-item">
              <span class="dash-v3-info-label">主机名</span>
              <span id="dashboard-hostname-value" class="dash-v3-info-value">${systemInfo.hostname}</span>
            </div>
            <div class="dash-v3-info-item">
              <span class="dash-v3-info-label">总内存</span>
              <span id="dashboard-memory-total-value" class="dash-v3-info-value">${systemInfo.memoryUsage.total}</span>
            </div>
          </div>
          <div class="dash-v3-info-col">
            <div class="dash-v3-info-item">
              <span class="dash-v3-info-label">处理器</span>
              <span id="dashboard-cpu-model-value" class="dash-v3-info-value" title="${systemInfo.cpuInfo.model}">${systemInfo.cpuInfo.model}</span>
            </div>
            <div class="dash-v3-info-item">
              <span class="dash-v3-info-label">磁盘总量</span>
              <span id="dashboard-disk-total-value" class="dash-v3-info-value">${systemInfo.diskUsage.total}</span>
            </div>
          </div>
          <div class="dash-v3-info-col">
            <div class="dash-v3-info-item">
              <span class="dash-v3-info-label">核心数</span>
              <span id="dashboard-cpu-cores-value" class="dash-v3-info-value">${systemInfo.cpuInfo.cores}</span>
            </div>
            <div class="dash-v3-info-item">
              <span class="dash-v3-info-label">运行时间</span>
              <span id="dashboard-uptime-value" class="dash-v3-info-value">${systemInfo.uptime}</span>
            </div>
          </div>
        </div>

        <div class="dash-v3-row dash-v3-row-charts">
          <div class="dash-v3-card">
            <div class="dash-v3-card-header">
              <span class="dash-v3-card-title">CPU使用率</span>
              <span id="dashboard-cpu-card-value" class="dash-v3-card-value">${snapshot.cpuUsage.toFixed(0)}<span class="dash-v3-card-unit">%</span></span>
            </div>
            <div class="dash-v3-card-body dash-v3-center">
              <div class="dash-v3-ring-wrap">
                <div id="dashboard-cpu-ring" class="dash-v3-ring" style="--ring-value: ${snapshot.cpuUsage}; --ring-gradient: linear-gradient(135deg, #22d3ee 0%, #2563eb 52%, #7c3aed 100%);">
                  <div class="dash-v3-ring-inner">
                    <span id="dashboard-cpu-ring-value" class="dash-v3-ring-value">${snapshot.cpuUsage.toFixed(0)}<span class="dash-v3-ring-unit">%</span></span>
                    <span class="dash-v3-ring-label">CPU使用率</span>
                  </div>
                </div>
                <div id="dashboard-cpu-mini-bars" class="dash-v3-mini-bars">
                  ${this.renderMiniBarChart(this.cpuHistory.slice(-10), '#3b82f6')}
                </div>
              </div>
            </div>
          </div>

          <div class="dash-v3-card">
            <div class="dash-v3-card-header">
              <span class="dash-v3-card-title">磁盘空间分布</span>
              <span id="dashboard-disk-card-value" class="dash-v3-card-value">${systemInfo.diskUsage.used} / ${systemInfo.diskUsage.total}</span>
            </div>
            <div class="dash-v3-card-body dash-v3-center">
              <div id="dashboard-disk-ring" class="dash-v3-ring" style="--ring-value: ${snapshot.diskUsage}; --ring-gradient: linear-gradient(135deg, #fde047 0%, #f97316 55%, #ef4444 100%);">
                <div class="dash-v3-ring-inner">
                  <span id="dashboard-disk-ring-value" class="dash-v3-ring-value">${snapshot.diskUsage.toFixed(0)}<span class="dash-v3-ring-unit">%</span></span>
                  <span class="dash-v3-ring-label">使用率</span>
                </div>
              </div>
            </div>
            <div class="dash-v3-card-footer">
              <span id="dashboard-disk-available">可用 ${systemInfo.diskUsage.available}</span>
              <span id="dashboard-partition-count">${systemInfo.partitions.length} 分区</span>
            </div>
          </div>

          <div class="dash-v3-card">
            <div class="dash-v3-card-header">
              <span class="dash-v3-card-title">系统负载</span>
              <span id="dashboard-load-card-value" class="dash-v3-card-value">${loadAvg.slice(0, 3).join(' / ')}</span>
            </div>
            <div class="dash-v3-card-body dash-v3-center">
              <div id="dashboard-load-ring" class="dash-v3-ring" style="--ring-value: ${snapshot.loadPercent}; --ring-gradient: linear-gradient(135deg, #a78bfa 0%, #8b5cf6 55%, #ec4899 100%);">
                <div class="dash-v3-ring-inner">
                  <span id="dashboard-load-ring-value" class="dash-v3-ring-value">${snapshot.loadPercent.toFixed(0)}<span class="dash-v3-ring-unit">%</span></span>
                  <span class="dash-v3-ring-label">5分钟</span>
                </div>
              </div>
            </div>
            <div class="dash-v3-card-footer">
              <span id="dashboard-load-1">1分钟 ${snapshot.load1.toFixed(2)}</span>
              <span id="dashboard-load-15">15分钟 ${snapshot.load15.toFixed(2)}</span>
            </div>
          </div>

          <div class="dash-v3-card dash-v3-card-network">
            <div class="dash-v3-card-header">
              <span class="dash-v3-card-title">网络状态</span>
              <span id="dashboard-network-connections" class="dash-v3-card-value">${systemInfo.networkConnections}<span class="dash-v3-card-unit"> 连接</span></span>
            </div>
            <div class="dash-v3-card-body">
              <div class="dash-v3-net-stats">
                <div class="dash-v3-net-stat">
                  <span class="dash-v3-net-label">上传速率</span>
                  <span id="dashboard-upload-rate" class="dash-v3-net-val">${this.formatRate(snapshot.uploadRate)}</span>
                </div>
                <div class="dash-v3-net-stat">
                  <span class="dash-v3-net-label">下载速率</span>
                  <span id="dashboard-download-rate" class="dash-v3-net-val">${this.formatRate(snapshot.downloadRate)}</span>
                </div>
                <div class="dash-v3-net-stat">
                  <span class="dash-v3-net-label">响应时间</span>
                  <span id="dashboard-latency-value" class="dash-v3-net-val">${this.formatLatency(snapshot.latencyMs)}</span>
                </div>
              </div>
              <div class="dash-v3-net-chart-box">
                <div class="dash-v3-net-chart-grid"></div>
                <div class="dash-v3-net-charts">
                  <div class="dash-v3-net-chart-item">
                    <div id="dashboard-download-chart" class="dash-v3-net-mini-chart" style="position:relative;">
                      ${this.renderNetMiniChart(this.downloadHistory.slice(-20), '#22c55e', 'KB/s')}
                      <div class="chart-tooltip" style="display:none;position:absolute;background:rgba(0,0,0,0.8);color:white;padding:4px 8px;border-radius:4px;font-size:11px;pointer-events:none;z-index:100;white-space:nowrap;">
                        <div class="tooltip-value"></div>
                        <div class="tooltip-time"></div>
                      </div>
                    </div>
                    <span class="dash-v3-net-chart-label">下载</span>
                  </div>
                  <div class="dash-v3-net-chart-item">
                    <div id="dashboard-upload-chart" class="dash-v3-net-mini-chart" style="position:relative;">
                      ${this.renderNetMiniChart(this.uploadHistory.slice(-20), '#3b82f6', 'KB/s')}
                      <div class="chart-tooltip" style="display:none;position:absolute;background:rgba(0,0,0,0.8);color:white;padding:4px 8px;border-radius:4px;font-size:11px;pointer-events:none;z-index:100;white-space:nowrap;">
                        <div class="tooltip-value"></div>
                        <div class="tooltip-time"></div>
                      </div>
                    </div>
                    <span class="dash-v3-net-chart-label">上传</span>
                  </div>
                  <div class="dash-v3-net-chart-item">
                    <div id="dashboard-latency-chart" class="dash-v3-net-mini-chart" style="position:relative;">
                      ${this.renderNetMiniChart(this.latencyHistory.slice(-20), '#f59e0b', 'ms')}
                      <div class="chart-tooltip" style="display:none;position:absolute;background:rgba(0,0,0,0.8);color:white;padding:4px 8px;border-radius:4px;font-size:11px;pointer-events:none;z-index:100;white-space:nowrap;">
                        <div class="tooltip-value"></div>
                        <div class="tooltip-time"></div>
                      </div>
                    </div>
                    <span class="dash-v3-net-chart-label">响应</span>
                  </div>
                </div>
              </div>
              <div class="dash-v3-net-legend">
                <div class="dash-v3-net-chart-item">
                  <span class="dash-v3-net-legend-dot download"></span>
                  <span class="dash-v3-net-chart-label">下载</span>
                </div>
                <div class="dash-v3-net-chart-item">
                  <span class="dash-v3-net-legend-dot upload"></span>
                  <span class="dash-v3-net-chart-label">上传</span>
                </div>
                <div class="dash-v3-net-chart-item">
                  <span class="dash-v3-net-legend-dot latency"></span>
                  <span class="dash-v3-net-chart-label">响应</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="dash-v3-row dash-v3-row-lines">
          <div class="dash-v3-card dash-v3-card-wide">
            <div class="dash-v3-card-header">
              <span class="dash-v3-card-title">内存使用率</span>
              <span id="dashboard-memory-card-value" class="dash-v3-card-value">${snapshot.memUsage.toFixed(0)}<span class="dash-v3-card-unit">%</span></span>
            </div>
            <div class="dash-v3-card-body dash-v3-chart-body">
              <div class="dash-v3-line-chart-grid" id="chart-memory">
                ${this.renderLineChartWithGrid(this.memoryHistory.slice(-20), '#06b6d4', 'chart-memory')}
              </div>
              <div id="dashboard-memory-usage-strip">${this.renderUsageBlocks(snapshot.memUsage, '#06b6d4')}</div>
            </div>
            <div class="dash-v3-card-footer">
              <span id="dashboard-memory-used">已用 ${systemInfo.memoryUsage.used}</span>
              <span id="dashboard-memory-total">总计 ${systemInfo.memoryUsage.total}</span>
            </div>
          </div>

          <div class="dash-v3-card dash-v3-card-wide">
            <div class="dash-v3-card-header">
              <span class="dash-v3-card-title">磁盘使用率</span>
              <span id="dashboard-disk-trend-card-value" class="dash-v3-card-value">${snapshot.diskUsage.toFixed(0)}<span class="dash-v3-card-unit">%</span></span>
            </div>
            <div class="dash-v3-card-body dash-v3-chart-body">
              <div class="dash-v3-line-chart-grid" id="chart-disk-trend">
                ${this.renderLineChartWithGrid(this.diskHistory.slice(-20), '#ef4444', 'chart-disk-trend')}
              </div>
              <div id="dashboard-disk-usage-strip">${this.renderUsageBlocks(snapshot.diskUsage, '#ef4444')}</div>
            </div>
            <div class="dash-v3-card-footer">
              <span id="dashboard-disk-used">已用 ${systemInfo.diskUsage.used} / ${systemInfo.diskUsage.total}</span>
              <span id="dashboard-disk-free">可用 ${systemInfo.diskUsage.available}</span>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  private renderMiniBarChart(points: number[], color: string): string {
    if (!points.length) return '';
    const barWidth = 4;
    const gap = 2;
    const chartWidth = points.length * (barWidth + gap);
    const height = 20;
    const max = Math.max(...points, 1);
    const bars = points.map((p, i) => {
      const barHeight = Math.max(1, (p / max) * (height - 2));
      const x = i * (barWidth + gap);
      const opacity = 0.3 + (p / max) * 0.7;
      return `<rect x="${x}" y="${height - barHeight}" width="${barWidth}" height="${barHeight}" fill="${color}" opacity="${opacity}" rx="1"/>`;
    }).join('');
    return `<svg viewBox="0 0 ${chartWidth} ${height}" style="width:100%;height:${height}px;"><defs><linearGradient id="bar-grad-${color.replace('#','')}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${color}" stop-opacity="0.9"/><stop offset="100%" stop-color="${color}" stop-opacity="0.3"/></linearGradient></defs>${bars.replace(new RegExp(color, 'g'), `url(#bar-grad-${color.replace('#','')})`)}</svg>`;
  }

  private renderNetMiniChart(points: number[], color: string, unit: string = ''): string {
    if (!points.length) return '';
    const width = 80;
    const height = 24;
    const displayPoints = points.length === 1 ? [points[0], points[0]] : points;
    const min = Math.min(...displayPoints);
    const max = Math.max(...displayPoints);
    const range = Math.max(1, max - min);
    const stepX = width / Math.max(1, displayPoints.length - 1);
    
    const coordArray = displayPoints.map((p, i) => {
      const x = i * stepX;
      const y = height - ((p - min) / range) * (height - 4) - 2;
      return { x, y, value: p };
    });
    
    const coords = coordArray.map(c => `${c.x},${c.y}`);
    const linePath = `M${coords.join(' L')}`;

    const title = unit ? `<title>趋势图 (${unit})</title>` : '<title>趋势图</title>';
    return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="width:100%;height:${height}px;overflow:visible;">${title}<path d="${linePath}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  }

  private renderLineChartWithGrid(points: number[], color: string, chartId: string): string {
    if (!points.length) return '';
    const width = 600;
    const height = 120;
    const padding = 10;
    const chartW = width - padding * 2;
    const chartH = height - padding * 2;

    const displayPoints = points.length === 1 ? [points[0], points[0]] : points;
    const min = 0;
    const max = 100;
    const range = max - min;
    const stepX = chartW / Math.max(1, displayPoints.length - 1);

    const coordArray = displayPoints.map((p, i) => {
      const x = padding + i * stepX;
      const y = padding + chartH - ((p - min) / range) * chartH;
      return { x, y, value: p };
    });

    const coords = coordArray.map(c => `${c.x},${c.y}`);

    const linePath = `M${coords.join(' L')}`;
    const areaPath = `M${coords[0].split(',')[0]},${padding + chartH} L${coords.join(' L')} L${coords[coords.length-1].split(',')[0]},${padding + chartH} Z`;

    const horizontalLines = [0, 25, 50, 75, 100].map(v => {
      const y = padding + chartH - (v / 100) * chartH;
      return `<line x1="${padding}" y1="${y}" x2="${width-padding}" y2="${y}" stroke="rgba(148,163,184,0.18)" stroke-width="1"/>`;
    }).join('');

    const pointCount = displayPoints.length;
    const verticalLines = Array.from({ length: pointCount }, (_, index) => {
      const x = padding + (chartW / Math.max(1, pointCount - 1)) * index;
      return `<line x1="${x}" y1="${padding}" x2="${x}" y2="${height - padding}" stroke="rgba(148,163,184,0.12)" stroke-width="1"/>`;
    }).join('');

    return `
      <div class="dash-v3-line-chart-wrap" id="${chartId}">
        <div class="dash-v3-chart-y-labels">
          ${[100, 75, 50, 25, 0].map(v => `<span style="color: #8898b0;">${v}%</span>`).join('')}
        </div>
        <div class="dash-v3-chart-main">
          <svg viewBox="0 0 ${width} ${height}" style="width:100%;height:100%;" class="line-chart-svg">
            <defs>
              <linearGradient id="area-${color.replace('#','')}" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="${color}" stop-opacity="0.15"/>
                <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
              </linearGradient>
            </defs>
            ${verticalLines}
            ${horizontalLines}
            <path d="${areaPath}" fill="url(#area-${color.replace('#','')})"/>
            <path d="${linePath}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <div class="chart-tooltip" style="display: none; position: absolute; background: rgba(0,0,0,0.8); color: white; padding: 6px 10px; border-radius: 6px; font-size: 12px; pointer-events: none; z-index: 100; white-space: nowrap;">
            <div class="tooltip-value"></div>
            <div class="tooltip-time"></div>
          </div>
        </div>
      </div>
    `;
  }

  private renderUsageBlocks(value: number, color: string): string {
    const clamped = Math.max(0, Math.min(100, value));
    const activeCount = Math.min(20, Math.ceil(clamped / 5));
    const blocks = Array.from({ length: 20 }, (_, index) => {
      const active = index < activeCount;
      return `<span class="dash-v3-usage-block${active ? ' active' : ''}" style="--usage-color: ${color}; --usage-index: ${index};"></span>`;
    }).join('');

    return `<div class="dash-v3-usage-strip" aria-hidden="true">${blocks}</div>`;
  }

  private getLiveSnapshot(systemInfo: SystemInfo): DashboardLiveSnapshot {
    const sampleTime = new Date(systemInfo.lastUpdate).getTime();
    if (this.lastSnapshot && sampleTime === this.lastSnapshotTime) {
      return this.lastSnapshot;
    }

    const cpuUsage = parseFloat(this.getCpuUsage(systemInfo));
    const memUsage = parseFloat(this.getMemoryUsage(systemInfo));
    const diskUsage = parseFloat(this.getDiskUsage(systemInfo));
    const loadAvg = systemInfo.loadAverage || ['0', '0', '0'];
    const load1 = parseFloat(loadAvg[0]) || 0;
    const load5 = parseFloat(loadAvg[1]) || 0;
    const load15 = parseFloat(loadAvg[2]) || 0;
    const cores = systemInfo.cpuInfo.cores || 1;
    const loadPercent = Math.min((load5 / cores) * 100, 100);
    const rxBytes = Number(systemInfo.networkInfo?.rxBytes || 0);
    const txBytes = Number(systemInfo.networkInfo?.txBytes || 0);

    let downloadRate = 0;
    let uploadRate = 0;
    if (this.lastTrafficSample && sampleTime > this.lastTrafficSample.time) {
      const elapsedSeconds = (sampleTime - this.lastTrafficSample.time) / 1000;
      if (elapsedSeconds > 0) {
        downloadRate = Math.max(0, (rxBytes - this.lastTrafficSample.rxBytes) / elapsedSeconds);
        uploadRate = Math.max(0, (txBytes - this.lastTrafficSample.txBytes) / elapsedSeconds);
      }
    }
    this.lastTrafficSample = { time: sampleTime, rxBytes, txBytes };

    const latencyRaw = systemInfo.networkInfo?.latencyMs;
    let latencyMs: number | null = typeof latencyRaw === 'number' && Number.isFinite(latencyRaw) ? latencyRaw : null;
    
    // 如果延迟数据异常，用历史数据或默认值代替
    if (latencyMs === null || latencyMs < 0 || latencyMs > 10000) {
      if (this.latencyHistory.length > 0) {
        // 用最后一个有效数据
        latencyMs = this.latencyHistory[this.latencyHistory.length - 1];
      } else {
        // 默认值
        latencyMs = 0;
      }
    }

    this.pushHistory(this.cpuHistory, cpuUsage);
    this.pushHistory(this.memoryHistory, memUsage);
    this.pushHistory(this.diskHistory, diskUsage);
    this.pushHistory(this.downloadHistory, downloadRate);
    this.pushHistory(this.uploadHistory, uploadRate);
    this.pushHistory(this.latencyHistory, latencyMs);

    const snapshot: DashboardLiveSnapshot = {
      cpuUsage,
      memUsage,
      diskUsage,
      load1,
      load5,
      load15,
      loadPercent,
      downloadRate,
      uploadRate,
      latencyMs
    };
    this.lastSnapshotTime = sampleTime;
    this.lastSnapshot = snapshot;
    return snapshot;
  }

  private pushHistory(history: number[], value: number): void {
    history.push(Number.isFinite(value) ? value : 0);
    while (history.length > DashboardRenderer.HISTORY_MAX) history.shift();
  }

  private formatRate(bytesPerSecond: number): string {
    if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) {
      return '0 B/s';
    }
    const units = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
    let value = bytesPerSecond;
    let index = 0;
    while (value >= 1024 && index < units.length - 1) {
      value /= 1024;
      index += 1;
    }
    const precision = value >= 100 ? 0 : value >= 10 ? 1 : 2;
    return `${value.toFixed(precision)} ${units[index]}`;
  }

  private formatLatency(latencyMs: number | null): string {
    if (latencyMs === null || !Number.isFinite(latencyMs)) {
      return '--';
    }
    return `${latencyMs.toFixed(latencyMs >= 100 ? 0 : 1)} ms`;
  }

  private setText(id: string, value: string): void {
    const el = document.getElementById(id);
    if (el) {
      el.textContent = value;
    }
  }

  private setHtml(id: string, value: string): void {
    const el = document.getElementById(id);
    if (el) {
      el.innerHTML = value;
    }
  }

  private setRingValue(id: string, value: number): void {
    const el = document.getElementById(id);
    if (el) {
      el.style.setProperty('--ring-value', String(Math.max(0, Math.min(100, value))));
    }
  }

  /**
   * 渲染空仪表盘
   */
  private renderEmptyDashboard(): string {
    return `
      <div class="dashboard-empty">
        <div class="empty-state-icon">
          ${this.renderDashboardPanelIcon(48)}
        </div>
        <h3>系统监控仪表盘</h3>
        <p>请先连接到Linux服务器以查看系统监控信息。连接成功后，这里将显示详细的系统状态和性能指标。</p>
        <button class="modern-btn primary" onclick="window.showServerModal()">
          ${LinkOne({ theme: 'outline', size: '16', fill: 'currentColor' })}
          <span>连接服务器</span>
        </button>
      </div>
    `;
  }

  private renderConnectedButNoData(): string {
    return `
      <div class="dashboard-empty">
        <div class="empty-state-icon">
          ${this.renderDashboardPanelIcon(48)}
        </div>
        <h3>已连接服务器，正在加载监控数据</h3>
        <p>连接状态正常，但系统监控信息尚未返回。请点击下方按钮重试加载。</p>
        <button class="modern-btn primary" onclick="window.loadSystemDetailedInfo(true)">
          ${Refresh({ theme: 'outline', size: '16', fill: 'currentColor' })}
          <span>刷新数据</span>
        </button>
      </div>
    `;
  }

  private renderDashboardPanelIcon(size: 24 | 48): string {
    return `
      <img
        class="dashboard-panel-icon dashboard-panel-icon-${size}"
        src="/icons/dashboard-panel.png"
        alt=""
        onload="this.nextElementSibling.classList.add('hidden')"
        onerror="this.classList.add('hidden')"
      />
      <span class="dashboard-panel-icon-fallback">
        ${DashboardIcon({ theme: 'filled', size: String(size), fill: 'currentColor' })}
      </span>
    `;
  }

  /**
   * 格式化时间
   */
  private formatTime(date: Date): string {
    const input = date instanceof Date ? date : new Date(date);
    const year = input.getFullYear();
    const month = String(input.getMonth() + 1).padStart(2, '0');
    const day = String(input.getDate()).padStart(2, '0');
    const hours = String(input.getHours()).padStart(2, '0');
    const minutes = String(input.getMinutes()).padStart(2, '0');
    const seconds = String(input.getSeconds()).padStart(2, '0');
    return `${year}/${month}/${day} ${hours}:${minutes}:${seconds}`;
  }

  /**
   * 获取CPU使用率
   */
  private getCpuUsage(systemInfo: SystemInfo): string {
    const usage = systemInfo.cpuInfo.usage.replace('%', '');
    const value = Number.parseFloat(usage);
    return Number.isFinite(value) ? value.toFixed(1) : '0.0';
  }

  /**
   * 获取内存使用率
   */
  private getMemoryUsage(systemInfo: SystemInfo): string {
    const total = this.parseMemoryValue(systemInfo.memoryUsage.total);
    const used = this.parseMemoryValue(systemInfo.memoryUsage.used);
    if (total <= 0) return '0.0';
    return ((used / total) * 100).toFixed(1);
  }

  /**
   * 获取磁盘使用率
   */
  private getDiskUsage(systemInfo: SystemInfo): string {
    const value = Number.parseFloat(systemInfo.diskUsage.percentage.replace('%', ''));
    return Number.isFinite(value) ? value.toFixed(1) : '0.0';
  }

  /**
   * 解析内存值
   */
  private parseMemoryValue(memStr: string): number {
    const match = memStr.trim().match(/^(\d+(?:\.\d+)?)\s*([KMGT]?B)?$/i);
    if (!match) return 0;
    const value = Number.parseFloat(match[1]);
    const unit = (match[2] || 'MB').toUpperCase();
    if (!Number.isFinite(value)) return 0;
    if (unit === 'KB') return value / 1024;
    if (unit === 'MB') return value;
    if (unit === 'GB') return value * 1024;
    if (unit === 'TB') return value * 1024 * 1024;
    return value;
  }

  /**
   * 检测系统类型并更新概览中的 OS 字段
   */
  private async detectAndShowSystemType(): Promise<void> {
    try {
      const info = await SystemDetector.detectSystem();
      const displayName = info.type === 'unknown' && info.prettyName
        ? info.prettyName
        : SystemDetector.getSystemDisplayName(info.type);
      const systemText = info.version && info.type !== 'unknown'
        ? `${displayName} ${info.version}`
        : displayName;

      this.systemMetaCache = {
        ...(this.systemMetaCache || {
          kernel: '--',
          arch: '--',
          virtualization: '--',
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || '--'
        }),
        os: systemText
      };
      const osEl = document.getElementById('dashboard-os-value');
      if (osEl) {
        osEl.textContent = systemText;
        osEl.setAttribute('title', systemText);
      }
    } catch {
      // ignore
    }
  }

  /**
   * 加载系统元数据
   */
  private async loadSystemMeta(): Promise<void> {
    if (this.systemMetaCache && this.systemMetaCache.kernel !== '--') {
      this.updateSystemMetaToDom(this.systemMetaCache);
      return;
    }

    const app = (window as any).app;
    if (!app?.sshManager?.executeCommand) return;

    try {
      const command = [
        'echo "__KERNEL__$(uname -r 2>/dev/null)"',
        'echo "__ARCH__$(uname -m 2>/dev/null)"',
        'echo "__TZ__$( (timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || date +%Z) | head -n1 )"',
        'echo "__VIRT__$(systemd-detect-virt 2>/dev/null || echo none)"'
      ].join(' && ');

      const raw = await app.sshManager.executeCommand(command);
      const lines = String(raw).split('\n').map((line: string) => line.trim());
      const meta = {
        os: this.systemMetaCache?.os || 'Linux',
        kernel: lines.find((line: string) => line.startsWith('__KERNEL__'))?.replace('__KERNEL__', '') || '--',
        arch: lines.find((line: string) => line.startsWith('__ARCH__'))?.replace('__ARCH__', '') || '--',
        timezone: lines.find((line: string) => line.startsWith('__TZ__'))?.replace('__TZ__', '') || '--',
        virtualization: lines.find((line: string) => line.startsWith('__VIRT__'))?.replace('__VIRT__', '') || '--'
      };
      this.systemMetaCache = meta;
      this.updateSystemMetaToDom(meta);
    } catch {
      // ignore
    }
  }

  /**
   * 更新系统元数据到 DOM
   */
  private updateSystemMetaToDom(meta: { os: string; kernel: string; arch: string; virtualization: string; timezone: string }): void {
    const mapping: Array<{ id: string; value: string }> = [
      { id: 'dashboard-os-value', value: meta.os },
      { id: 'dashboard-kernel-value', value: meta.kernel },
      { id: 'dashboard-arch-value', value: meta.arch },
      { id: 'dashboard-virt-value', value: meta.virtualization },
      { id: 'dashboard-timezone-value', value: meta.timezone }
    ];

    mapping.forEach(item => {
      const el = document.getElementById(item.id);
      if (!el) return;
      el.textContent = item.value;
      el.setAttribute('title', item.value);
    });
  }

  updateMetricCards(systemInfo: SystemInfo): void {
    const snapshot = this.getLiveSnapshot(systemInfo);
    const loadAvg = systemInfo.loadAverage || ['0', '0', '0'];

    this.setText('dashboard-last-update', `最后更新: ${this.formatTime(systemInfo.lastUpdate)}`);
    this.setText('dashboard-hostname-value', systemInfo.hostname);
    this.setText('dashboard-memory-total-value', systemInfo.memoryUsage.total);
    this.setText('dashboard-cpu-model-value', systemInfo.cpuInfo.model);
    this.setText('dashboard-disk-total-value', systemInfo.diskUsage.total);
    this.setText('dashboard-cpu-cores-value', String(systemInfo.cpuInfo.cores));
    this.setText('dashboard-uptime-value', systemInfo.uptime);

    this.setHtml('dashboard-cpu-card-value', `${snapshot.cpuUsage.toFixed(0)}<span class="dash-v3-card-unit">%</span>`);
    this.setHtml('dashboard-cpu-ring-value', `${snapshot.cpuUsage.toFixed(0)}<span class="dash-v3-ring-unit">%</span>`);
    this.setRingValue('dashboard-cpu-ring', snapshot.cpuUsage);
    this.setHtml('dashboard-cpu-mini-bars', this.renderMiniBarChart(this.cpuHistory.slice(-10), '#3b82f6'));

    this.setText('dashboard-disk-card-value', `${systemInfo.diskUsage.used} / ${systemInfo.diskUsage.total}`);
    this.setHtml('dashboard-disk-ring-value', `${snapshot.diskUsage.toFixed(0)}<span class="dash-v3-ring-unit">%</span>`);
    this.setRingValue('dashboard-disk-ring', snapshot.diskUsage);
    this.setText('dashboard-disk-available', `可用 ${systemInfo.diskUsage.available}`);
    this.setText('dashboard-partition-count', `${systemInfo.partitions.length} 分区`);

    this.setText('dashboard-load-card-value', loadAvg.slice(0, 3).join(' / '));
    this.setHtml('dashboard-load-ring-value', `${snapshot.loadPercent.toFixed(0)}<span class="dash-v3-ring-unit">%</span>`);
    this.setRingValue('dashboard-load-ring', snapshot.loadPercent);
    this.setText('dashboard-load-1', `1分钟 ${snapshot.load1.toFixed(2)}`);
    this.setText('dashboard-load-15', `15分钟 ${snapshot.load15.toFixed(2)}`);

    this.setHtml('dashboard-network-connections', `${systemInfo.networkConnections}<span class="dash-v3-card-unit"> 连接</span>`);
    this.setText('dashboard-upload-rate', this.formatRate(snapshot.uploadRate));
    this.setText('dashboard-download-rate', this.formatRate(snapshot.downloadRate));
    this.setText('dashboard-latency-value', this.formatLatency(snapshot.latencyMs));
    this.setHtml('dashboard-download-chart', `<div style="position:relative;">${this.renderNetMiniChart(this.downloadHistory.slice(-20), '#22c55e', 'KB/s')}<div class="chart-tooltip" style="display:none;position:absolute;background:rgba(0,0,0,0.8);color:white;padding:4px 8px;border-radius:4px;font-size:11px;pointer-events:none;z-index:100;white-space:nowrap;"><div class="tooltip-value"></div><div class="tooltip-time"></div></div></div>`);
    this.setHtml('dashboard-upload-chart', `<div style="position:relative;">${this.renderNetMiniChart(this.uploadHistory.slice(-20), '#3b82f6', 'KB/s')}<div class="chart-tooltip" style="display:none;position:absolute;background:rgba(0,0,0,0.8);color:white;padding:4px 8px;border-radius:4px;font-size:11px;pointer-events:none;z-index:100;white-space:nowrap;"><div class="tooltip-value"></div><div class="tooltip-time"></div></div></div>`);
    this.setHtml('dashboard-latency-chart', `<div style="position:relative;">${this.renderNetMiniChart(this.latencyHistory.slice(-20), '#f59e0b', 'ms')}<div class="chart-tooltip" style="display:none;position:absolute;background:rgba(0,0,0,0.8);color:white;padding:4px 8px;border-radius:4px;font-size:11px;pointer-events:none;z-index:100;white-space:nowrap;"><div class="tooltip-value"></div><div class="tooltip-time"></div></div></div>`);

    this.setHtml('dashboard-memory-card-value', `${snapshot.memUsage.toFixed(0)}<span class="dash-v3-card-unit">%</span>`);
    this.setHtml('dashboard-memory-used', `已用 ${systemInfo.memoryUsage.used}`);
    this.setHtml('dashboard-memory-total', `总计 ${systemInfo.memoryUsage.total}`);
    this.setHtml('dashboard-memory-usage-strip', this.renderUsageBlocks(snapshot.memUsage, '#06b6d4'));

    const memEl = document.querySelector('#chart-memory');
    if (memEl) {
      memEl.innerHTML = this.renderLineChartWithGrid(this.memoryHistory.slice(-20), '#06b6d4', 'chart-memory');
    }

    this.setHtml('dashboard-disk-trend-card-value', `${snapshot.diskUsage.toFixed(0)}<span class="dash-v3-card-unit">%</span>`);
    this.setHtml('dashboard-disk-used', `已用 ${systemInfo.diskUsage.used} / ${systemInfo.diskUsage.total}`);
    this.setHtml('dashboard-disk-free', `可用 ${systemInfo.diskUsage.available}`);
    this.setHtml('dashboard-disk-usage-strip', this.renderUsageBlocks(snapshot.diskUsage, '#ef4444'));

    const diskEl = document.querySelector('#chart-disk-trend');
    if (diskEl) {
      diskEl.innerHTML = this.renderLineChartWithGrid(this.diskHistory.slice(-20), '#ef4444', 'chart-disk-trend');
    }
  }

  initCharts(_force: boolean = false): void {
    this.initChartTooltips();
  }

  private initChartTooltips(): void {
    setTimeout(() => {
      document.querySelectorAll('.chart-data-point').forEach(point => {
        const el = point as HTMLElement;
        el.style.transition = 'r 0.2s ease';
        
        el.addEventListener('mouseenter', (e) => {
          el.setAttribute('r', '6');
          const value = el.dataset.value;
          const time = el.dataset.time;
          this.showTooltip(e, value, time);
        });
        
        el.addEventListener('mouseleave', () => {
          el.setAttribute('r', '4');
          this.hideTooltip();
        });
        
        el.addEventListener('mousemove', (e) => {
          this.updateTooltipPosition(e);
        });
      });
      
      document.querySelectorAll('.net-chart-point').forEach(point => {
        const el = point as HTMLElement;
        el.style.transition = 'r 0.2s ease';
        
        el.addEventListener('mouseenter', (e) => {
          el.setAttribute('r', '4');
          const value = el.dataset.value;
          const unit = el.dataset.unit || '';
          const time = el.dataset.time;
          this.showTooltip(e, value, time, unit);
        });
        
        el.addEventListener('mouseleave', () => {
          el.setAttribute('r', '2');
          this.hideTooltip();
        });
        
        el.addEventListener('mousemove', (e) => {
          this.updateTooltipPosition(e);
        });
      });
    }, 100);
  }

  private showTooltip(e: MouseEvent, value: string | undefined, time: string | undefined, unit: string = '%'): void {
    const chartMain = (e.target as HTMLElement).closest('.dash-v3-chart-main');
    const netChartItem = (e.target as HTMLElement).closest('.dash-v3-net-chart-item');
    const tooltip = (chartMain?.querySelector('.chart-tooltip') || netChartItem?.querySelector('.chart-tooltip')) as HTMLElement;
    if (!tooltip) return;
    
    const valueEl = tooltip.querySelector('.tooltip-value');
    const timeEl = tooltip.querySelector('.tooltip-time');
    if (valueEl) valueEl.textContent = `值: ${value}${unit}`;
    if (timeEl) timeEl.textContent = `时间: ${time}`;
    
    tooltip.style.display = 'block';
    this.updateTooltipPosition(e);
  }

  private updateTooltipPosition(e: MouseEvent): void {
    const targetEl = e.target as HTMLElement;
    const chartMain = targetEl.closest('.dash-v3-chart-main');
    const netChartContainer = targetEl.closest('#dashboard-download-chart, #dashboard-upload-chart, #dashboard-latency-chart');
    
    let tooltip: HTMLElement | null = null;
    let containerRect: DOMRect | null = null;
    
    if (chartMain) {
      tooltip = chartMain.querySelector('.chart-tooltip') as HTMLElement;
      containerRect = chartMain.getBoundingClientRect();
    } else if (netChartContainer) {
      tooltip = netChartContainer.querySelector('.chart-tooltip') as HTMLElement;
      containerRect = netChartContainer.getBoundingClientRect();
    }
    
    if (!tooltip || !containerRect) return;
    
    tooltip.style.left = `${e.clientX - containerRect.left + 10}px`;
    tooltip.style.top = `${e.clientY - containerRect.top - 40}px`;
  }

  private hideTooltip(): void {
    document.querySelectorAll('.chart-tooltip').forEach(tooltip => {
      (tooltip as HTMLElement).style.display = 'none';
    });
  }

}

// Declare ApexCharts global
declare var ApexCharts: any;
