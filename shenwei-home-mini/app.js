/** 深维之家小程序全局入口：静默登录 + 全局会话凭证。 */
const api = require('./utils/api');

App({
  globalData: {
    token: '',
    openid: '',
    // 生产后端（本地调试可改回 http://127.0.0.1:8200）
    baseUrl: 'https://xdf.nonoai.com.cn',
  },

  onLaunch() {
    this.ensureLogin();
  },

  /** 静默登录（缓存 Promise）：防多处并发触发；调用方 await 后保证 token 已就绪或已失败。 */
  ensureLogin() {
    if (!this._loginPromise) {
      this._loginPromise = this.silentLogin().finally(() => {
        this._loginPromise = null;
      });
    }
    return this._loginPromise;
  },

  /** wx.login 静默登录：code 换 token；失败不阻塞 UI（聊天页可重试）。 */
  async silentLogin() {
    try {
      const { code } = await new Promise((resolve, reject) => {
        wx.login({ success: resolve, fail: reject });
      });
      const res = await api.login(this.globalData.baseUrl, code);
      this.globalData.token = res.token;
      this.globalData.openid = res.openid;
      wx.setStorageSync('token', res.token);
      wx.setStorageSync('openid', res.openid);
    } catch (err) {
      console.error('silentLogin failed', err);
    }
  },
});
