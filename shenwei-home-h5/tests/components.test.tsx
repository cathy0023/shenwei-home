/** T2: UI 组件 — 消息流三态渲染 / 金标 / 图片节点 / 输入栏 / hero。 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageList } from '../src/components/MessageList';
import { Hero } from '../src/components/Hero';
import type { MessageItem } from '../src/api';

const base: MessageItem = {
  id: 'm1', role: 'user', msg_type: 'text',
  content: { content: '你好' }, status: 'accepted', created_at: 1,
};

describe('MessageList', () => {
  it('user 消息渲染文本，无头像', () => {
    render(<MessageList items={[base]} />);
    expect(screen.getByText('你好')).toBeTruthy();
    expect(document.querySelector('.human-corner-tag')).toBeNull();
  });

  it('assistant 文本消息渲染头像+文本', () => {
    render(<MessageList items={[{ ...base, id: 'm2', role: 'assistant', content: { content: '回复' } }]} />);
    expect(screen.getByText('回复')).toBeTruthy();
  });

  it('boss_reply 渲染「人工」金标 + human 头像徽章', () => {
    render(<MessageList items={[{
      ...base, id: 'm3', role: 'assistant', kind: 'boss_reply',
      content: { content: '人工回复' },
    }]} />);
    expect(screen.getByText('人工')).toBeTruthy();
    expect(document.querySelector('.human-mini')).toBeTruthy();
    expect(document.querySelector('.bot-mini')).toBeNull();
  });

  it('ai_reply 无金标，机器人头像', () => {
    render(<MessageList items={[{
      ...base, id: 'm4', role: 'assistant', kind: 'ai_reply',
      content: { content: 'AI 回复' },
    }]} />);
    expect(document.querySelector('.human-corner-tag')).toBeNull();
    expect(document.querySelector('.bot-mini')).toBeTruthy();
  });

  it('image 消息渲染 <img>，非文本', () => {
    render(<MessageList items={[{
      ...base, id: 'm5', role: 'user', msg_type: 'image',
      content: { image_url: 'https://x/api/media/a.png' },
    }]} />);
    const img = document.querySelector('img.pic') as HTMLImageElement;
    expect(img).toBeTruthy();
    expect(img.getAttribute('src')).toBe('https://x/api/media/a.png');
  });

  it('image 加载失败（picBroken）→ 占位卡片', () => {
    const broken = { ...base, id: 'm6', role: 'user' as const, msg_type: 'image',
      content: { image_url: 'https://x/b.png' }, picBroken: true };
    render(<MessageList items={[broken]} />);
    expect(document.querySelector('img.pic')).toBeNull();
    expect(document.querySelector('.pic-fallback')).toBeTruthy();
  });

  it('system 消息渲染提示条', () => {
    render(<MessageList items={[{
      ...base, id: 'm7', role: 'system', msg_type: 'event',
      content: { content: '已为您转接人工客服' },
    }]} />);
    expect(screen.getByText(/已为您转接人工客服/)).toBeTruthy();
  });
});

describe('Hero', () => {
  it('渲染 Hello + 副标题 + CSS 机器人（无 img 标签）', () => {
    render(<Hero />);
    expect(screen.getByText('Hello :)')).toBeTruthy();
    expect(screen.getByText(/咨询小助手/)).toBeTruthy();
    expect(document.querySelector('.mascot-css')).toBeTruthy();
    expect(document.querySelector('img')).toBeNull();
  });
});
