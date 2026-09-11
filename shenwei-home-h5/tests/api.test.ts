/** T1: API 层 — Bearer 注入 / 401 处理 / 各端点请求形状。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, AuthError } from '../src/api';

const mockedFetch = vi.fn();

beforeEach(() => {
  vi.stubGlobal('fetch', mockedFetch);
  vi.stubGlobal('location', new URL('https://xdf.nonoai.com.cn/h5/'));
  sessionStorage.setItem('shm_token', 'tok123');
  mockedFetch.mockReset();
});

afterEach(() => vi.unstubAllGlobals());

describe('api', () => {
  it('send 携带 Bearer 与 JSON body，返回解析后数据', async () => {
    mockedFetch.mockResolvedValueOnce(new Response(
      JSON.stringify({ id: 'm1', status: 'accepted', created_at: 1 }),
      { status: 200 }));
    const res = await api.send('你好');
    const [url, init] = mockedFetch.mock.calls[0];
    expect(url).toBe('/api/messages/send');
    expect(init.headers.Authorization).toBe('Bearer tok123');
    expect(JSON.parse(init.body)).toEqual({ content: '你好' });
    expect(res.status).toBe('accepted');
  });

  it('401 → 抛 AuthError 并清除 sessionStorage', async () => {
    mockedFetch.mockResolvedValueOnce(new Response('{"detail":"invalid_token"}', { status: 401 }));
    await expect(api.list('')).rejects.toThrow(AuthError);
    expect(sessionStorage.getItem('shm_token')).toBeNull();
  });

  it('list 拼接 cursor 与 limit', async () => {
    mockedFetch.mockResolvedValueOnce(new Response('{"items":[],"next_cursor":"","has_more":false}', { status: 200 }));
    await api.list('c1', 20);
    expect(mockedFetch.mock.calls[0][0]).toBe('/api/messages/list?cursor=c1&limit=20');
  });

  it('poll 拼接 since', async () => {
    mockedFetch.mockResolvedValueOnce(new Response('{"items":[],"next_since":0,"has_more":false}', { status: 200 }));
    await api.poll(123);
    expect(mockedFetch.mock.calls[0][0]).toBe('/api/messages/poll?since=123&limit=20');
  });

  it('transfer POST 到正确端点', async () => {
    mockedFetch.mockResolvedValueOnce(new Response('{"status":"accepted"}', { status: 200 }));
    await api.transfer();
    expect(mockedFetch.mock.calls[0][0]).toBe('/api/messages/transfer');
  });

  it('image 上传用 FormData（不设 Content-Type，浏览器自动带 boundary）', async () => {
    mockedFetch.mockResolvedValueOnce(new Response(
      JSON.stringify({ id: 'i1', msg_type: 'image', image_url: 'https://x/api/media/a.png', status: 'accepted', created_at: 1 }),
      { status: 200 }));
    const blob = new Blob([new Uint8Array([1])], { type: 'image/png' });
    await api.uploadImage(blob);
    const [url, init] = mockedFetch.mock.calls[0];
    expect(url).toBe('/api/messages/image');
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.headers.Authorization).toBe('Bearer tok123');
  });
});
