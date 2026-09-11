/** 「我的」个人页：静默登录持 token，联系客服入口（对齐客户侧个人中心形态）。 */
const H5_BASE = 'https://xdf.nonoai.com.cn/h5/';

Page({
  data: {
    token: '',
    loggedIn: false,
  },

  async onLoad() {
    const app = getApp();
    // 防竞态：await app 级登录 Promise（webview 进入前必须持 token）
    if (!app.globalData.token) {
      await app.ensureLogin();
    }
    this.setData({ token: app.globalData.token, loggedIn: true });
  },

  /** 联系客服：携带 token 进 web-view。 */
  goService() {
    if (!this.data.token) {
      wx.showToast({ title: '登录中，请稍候', icon: 'none' });
      return;
    }
    wx.navigateTo({ url: `/pages/webview/webview?token=${this.data.token}` });
  },
});
