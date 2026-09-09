/** 聊天页：消息流 + 轮询 + 输入（文字/表情/图片）+ 转人工。 */
const api = require('../../utils/api');

const EMOJIS = ['😀','😁','🤣','😊','😍','🤔','😅','😭','😤','😱','🥳','😴',
  '🤝','👍','👏','🙏','💪','🔥','✨','💝','🎉','🌹','☕','🎁',
  '📞','💬','📮','⚠️','✅','❌','⭐','🌙'];

// 轮询节奏（RFC 5.6）：有新消息 3s，空闲退避至 10s
const POLL_FAST_MS = 3000;
const POLL_SLOW_MS = 10000;

Page({
  data: {
    messages: [],          // {id, role, msgType, content, status, picUrl?}
    suggestions: [],
    inputText: '',
    emojis: EMOJIS,
    showEmojiPanel: false,
    showImagePanel: false,
    sending: false,
    transferred: false,
    welcomeVisible: true,  // 首条用户消息发出后隐藏 hero
  },

  pollTimer: null,
  pollInterval: POLL_FAST_MS,
  lastSince: 0,
  transferLockUntil: 0,   // 转人工 5s 防抖

  onLoad() {
    const app = getApp();
    this.baseUrl = app.globalData.baseUrl;
    this.token = app.globalData.token;
    this.loadSuggestions();
    this.loadHistory();
    this.startPolling();
  },

  onShow() {
    // 切回前台立即拉一次（RFC：切后台暂停、onShow 立即拉）
    this.pollOnce();
    this.startPolling();
  },

  onHide() {
    this.stopPolling();
  },

  onUnload() {
    this.stopPolling();
  },

  async loadSuggestions() {
    try {
      const res = await api.suggestions(this.baseUrl);
      this.setData({ suggestions: res.items });
    } catch (err) {
      console.error('suggestions failed', err);
    }
  },

  async loadHistory() {
    try {
      const res = await api.list(this.baseUrl, this.token);
      const messages = res.items.map(this.toViewModel);
      this.setData({
        messages,
        welcomeVisible: messages.length === 0,
      });
      this.scrollToBottom();
    } catch (err) {
      console.error('loadHistory failed', err);
      if (err.statusCode === 401) this.relogin();
    }
  },

  /** 下拉加载更早历史。 */
  async loadEarlier() {
    const first = this.data.messages.find((m) => m.role !== 'temp');
    if (!first) return;
    try {
      const res = await api.list(this.baseUrl, this.token, first.id);
      if (res.items.length) {
        const earlier = res.items.map(this.toViewModel);
        this.setData({ messages: [...earlier, ...this.data.messages] });
      }
    } catch (err) {
      wx.showToast({ title: '历史加载失败', icon: 'none' });
    }
  },

  toViewModel(item) {
    return {
      id: item.id,
      role: item.role,
      isUser: item.role === 'user',
      isSystem: item.role === 'system',
      isImage: item.msg_type === 'image',
      content: item.content.content || '',
      picUrl: item.content.image_url ? `${getApp().globalData.baseUrl}${item.content.image_url}` : '',
      status: item.status,
    };
  },

  // ---------- 发送 ----------

  onInput(e) {
    this.setData({ inputText: e.detail.value });
  },

  async onSendTap() {
    const text = (this.data.inputText || '').trim();
    if (!text || this.data.sending) return;
    this.setData({ sending: true, inputText: '' });
    await this.sendText(text);
    this.setData({ sending: false });
  },

  async sendText(text) {
    const tempId = `temp-${Date.now()}`;
    this.appendLocal({
      id: tempId, role: 'user', isUser: true, isSystem: false, isImage: false,
      content: text, picUrl: '', status: 'pending',
    });
    this.hideWelcome();
    try {
      const res = await api.send(this.baseUrl, this.token, text);
      this.updateLocalStatus(tempId, res.status);
      this.pollInterval = POLL_FAST_MS;
    } catch (err) {
      this.updateLocalStatus(tempId, 'failed');
      wx.showToast({ title: '发送失败，请重试', icon: 'none' });
    }
  },

  onSuggestTap(e) {
    this.sendText(e.currentTarget.dataset.q);
  },

  /** 图片：选择即上传（≤10MB 由后端兜底）。 */
  async onChooseImage() {
    this.closePanels();
    try {
      const { tempFiles } = await wx.chooseMedia({
        count: 1,
        mediaType: ['image'],
        sizeType: ['compressed'],
      });
      const filePath = tempFiles[0].tempFilePath;
      const tempId = `temp-${Date.now()}`;
      this.appendLocal({
        id: tempId, role: 'user', isUser: true, isSystem: false, isImage: true,
        content: '', picUrl: filePath, status: 'pending',
      });
      this.hideWelcome();
      const res = await api.uploadImage(this.baseUrl, this.token, filePath);
      this.updateLocalStatus(tempId, res.status);
      wx.showToast({ title: '图片已发送', icon: 'none' });
    } catch (err) {
      if (err && err.errMsg && err.errMsg.includes('cancel')) return;
      wx.showToast({ title: '图片发送失败', icon: 'none' });
    }
  },

  /** 转人工：5s 防抖 + 后端 event。 */
  async onTransferTap() {
    const now = Date.now();
    if (now < this.transferLockUntil) {
      wx.showToast({ title: '已转接，请稍候', icon: 'none' });
      return;
    }
    this.transferLockUntil = now + 5000;
    try {
      await api.transfer(this.baseUrl, this.token);
      this.setData({ transferred: true });
      this.pollOnce();
    } catch (err) {
      wx.showToast({ title: '转接失败，请重试', icon: 'none' });
    }
  },

  // ---------- 轮询 ----------

  startPolling() {
    this.stopPolling();
    this.pollTimer = setTimeout(async () => {
      await this.pollOnce();
      this.startPolling();
    }, this.pollInterval);
  },

  stopPolling() {
    if (this.pollTimer) {
      clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }
  },

  async pollOnce() {
    try {
      const res = await api.poll(this.baseUrl, this.token, this.lastSince);
      if (res.items && res.items.length) {
        const known = new Set(this.data.messages.map((m) => m.id));
        const fresh = res.items
          .filter((i) => !known.has(i.id))
          .map(this.toViewModel);
        if (fresh.length) {
          this.setData({ messages: [...this.data.messages, ...fresh] });
          this.scrollToBottom();
        }
        this.lastSince = res.next_since;
        this.pollInterval = POLL_FAST_MS;
      } else {
        // 空轮询退避
        this.pollInterval = Math.min(this.pollInterval + 1000, POLL_SLOW_MS);
      }
    } catch (err) {
      if (err.statusCode === 401) this.relogin();
    }
  },

  async relogin() {
    const app = getApp();
    await app.silentLogin();
    this.token = app.globalData.token;
  },

  // ---------- 本地消息操作 ----------

  appendLocal(msg) {
    this.setData({ messages: [...this.data.messages, msg] });
    this.scrollToBottom();
  },

  updateLocalStatus(tempId, status) {
    const messages = this.data.messages.map((m) =>
      m.id === tempId ? { ...m, status } : m);
    this.setData({ messages });
  },

  hideWelcome() {
    if (this.data.welcomeVisible) this.setData({ welcomeVisible: false });
  },

  scrollToBottom() {
    wx.nextTick(() => {
      wx.pageScrollTo({ scrollTop: 999999, duration: 200 });
    });
  },

  // ---------- 面板 ----------

  onEmojiTap(e) {
    this.setData({ inputText: this.data.inputText + e.currentTarget.dataset.e });
  },

  toggleEmojiPanel() {
    const next = !this.data.showEmojiPanel;
    this.setData({ showEmojiPanel: next, showImagePanel: false });
  },

  toggleImagePanel() {
    const next = !this.data.showImagePanel;
    this.setData({ showImagePanel: next, showEmojiPanel: false });
    if (next) this.onChooseImage();
  },

  closePanels() {
    this.setData({ showEmojiPanel: false, showImagePanel: false });
  },

  onImagePreview(e) {
    wx.previewImage({ urls: [e.currentTarget.dataset.url] });
  },
});
