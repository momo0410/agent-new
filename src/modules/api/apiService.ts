/**
 * API 服务
 * 负责与后端 API 通信
 */

import { API_CONFIG } from '../../config/api.config';

// API 响应接口
export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
  timestamp: number;
}

// 用户信息接口（与后端对应）
export interface ApiUser {
  id: string;
  username: string;
  nickname?: string;
  email: string;
  qq_id?: string;
  is_vip: boolean;
  vip_expire_date?: string;
  vip_days: number;
  max_devices: number;
  device_rebind_count: number;
  max_rebind_count: number;
  status: string;
  email_verified: boolean;
  created_at: string;
  updated_at: string;
  last_login_at?: string;
}

// Token 信息接口
export interface TokenInfo {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

// 登录响应
export interface LoginResponse {
  user: ApiUser;
  token: TokenInfo;
}

// 注册请求
export interface RegisterRequest {
  username: string;
  nickname?: string;
  email: string;
  password: string;
  qq_id?: string;
}

// 登录请求
export interface LoginRequest {
  username: string;
  password: string;
}

/**
 * API 服务类
 */
export class ApiService {
  private static instance: ApiService;
  private accessToken: string | null = null;
  private refreshToken: string | null = null;

  private constructor() {
    this.loadTokensFromStorage();
  }

  /**
   * 获取单例实例
   */
  public static getInstance(): ApiService {
    if (!ApiService.instance) {
      ApiService.instance = new ApiService();
    }
    return ApiService.instance;
  }

  /**
   * 从本地存储加载 Token
   */
  private loadTokensFromStorage(): void {
    try {
      this.accessToken = localStorage.getItem('LERT-access-token');
      this.refreshToken = localStorage.getItem('LERT-refresh-token');
    } catch (error) {
      console.error('加载 Token 失败:', error);
    }
  }

  /**
   * 保存 Token 到本地存储
   */
  private saveTokensToStorage(accessToken: string, refreshToken: string): void {
    try {
      this.accessToken = accessToken;
      this.refreshToken = refreshToken;
      localStorage.setItem('LERT-access-token', accessToken);
      localStorage.setItem('LERT-refresh-token', refreshToken);
    } catch (error) {
      console.error('保存 Token 失败:', error);
    }
  }

  /**
   * 清除 Token
   */
  private clearTokens(): void {
    this.accessToken = null;
    this.refreshToken = null;
    localStorage.removeItem('LERT-access-token');
    localStorage.removeItem('LERT-refresh-token');
  }

  /**
   * 发送 HTTP 请求
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    const url = `${API_CONFIG.baseURL}${endpoint}`;

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    // 如果有 access token，添加到请求头
    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      const data = await response.json();

      if (!response.ok) {
        // 如果是 401 错误且不是登录/注册/刷新请求，尝试刷新 token
        if (response.status === 401 && !endpoint.includes('/auth/')) {
          console.log('Token 可能已过期，尝试刷新...');
          const refreshed = await this.tryRefreshToken();
          if (refreshed) {
            console.log('Token 刷新成功，重试请求...');
            headers['Authorization'] = `Bearer ${this.accessToken}`;
            
            const retryResponse = await fetch(url, {
              ...options,
              headers,
            });
            const retryData = await retryResponse.json();

            if (!retryResponse.ok) {
              throw new Error(retryData.message || `HTTP ${retryResponse.status}`);
            }
            return retryData;
          } else {
            console.error('Token 刷新失败');
          }
        }
        throw new Error(data.message || `HTTP ${response.status}`);
      }

      return data;
    } catch (error) {
      console.error('API 请求失败:', error);
      throw error;
    }
  }

  /**
   * 尝试刷新 Token
   */
  private async tryRefreshToken(): Promise<boolean> {
    if (!this.refreshToken) {
      console.error('没有 Refresh Token');
      return false;
    }

    try {
      const response = await fetch(`${API_CONFIG.baseURL}/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          refresh_token: this.refreshToken,
        }),
      });

      if (!response.ok) {
        return false;
      }

      const data = await response.json() as ApiResponse<{ token: TokenInfo }>;

      if (data.code !== 200) {
        return false;
      }

      this.saveTokensToStorage(
        data.data.token.access_token,
        data.data.token.refresh_token
      );

      console.log('Token 刷新成功');
      return true;
    } catch (error) {
      console.error('Token 刷新失败:', error);
      return false;
    }
  }

  /**
   * 用户注册
   */
  async register(data: RegisterRequest): Promise<ApiResponse<{ token: TokenInfo }>> {
    return this.request('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /**
   * 用户登录
   */
  async login(data: LoginRequest): Promise<ApiResponse<LoginResponse>> {
    const response = await this.request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    });

    // 保存 Token
    this.saveTokensToStorage(
      response.data.token.access_token,
      response.data.token.refresh_token
    );

    return response;
  }

  /**
   * 用户登出
   */
  async logout(): Promise<void> {
    try {
      await this.request('/auth/logout', {
        method: 'POST',
      });
    } catch (error) {
      console.error('登出失败:', error);
    } finally {
      this.clearTokens();
    }
  }

  /**
   * 刷新 Access Token
   */
  async refreshAccessToken(): Promise<TokenInfo> {
    if (!this.refreshToken) {
      throw new Error('没有有效的刷新令牌');
    }

    const response = await this.request<{ token: TokenInfo }>('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({
        refresh_token: this.refreshToken,
      }),
    });

    if (response.code !== 200) {
      throw new Error(response.message);
    }

    this.saveTokensToStorage(
      response.data.token.access_token,
      response.data.token.refresh_token
    );

    return response.data.token;
  }

  /**
   * 获取当前用户信息
   */
  async getCurrentUser(): Promise<ApiResponse<ApiUser>> {
    return this.request<ApiUser>('/users/me', {
      method: 'GET',
    });
  }

  /**
   * 更新用户信息
   */
  async updateUserInfo(data: Partial<Pick<ApiUser, 'nickname' | 'email' | 'qq_id'>>): Promise<ApiResponse<ApiUser>> {
    return this.request<ApiUser>('/users/me', {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  /**
   * 修改密码
   */
  async changePassword(data: { old_password: string; new_password: string }): Promise<ApiResponse<void>> {
    return this.request('/users/me/password', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /**
   * 获取设备列表
   */
  async getDevices(): Promise<ApiResponse<any[]>> {
    return this.request<any[]>('/devices', {
      method: 'GET',
    });
  }

  /**
   * 绑定设备
   */
  async bindDevice(data: { device_name: string; device_id: string }): Promise<ApiResponse<any>> {
    return this.request('/devices', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  /**
   * 解绑设备
   */
  async unbindDevice(deviceId: string): Promise<ApiResponse<void>> {
    return this.request(`/devices/${deviceId}`, {
      method: 'DELETE',
    });
  }

  /**
   * 检查是否有有效的 Token
   */
  hasToken(): boolean {
    return !!this.accessToken;
  }

  /**
   * 获取 Access Token（用于其他服务）
   */
  getAccessToken(): string | null {
    return this.accessToken;
  }
}

export const apiService = ApiService.getInstance();
