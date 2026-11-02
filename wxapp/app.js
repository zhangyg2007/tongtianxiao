// app.js
App({
  onLaunch() {
    // 检查登录状态
    this.checkLoginStatus();
  },

  onShow() {
    // 应用启动或从后台进入前台时触发
  },

  onHide() {
    // 应用从前台进入后台时触发
  },

  // 检查登录状态
  checkLoginStatus() {
    const token = wx.getStorageSync('token');
    const userInfo = wx.getStorageSync('userInfo');
    
    if (token && userInfo) {
      this.globalData.isLoggedIn = true;
      this.globalData.userInfo = userInfo;
    }
  },

  // 登录
  login() {
    return new Promise((resolve, reject) => {
      wx.login({
        success: (res) => {
          if (res.code) {
            // 发送 res.code 到后台换取 openId, sessionKey, unionId
            wx.request({
              url: `${this.globalData.apiBaseUrl}/wx/auth/login`,
              method: 'POST',
              data: {
                code: res.code
              },
              success: (response) => {
                if (response.data.success) {
                  const { token, userInfo, role } = response.data.data;
                  
                  // 保存登录状态
                  this.globalData.isLoggedIn = true;
                  this.globalData.token = token;
                  this.globalData.userInfo = userInfo;
                  this.globalData.role = role;
                  
                  // 持久化存储
                  wx.setStorageSync('token', token);
                  wx.setStorageSync('userInfo', userInfo);
                  wx.setStorageSync('role', role);
                  
                  resolve(response.data.data);
                } else {
                  reject(new Error(response.data.message || '登录失败'));
                }
              },
              fail: (error) => {
                reject(error);
              }
            });
          } else {
            reject(new Error('登录失败：' + res.errMsg));
          }
        },
        fail: (error) => {
          reject(error);
        }
      });
    });
  },

  // 退出登录
  logout() {
    // 清除登录状态
    this.globalData.isLoggedIn = false;
    this.globalData.token = '';
    this.globalData.userInfo = null;
    this.globalData.role = 'user';
    
    // 清除本地存储
    wx.removeStorageSync('token');
    wx.removeStorageSync('userInfo');
    wx.removeStorageSync('role');
  },

  // 全局数据
  globalData: {
    apiBaseUrl: 'http://localhost:5000/api',
    isLoggedIn: false,
    token: '',
    userInfo: null,
    role: 'user'
  }
});