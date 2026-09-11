/** 轮询节奏状态机（对齐原生页 chat.js 策略）：
 *  有新消息 → 3s 快速轮询；空轮询 → 每次空闲 +1s，10s 封顶。 */

export const POLL_FAST_MS = 3000;
export const POLL_SLOW_MS = 10000;

/** 计算下一次轮询间隔。 */
export function nextPollInterval(current: number, gotNew: boolean): number {
  return gotNew ? POLL_FAST_MS : Math.min(current + 1000, POLL_SLOW_MS);
}

/** 乐观回显消息与服务器消息对账：返回应保留/移除的 temp 集合。
 *  规则：服务器消息出现后，同内容同角色的 temp 气泡即被替代（保留服务器 id 那份）。 */
export function reconcileTemps<T extends { id: string; role: string; msg_type: string; content: { content?: string } }>(
  items: T[],
  tempPrefix = 'temp-',
): { keep: T[]; removeTempIds: Set<string> } {
  const removeTempIds = new Set<string>();
  const serverKeys = new Set(
    items.filter((i) => !i.id.startsWith(tempPrefix))
      .map((i) => `${i.role}:${i.msg_type}:${i.content.content ?? ''}`));
  for (const item of items) {
    if (item.id.startsWith(tempPrefix)
        && serverKeys.has(`${item.role}:${item.msg_type}:${item.content.content ?? ''}`)) {
      removeTempIds.add(item.id);
    }
  }
  return { keep: items.filter((i) => !removeTempIds.has(i.id)), removeTempIds };
}
