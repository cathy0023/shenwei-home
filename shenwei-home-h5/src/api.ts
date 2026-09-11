/** 后端 API 封装：统一 Bearer 注入、401 → AuthError + 清凭证。

契约与小程序端 utils/api.js 完全一致（后端零改动）。
*/
import { clearToken } from './utils/token';

export class AuthError extends Error {
  constructor() {
    super('登录已过期，请返回小程序重新进入');
    this.name = 'AuthError';
  }
}

function headersWithToken(hasBody: boolean): Record<string, string> {
  const token = sessionStorage.getItem('shm_token') ?? '';
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (hasBody) headers['Content-Type'] = 'application/json';
  return headers;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(path, { ...init, headers: { ...headersWithToken(!!init.body), ...init.headers } });
  if (resp.status === 401) {
    clearToken();
    throw new AuthError();
  }
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
  }
  return resp.json() as Promise<T>;
}

export interface SendResult { id: string; status: string; created_at: number }
export interface MessageItem {
  id: string;
  role: 'user' | 'assistant' | 'system';
  kind?: string;
  msg_type: string;
  content: { content?: string; image_url?: string; media_url?: string; event_type?: string };
  status?: string;
  created_at: number;
}
export interface ListResult { items: MessageItem[]; next_cursor: string; has_more: boolean }
export interface PollResult { items: MessageItem[]; next_since: number; has_more: boolean }
export interface ImageResult { id: string; msg_type: 'image'; image_url: string; status: string; created_at: number }

export const api = {
  send: (content: string) =>
    request<SendResult>('/api/messages/send', { method: 'POST', body: JSON.stringify({ content }) }),

  list: (cursor = '', limit = 20) =>
    request<ListResult>(`/api/messages/list?cursor=${encodeURIComponent(cursor)}&limit=${limit}`),

  poll: (since = 0, limit = 20) =>
    request<PollResult>(`/api/messages/poll?since=${since}&limit=${limit}`),

  transfer: () =>
    request<{ status: string; tip_id: string }>('/api/messages/transfer', { method: 'POST', body: '{}' }),

  uploadImage: (blob: Blob) => {
    const fd = new FormData();
    fd.append('file', blob, 'image.png');
    return request<ImageResult>('/api/messages/image', { method: 'POST', body: fd });
  },
};
