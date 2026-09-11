/** T3: 核心交互纯逻辑 — 轮询退避 / 乐观回显对账。 */
import { describe, expect, it } from 'vitest';
import { nextPollInterval, POLL_FAST_MS, POLL_SLOW_MS, reconcileTemps } from '../src/utils/poll';

describe('nextPollInterval', () => {
  it('有新消息 → 重置为 3s 快速', () => {
    expect(nextPollInterval(10000, true)).toBe(POLL_FAST_MS);
  });
  it('空轮询 → +1s', () => {
    expect(nextPollInterval(3000, false)).toBe(4000);
  });
  it('空闲封顶 10s', () => {
    expect(nextPollInterval(10000, false)).toBe(POLL_SLOW_MS);
  });
});

describe('reconcileTemps', () => {
  const mk = (id: string, role: string, content: string) => ({
    id, role, msg_type: 'text', content: { content },
  });

  it('服务器消息到达后移除同内容 temp', () => {
    const items = [
      mk('temp-1', 'user', '你好'),
      mk('srv-1', 'user', '你好'),
      mk('srv-2', 'assistant', '回复'),
    ];
    const { keep, removeTempIds } = reconcileTemps(items);
    expect(removeTempIds).toEqual(new Set(['temp-1']));
    expect(keep.map((i) => i.id)).toEqual(['srv-1', 'srv-2']);
  });

  it('无匹配服务器消息时 temp 保留（发送中）', () => {
    const items = [mk('temp-2', 'user', '还在发')];
    const { keep, removeTempIds } = reconcileTemps(items);
    expect(removeTempIds.size).toBe(0);
    expect(keep).toHaveLength(1);
  });

  it('图片消息按 msg_type 区分不误删', () => {
    const items = [
      { id: 'temp-3', role: 'user', msg_type: 'image', content: {} },
    ];
    const { removeTempIds } = reconcileTemps(items);
    expect(removeTempIds.size).toBe(0);
  });
});
