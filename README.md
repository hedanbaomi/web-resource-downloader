# 🌐 网页资源下载器

输入网址，自动发现网页中的所有资源（PDF、DOCX、视频、音频、图片等），用户自行选择后批量下载到本地。

## ✨ 功能特性

- **资源发现** — 输入 URL 后自动扫描网页中所有可下载资源
- **智能分类** — 按文档、视频、音频、图片、压缩包等类别自动归类
- **分类筛选** — 前端支持按类别快速筛选，一键全选/取消
- **批量下载** — 多线程并发下载，支持大量文件同时下载
- **实时进度** — SSE 实时推送下载进度，显示成功/失败计数
- **忽略 robots.txt** — 不受网站 robots.txt 限制，伪装浏览器请求头绕过反爬
- **断点容错** — 下载失败自动重试（最多3次），文件名冲突自动重命名
- **B站视频提取** — 自动调用B站 API 提取视频/音频流，支持 DASH 格式多画质多编码
- **B站高画质** — 支持 Cookie 登录认证，获取 1080P60、1080P、720P 等高画质视频流
- **通用动态提取** — 解析 og:video、JSON-LD、嵌入 JS 中的媒体 URL，覆盖更多动态网站

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3 + Flask |
| 网页解析 | requests + BeautifulSoup4 + lxml |
| 并发下载 | concurrent.futures (ThreadPoolExecutor) |
| 进度推送 | Server-Sent Events (SSE) |
| 前端 | HTML + CSS + JavaScript |

## 📁 项目结构

```
网页资源下载器/
├── app.py                  # Flask 主应用（路由与 API）
├── scraper.py              # 网页抓取与资源解析模块
├── extractors.py           # 站点专用与通用媒体提取器
├── downloader.py           # 批量下载管理模块
├── requirements.txt        # Python 依赖包
├── README.md               # 项目说明
├── templates/
│   └── index.html          # 前端主页面
├── static/
│   ├── css/
│   │   └── style.css       # 样式文件
│   └── js/
│       └── app.js          # 前端交互逻辑
└── downloads/              # 默认下载目录
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python app.py
```

### 3. 打开浏览器

访问 http://127.0.0.1:5000

### 4. 使用步骤

1. 在输入框中输入目标网址
2. 点击「分析」按钮，等待资源扫描完成
3. 使用分类标签筛选资源，勾选需要下载的文件
4. 点击「批量下载」按钮开始下载
5. 在进度区域查看下载状态

## 🎬 B站视频下载指南

### 基本用法

直接输入B站视频链接（如 `https://www.bilibili.com/video/BV1xxxx`），工具会自动识别并提取视频/音频流。

**未登录时**可获取的画质：480P、360P

### 获取高画质（1080P60 等）

B站 720P 及以上画质需要登录 Cookie，操作步骤：

1. 在浏览器中登录 [bilibili.com](https://www.bilibili.com)
2. 按 **F12** 打开开发者工具
3. 切换到 **Application**（应用程序）标签
4. 左侧展开 **Cookies** → 点击 `https://www.bilibili.com`
5. 找到 **SESSDATA** 行，双击其值复制
6. 回到本工具，点击「🍪 网站Cookie设置」展开面板
7. 将 SESSDATA 值粘贴到输入框中
8. 输入B站视频URL，点击分析

**登录后**可获取的画质：1080P60、1080P、720P、480P、360P

### DASH 视频流说明

B站使用 DASH 格式，视频和音频是分开的：

- 🔐 标记的资源需要特殊请求头下载
- ⚠ 标记的资源为 DASH 视频流（仅含画面，无声音）

**合并音视频**：同时下载视频流和音频流后，使用 ffmpeg 合并：

```bash
ffmpeg -i 视频流_1080P60_H.264.mp4 -i 音频流_高品质.m4a -c copy 输出.mp4
```

### 支持的画质与编码

| 画质 | 编码 | 登录要求 |
|------|------|----------|
| 4K (120) | H.264 / H.265 / AV1 | 大会员 Cookie |
| 1080P60 (116) | H.264 / H.265 / AV1 | 登录 Cookie |
| 1080P高码率 (112) | H.264 / H.265 / AV1 | 登录 Cookie |
| 1080P (80) | H.264 / H.265 / AV1 | 登录 Cookie |
| 720P60 (74) | H.264 / H.265 / AV1 | 登录 Cookie |
| 720P (64) | H.264 / H.265 / AV1 | 登录 Cookie |
| 480P (32) | H.264 / H.265 | 无需登录 |
| 360P (16) | H.264 / H.265 | 无需登录 |

| 音质 | 登录要求 |
|------|----------|
| Hi-Res (30251) | 大会员 Cookie |
| 高品质 (30280) | 登录 Cookie |
| 中品质 (30232) | 无需登录 |
| 低品质 (30216) | 无需登录 |

## 📡 API 接口

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 主页面 |
| `/api/analyze` | POST | 分析网页资源 |
| `/api/download` | POST | 开始批量下载 |
| `/api/download/progress` | GET (SSE) | 下载进度推送 |
| `/api/download/cancel` | POST | 取消下载任务 |

### 请求示例

**分析网页**

```bash
curl -X POST http://127.0.0.1:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

**分析B站视频（带 Cookie）**

```bash
curl -X POST http://127.0.0.1:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.bilibili.com/video/BV1xxxx", "cookies": {"SESSDATA": "你的SESSDATA值"}}'
```

**开始下载**

```bash
curl -X POST http://127.0.0.1:5000/api/download \
  -H "Content-Type: application/json" \
  -d '{"resources": [{"url": "https://example.com/file.pdf", "name": "file.pdf"}], "save_dir": ""}'
```

## 📄 许可证

MIT License
