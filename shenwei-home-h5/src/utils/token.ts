/** token 生命周期：query 优先 → sessionStorage 兜底 → replaceState 清 URL。

spec: docs/rfcs/approved/SHM-002-chat-h5-webview.md §3.3
*/
const TOKEN_KEY = 'shm_token';

/** 读 token：URL query 优先（新进入），无则回读 sessionStorage（刷新/重载恢复）。
 *  解析到 query token 时写入 sessionStorage 并用 replaceState 清除 URL 中的 token。 */
export function resolveToken(): string | null {
  const url = new URL(window.location.href);
  const fromQuery = url.searchParams.get('token');

  if (fromQuery) {
    sessionStorage.setItem(TOKEN_KEY, fromQuery);
    // 清除 URL 中的 token（不产生历史记录、不触发刷新）
    url.searchParams.delete('token');
    window.history.replaceState(null, '', url.toString());
    return fromQuery;
  }

  return sessionStorage.getItem(TOKEN_KEY);
}

/** token 失效（401）时清理本地凭证。 */
export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}
