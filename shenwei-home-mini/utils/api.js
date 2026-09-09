/** 后端 API 封装：统一 Bearer、错误上抛。 */
function request(baseUrl, path, { method = 'GET', data = null, token = '', header = {} } = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${baseUrl}${path}`,
      method,
      data,
      header: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...header,
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject({ statusCode: res.statusCode, data: res.data });
        }
      },
      fail: reject,
    });
  });
}

function uploadImage(baseUrl, token, filePath) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: `${baseUrl}/api/messages/image`,
      filePath,
      name: 'file',
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(JSON.parse(res.data));
        } else {
          reject({ statusCode: res.statusCode, data: res.data });
        }
      },
      fail: reject,
    });
  });
}

module.exports = {
  request,
  uploadImage,
  login: (baseUrl, code) =>
    request(baseUrl, '/api/auth/login', { method: 'POST', data: { code } }),
  send: (baseUrl, token, content) =>
    request(baseUrl, '/api/messages/send', { method: 'POST', data: { content }, token }),
  list: (baseUrl, token, cursor = '', limit = 20) =>
    request(baseUrl, `/api/messages/list?cursor=${encodeURIComponent(cursor)}&limit=${limit}`, { token }),
  poll: (baseUrl, token, since = 0, limit = 20) =>
    request(baseUrl, `/api/messages/poll?since=${since}&limit=${limit}`, { token }),
  transfer: (baseUrl, token) =>
    request(baseUrl, '/api/messages/transfer', { method: 'POST', data: {}, token }),
  suggestions: (baseUrl) =>
    request(baseUrl, '/api/suggestions'),
};
