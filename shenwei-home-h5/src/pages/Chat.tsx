/** 聊天页主体：消息流 + 轮询 + 输入（文字/表情/图片）+ 转人工。
 *  功能基准：shenwei-home-mini/pages/chat/chat.js（对齐原生页最终形态）。 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { AuthError, api } from '../api';
import { nextPollInterval, POLL_FAST_MS, reconcileTemps } from '../utils/poll';
import { resolveToken } from '../utils/token';
import { MessageList, type MsgVM } from '../components/MessageList';
import { Hero } from '../components/Hero';
import { ErrorState } from '../components/ErrorState';

const EMOJIS = ['😀','😁','🤣','😊','😍','🤔','😅','😭','😤','😱','🥳','😴',
  '🤝','👍','👏','🙏','💪','🔥','✨','💝','🎉','🌹','☕','🎁',
  '📞','💬','📮','⚠️','✅','❌','⭐','🌙'];

type Phase = 'init' | 'ready' | 'auth-failed';

export function Chat() {
  const [phase, setPhase] = useState<Phase>('init');
  const [messages, setMessages] = useState<MsgVM[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [inputText, setInputText] = useState('');
  const [showEmoji, setShowEmoji] = useState(false);
  const [sending, setSending] = useState(false);
  const [transferred, setTransferred] = useState(false);
  const [loadingEarlier, setLoadingEarlier] = useState(false);

  const tokenRef = useRef<string | null>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollInterval = useRef(POLL_FAST_MS);
  const lastSince = useRef(0);
  const scrollAnchor = useRef<HTMLDivElement>(null);

  const scrollBottom = useCallback(() => {
    requestAnimationFrame(() => scrollAnchor.current?.scrollIntoView({ behavior: 'smooth' }));
  }, []);

  /** 统一入口：token 就绪后设置 phase 并装载。 */
  const initWithToken = useCallback(async (token: string) => {
    tokenRef.current = token;
    try {
      const res = await api.list('', 20);
      // list DESC（最新在前）→ 反转 ASC 渲染；游标从最新历史初始化防重放
      setMessages(res.items.map(toVM).reverse());
      if (res.items.length) {
        lastSince.current = Math.max(...res.items.map((i) => i.created_at));
      }
      setPhase('ready');
      fetchSuggestions();
      startPolling();
    } catch (err) {
      if (err instanceof AuthError) setPhase('auth-failed');
      else setPhase('ready'); // 非鉴权错误仍进入（历史可空）
    }
  }, []);

  // 首帧：解析 token（query 优先/storage 兜底）
  useEffect(() => {
    const token = resolveToken();
    if (token) void initWithToken(token);
    else setPhase('auth-failed');
  }, [initWithToken]);

  // ---------- 轮询 ----------
  const pollOnce = useCallback(async () => {
    if (!tokenRef.current) return;
    try {
      const res = await api.poll(lastSince.current);
      if (res.items.length) {
        setMessages((prev) => {
          const known = new Set(prev.map((m) => m.id));
          const fresh = res.items.filter((i) => !known.has(i.id)).map(toVM);
          const merged = [...prev, ...fresh];
          const { keep } = reconcileTemps(merged); // 服务器消息替代同内容 temp
          return keep;
        });
        lastSince.current = res.next_since;
        pollInterval.current = nextPollInterval(pollInterval.current, true);
        scrollBottom();
      } else {
        pollInterval.current = nextPollInterval(pollInterval.current, false);
      }
    } catch (err) {
      if (err instanceof AuthError) {
        setPhase('auth-failed');
        stopPolling();
      }
    }
  }, [scrollBottom]);

  const startPolling = useCallback(() => {
    stopPolling();
    pollTimer.current = setTimeout(async () => {
      await pollOnce();
      startPolling();
    }, pollInterval.current);
  }, [pollOnce]);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) { clearTimeout(pollTimer.current); pollTimer.current = null; }
  }, []);

  // visibilitychange：暂停/恢复（恢复时立即拉一次）
  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState === 'hidden') stopPolling();
      else if (phase === 'ready') { void pollOnce(); startPolling(); }
    };
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, [phase, pollOnce, startPolling, stopPolling]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const fetchSuggestions = useCallback(async () => {
    try {
      const res = await fetch('/api/suggestions').then((r) => r.json());
      setSuggestions(res.items ?? []);
    } catch { /* 非关键路径 */ }
  }, []);

  // ---------- 发送 ----------
  const sendText = useCallback(async (text: string) => {
    const tempId = `temp-${Date.now()}`;
    setMessages((prev) => [...prev, {
      id: tempId, role: 'user', msg_type: 'text',
      content: { content: text }, status: 'pending', created_at: Date.now(),
    }]);
    scrollBottom();
    try {
      const res = await api.send(text);
      setMessages((prev) => prev.map((m) => (m.id === tempId ? { ...m, status: res.status } : m)));
      pollInterval.current = POLL_FAST_MS;
      void pollOnce(); // 立即拉一次，缩短回复延迟
    } catch (err) {
      if (err instanceof AuthError) { setPhase('auth-failed'); return; }
      setMessages((prev) => prev.map((m) => (m.id === tempId ? { ...m, status: 'failed' } : m)));
    }
  }, [pollOnce, scrollBottom]);

  const onSendTap = useCallback(async () => {
    const text = inputText.trim();
    if (!text || sending) return;
    setSending(true);
    setInputText('');
    await sendText(text);
    setSending(false);
  }, [inputText, sending, sendText]);

  // ---------- 历史 / 图片 ----------
  const loadEarlier = useCallback(async () => {
    const first = messages.find((m) => !m.id.startsWith('temp-'));
    if (!first || loadingEarlier) return;
    setLoadingEarlier(true);
    try {
      const res = await api.list(first.id, 20);
      if (res.items.length) {
        setMessages((prev) => [...res.items.map(toVM).reverse(), ...prev]);
      }
    } catch { /* 非关键路径 */ } finally {
      setLoadingEarlier(false);
    }
  }, [messages, loadingEarlier]);

  const onPicError = useCallback((id: string) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, picBroken: true } : m)));
  }, []);

  const onPicTap = useCallback((url: string) => {
    window.open(url, '_blank');
  }, []);

  const onFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // 允许重复选同一文件
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      alert('图片超过 10MB，请选择更小的图片');
      return;
    }
    const tempId = `temp-${Date.now()}`;
    const blobUrl = URL.createObjectURL(file);
    setMessages((prev) => [...prev, {
      id: tempId, role: 'user', msg_type: 'image',
      content: { image_url: blobUrl }, status: 'pending', created_at: Date.now(),
    }] as MsgVM[]);
    scrollBottom();
    try {
      const compressed = await compressImage(file);
      const res = await api.uploadImage(compressed);
      // blob URL 本会话稳定：仅同步状态（与原生页策略一致，不闪烁）
      setMessages((prev) => prev.map((m) => (m.id === tempId ? { ...m, status: res.status } : m)));
    } catch (err) {
      if (err instanceof AuthError) { setPhase('auth-failed'); return; }
      URL.revokeObjectURL(blobUrl);
      setMessages((prev) => prev.map((m) => (m.id === tempId ? { ...m, picBroken: true } : m)));
    }
  }, [scrollBottom]);

  // ---------- 转人工 ----------
  const onTransferTap = useCallback(async () => {
    if (transferred) return;
    try {
      await api.transfer();
      setTransferred(true);
      void pollOnce();
    } catch (err) {
      if (err instanceof AuthError) setPhase('auth-failed');
    }
  }, [transferred, pollOnce]);

  if (phase === 'auth-failed') {
    return <ErrorState
      title="登录已过期"
      message="请返回小程序重新进入客服"
    />;
  }
  if (phase === 'init') {
    return <div className="state-card"><p>加载中…</p></div>;
  }

  return (
    <div className="app">
      <div
        className="chat-scroll"
        onScroll={(e) => {
          const el = e.currentTarget;
          if (el.scrollTop < 10 && !loadingEarlier) void loadEarlier();
        }}
      >
        <Hero />
        {suggestions.length > 0 && (
          <div className="suggest">
            <h4>你可以这样问我</h4>
            {suggestions.map((q) => (
              <div key={q} className="suggest-item" onClick={() => void sendText(q)} role="button">
                <span>✦ {q}</span>
              </div>
            ))}
          </div>
        )}
        {/* 开场白（常显） */}
        <div className="msg">
          <div className="avatar"><div className="bot-mini"><div className="bot-mini-visor">
            <div className="bot-mini-eye left" /><div className="bot-mini-eye right" /><div className="bot-mini-mouth" />
          </div></div></div>
          <div className="bubble bot">您好！我是深维之家咨询小助手，很高兴为您服务！请问有什么可以帮到您的呢？</div>
        </div>
        <MessageList items={messages} onPicError={onPicError} onPicTap={onPicTap} />
        {loadingEarlier && <div className="sys-tip">正在加载…</div>}
        <div ref={scrollAnchor} id="page-bottom" />
      </div>

      <div className="quickbar">
        <button className={`chip ${transferred ? 'chip-done' : ''}`} onClick={onTransferTap}>
          🎧 {transferred ? '已转人工' : '转人工'}
        </button>
      </div>

      <div className="inputzone">
        <div className="inputbar">
          <label className="icon-btn" title="发送图片">
            <input type="file" accept="image/*" style={{ display: 'none' }} onChange={onFileChange} />
            ＋
          </label>
          <input
            value={inputText}
            placeholder="有什么不懂的可以问我"
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void onSendTap(); }}
          />
          <button
            className={`icon-btn ${showEmoji ? 'active' : ''}`}
            onClick={() => setShowEmoji(!showEmoji)}
          >😊</button>
          <button className="send-btn" disabled={!inputText.trim()} onClick={onSendTap}>➤</button>
        </div>
        <div className={`panel ${showEmoji ? 'open' : ''}`}>
          <div className="emoji-grid">
            {EMOJIS.map((e) => (
              <button key={e} onClick={() => setInputText(inputText + e)}>{e}</button>
            ))}
          </div>
        </div>
        <div className="home-indicator" />
      </div>
    </div>
  );
}

function toVM(item: import('../api').MessageItem): MsgVM {
  return { ...item };
}

/** canvas 压缩：长边 1600px、quality 0.6；解码失败回退原图（HEIC 兜底）。 */
async function compressImage(file: File): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(file);
    const long = Math.max(bitmap.width, bitmap.height);
    const scale = Math.min(1, 1600 / long);
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, 'image/jpeg', 0.6));
    return blob ?? file;
  } catch {
    return file; // 解码失败（HEIC 等）→ 原图直传，后端 415 时走失败占位
  }
}
