# LEGACY：Vue3 前端（已归档）

## 这是什么

- 早期 M2 设计线的前端：Vue 3 + Vite + TypeScript + Pinia
- 已建登录/注册/首页/分析页骨架；`src/utils/http.ts` 基址写死 `http://localhost:5000/api`
- 路由引用了尚未创建的 `ReportsView.vue` / `ReportDetailView.vue` / `ConfigView.vue`

## 为何废弃

- 与 B 线主线前端重复：产品前端统一为 `bettafish-main/frontend/`（React 18 + Vite）
- 两套 Vite 默认端口都是 5173，同时启动必冲突
- 页面只到骨架，未接 `core` 数据模型

## 替代方案

- 产品前端：`bettafish-main/frontend/`（React + Vite，开发端口 5173，`/api` 代理到 Flask）
- 生产形态：构建产物由 Flask 托管，单入口 `http://<host>:8080/`

## 删除条件

同时满足才可删除：

1. React 工作台覆盖登录/对象检索/任务提交/报告查看/证据抽屉全部流程；
2. 连续 30 天无对 `web/` 的提交与依赖更新；
3. `archive/m2-20261104` 可随时取回。

在此之前：**不参与构建、不安装 npm 依赖、不修 bug**。
