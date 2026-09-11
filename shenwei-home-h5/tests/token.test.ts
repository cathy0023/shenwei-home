/** T1: token 工具 — query 优先 / sessionStorage 兜底 / replaceState 清除 / 401 清理。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { resolveToken, clearToken } from '../src/utils/token';

describe('resolveToken', () => {
  beforeEach(() => sessionStorage.clear());

  it('query 优先：URL 有 token 时返回并写入 sessionStorage', () => {
    vi.stubGlobal('location', new URL('https://xdf.nonoai.com.cn/h5/?token=abc123'));
    vi.stubGlobal('history', { replaceState: vi.fn() });  // jsdom origin 限制，stub 掉
    const t = resolveToken();
    expect(t).toBe('abc123');
    expect(sessionStorage.getItem('shm_token')).toBe('abc123');
  });

  it('无 query 时回读 sessionStorage（刷新/重载恢复）', () => {
    vi.stubGlobal('location', new URL('https://xdf.nonoai.com.cn/h5/'));
    sessionStorage.setItem('shm_token', 'stored456');
    expect(resolveToken()).toBe('stored456');
  });

  it('token 解析后清除 URL query（replaceState）', () => {
    const replaceSpy = vi.fn();
    vi.stubGlobal('location', new URL('https://xdf.nonoai.com.cn/h5/?token=xyz'));
    vi.stubGlobal('history', { replaceState: replaceSpy });
    resolveToken();
    expect(replaceSpy).toHaveBeenCalled();
  });

  it('两者皆无 → 返回 null', () => {
    vi.stubGlobal('location', new URL('https://xdf.nonoai.com.cn/h5/'));
    expect(resolveToken()).toBeNull();
  });
});

describe('clearToken', () => {
  it('清除 sessionStorage 中的 token', () => {
    sessionStorage.setItem('shm_token', 'gone');
    clearToken();
    expect(sessionStorage.getItem('shm_token')).toBeNull();
  });
});
