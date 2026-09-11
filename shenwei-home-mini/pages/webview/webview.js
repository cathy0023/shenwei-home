/** web-view 壳：携带 token 打开 H5 聊天页。禁分享防 token 泄露。 */
const H5_BASE = 'https://xdf.nonoai.com.cn/h5/';

Page({
  data: { src: '' },

  onLoad(options) {
    const token = options.token || '';
    if (!token) {
      wx.showToast({ title: '登录状态缺失，请重试', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 1500);
      return;
    }
    this.setData({ src: `${H5_BASE}?token=${encodeURIComponent(token)}` });
  },

  /** 禁用转发：分享卡片会携带含 token 的 src（RFC SHM-002 风险项）。 */
  onShareAppMessage() {
    return { title: '深维之家', path: '/pages/mine/mine' };  // 剥离 token，仅回首页
  },
});
