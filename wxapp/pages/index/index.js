// index.js
Page({
  /**
   * 页面的初始数据
   */
  data: {
    keyword: '',
    hotTopics: [
      { id: 1, rank: 1, keyword: '人工智能', platform: '微博', hotness: '100万+' },
      { id: 2, rank: 2, keyword: '新能源汽车', platform: '小红书', hotness: '80万+' },
      { id: 3, rank: 3, keyword: '气候变化', platform: '抖音', hotness: '70万+' },
      { id: 4, rank: 4, keyword: '数字经济', platform: '快手', hotness: '60万+' },
      { id: 5, rank: 5, keyword: '元宇宙', platform: '知乎', hotness: '50万+' }
    ],
    recentReports: [
      { id: 1, title: '人工智能舆情分析报告', keyword: '人工智能', created_at: '2025-12-10 14:30', status: 'completed' },
      { id: 2, title: '新能源汽车市场分析', keyword: '新能源汽车', created_at: '2025-12-09 10:15', status: 'completed' },
      { id: 3, title: '气候变化公众态度调研', keyword: '气候变化', created_at: '2025-12-08 16:45', status: 'completed' },
      { id: 4, title: '数字经济发展趋势', keyword: '数字经济', created_at: '2025-12-07 09:30', status: 'completed' }
    ]
  },

  /**
   * 生命周期函数--监听页面加载
   */
  onLoad(options) {
    // 页面加载时的初始化
    this.checkLoginStatus();
  },

  /**
   * 生命周期函数--监听页面初次渲染完成
   */
  onReady() {
    // 页面渲染完成
  },

  /**
   * 生命周期函数--监听页面显示
   */
  onShow() {
    // 页面显示
  },

  /**
   * 生命周期函数--监听页面隐藏
   */
  onHide() {
    // 页面隐藏
  },

  /**
   * 生命周期函数--监听页面卸载
   */
  onUnload() {
    // 页面卸载
  },

  /**
   * 检查登录状态
   */
  checkLoginStatus() {
    const app = getApp();
    if (!app.globalData.isLoggedIn) {
      // 提示用户登录
      wx.showModal({
        title: '提示',
        content: '请先登录',
        success: (res) => {
          if (res.confirm) {
            wx.navigateTo({
              url: '/pages/login/login'
            });
          }
        }
      });
    }
  },

  /**
   * 关键词输入处理
   */
  onKeywordInput(e) {
    this.setData({
      keyword: e.detail.value
    });
  },

  /**
   * 开始分析
   */
  startAnalysis() {
    const keyword = this.data.keyword.trim();
    if (!keyword) {
      wx.showToast({
        title: '请输入关键词',
        icon: 'none'
      });
      return;
    }

    // 跳转到分析配置页面
    wx.navigateTo({
      url: `/pages/analysis/analysis?keyword=${encodeURIComponent(keyword)}`
    });
  },

  /**
   * 热门话题点击
   */
  onTopicClick(e) {
    const keyword = e.currentTarget.dataset.keyword;
    this.setData({
      keyword: keyword
    });
    this.startAnalysis();
  },

  /**
   * 查看报告
   */
  viewReport(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/reportDetail/reportDetail?id=${id}`
    });
  },

  /**
   * 查看全部热门话题
   */
  viewAllTopics() {
    wx.showToast({
      title: '功能开发中',
      icon: 'none'
    });
  },

  /**
   * 查看全部报告
   */
  viewAllReports() {
    wx.navigateTo({
      url: '/pages/reports/reports'
    });
  },

  /**
   * 跳转到舆情分析页面
   */
  navigateToAnalysis() {
    wx.navigateTo({
      url: '/pages/analysis/analysis'
    });
  },

  /**
   * 跳转到报告管理页面
   */
  navigateToReports() {
    wx.navigateTo({
      url: '/pages/reports/reports'
    });
  },

  /**
   * 跳转到个人中心页面
   */
  navigateToProfile() {
    wx.navigateTo({
      url: '/pages/profile/profile'
    });
  }
});