# 微舆舆情分析系统 - Web应用

## 项目介绍

微舆舆情分析系统的Web应用部分，基于Vue 3 + TypeScript + Element Plus开发，提供完整的舆情分析功能。

## 技术栈

- **前端框架**: Vue 3
- **开发语言**: TypeScript
- **UI组件库**: Element Plus
- **状态管理**: Pinia
- **路由管理**: Vue Router
- **HTTP客户端**: Axios
- **构建工具**: Vite

## 功能模块

- **用户管理**: 注册、登录、个人信息管理
- **舆情分析**: 提交分析请求、查看分析结果
- **报告管理**: 查看历史报告、下载报告
- **系统配置**: API密钥配置、模型选择
- **监控中心**: 查看系统状态、日志
- **智能体管理**: 启动/停止智能体、配置参数

## 安装步骤

### 1. 安装依赖

```bash
npm install
```

### 2. 配置环境变量

创建 `.env` 文件，配置API基础URL：

```
VITE_API_BASE_URL=http://localhost:5000/api
```

### 3. 开发模式运行

```bash
npm run dev
```

### 4. 生产构建

```bash
npm run build
```

### 5. 预览生产构建

```bash
npm run preview
```

## 目录结构

```
├── public/              # 静态资源
├── src/                 # 源代码
│   ├── assets/          # 资源文件
│   ├── components/      # 组件
│   ├── router/          # 路由配置
│   ├── store/           # 状态管理
│   ├── utils/           # 工具函数
│   ├── views/           # 页面组件
│   ├── App.vue          # 根组件
│   ├── main.ts          # 入口文件
│   └── style.css        # 全局样式
├── .env                 # 环境变量
├── index.html           # HTML模板
├── package.json         # 项目配置
├── tsconfig.json        # TypeScript配置
└── vite.config.ts       # Vite配置
```

## 开发指南

### 代码规范

- 遵循Vue 3 Composition API
- 使用TypeScript进行类型检查
- 组件命名使用PascalCase
- 变量命名使用camelCase
- 常量命名使用UPPER_CASE

### 路由配置

路由配置位于 `src/router/index.ts`，添加新页面时需要在该文件中注册路由。

### 状态管理

状态管理使用Pinia，配置位于 `src/store/` 目录下。

### API请求

API请求通过封装的Axios实例进行，配置位于 `src/utils/http.ts`。

## 部署

### 本地部署

1. 构建生产版本
2. 使用Nginx或Apache等Web服务器部署
3. 配置反向代理指向API服务

### Docker部署

```dockerfile
FROM nginx:latest
COPY dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

## 许可证

MIT License
