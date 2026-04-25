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
- **17个网站专用适配器** — 针对国内主流网站定制提取逻辑
- **Cookie认证** — 支持传入登录Cookie，获取高画质/私密内容

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
├── extractors.py           # 17个站点专用 + 通用媒体提取器
├── downloader.py           # 批量下载管理模块
├── requirements.txt        # Python 依赖包
├── templates/
│   └── index.html          # 前端主页面
├── static/
│   ├── css/style.css       # 样式文件
│   └── js/app.js           # 前端交互逻辑
└── downloads/              # 默认下载目录
```

## 🚀 快速开始

```bash
pip install -r requirements.txt
python app.py
```

访问 http://127.0.0.1:5000

## 🌍 支持的网站

### ✅ 无需登录即可提取

| 网站 | 提取内容 | 说明 |
|------|----------|------|
| **GitHub** | 仓库文件、Release资源、代码文件 | 支持Repo/Release/Blob页面 |
| **CSDN** | 博客文章图片 | 自动提取博文中的全部图片 |
| **酷狗音乐** | 歌曲封面、排行榜图片 | 首页及歌曲页面 |
| **网易云音乐** | 歌曲封面、歌手图片 | 通过API获取歌曲详情 |
| **酷安** | 帖子图片 | 自动去除缩略图后缀获取原图 |
| **Pinterest** | Pin图片 | 提取original尺寸图片 |
| **Pixiv** | 插画图片 | 需Cookie获取具体作品图 |
| **Instagram** | 帖子图片/视频 | 需Cookie获取用户帖子 |
| **Twitter/X** | 推文图片/视频 | 需Cookie获取推文内容 |

### 🔑 需要登录Cookie

| 网站 | 所需Cookie | 提取内容 |
|------|-----------|----------|
| **B站** | SESSDATA | 视频/音频流（1080P60高画质） |
| **小红书** | 完整Cookie或a1值 | 笔记图片/视频 |
| **微博** | SUB | 微博图片/视频 |
| **抖音** | ttwid / msToken | 短视频/图集 |
| **快手** | — | 短视频/封面 |
| **知乎** | _xsrf等 | 专栏文章图片/视频 |
| **百度贴吧** | BDUSS | 帖子图片 |
| **Lofter** | — | 博客图片 |

### 提取策略

每个网站采用**多级回退策略**：

1. **专用API** — 优先调用网站API获取结构化数据（最高质量）
2. **嵌入JS解析** — 提取 `__INITIAL_STATE__`、`_ROUTER_DATA`、`__APOLLO_STATE__` 等嵌入数据
3. **HTML正则** — 匹配CDN图片/视频URL模式
4. **og:meta** — 提取 OpenGraph 标签中的媒体URL
5. **通用抓取** — 解析所有 `<img>`、`<video>`、`<a>` 标签

## 🎬 B站视频下载指南

### 基本用法

直接输入B站视频链接（如 `https://www.bilibili.com/video/BV1xxxx`）。

**未登录**：480P、360P | **登录后**：1080P60、1080P、720P 等

### 获取高画质

1. 浏览器登录 bilibili.com → F12 → Application → Cookies
2. 复制 **SESSDATA** 值
3. 粘贴到工具「🍪 网站Cookie设置」的B站输入框

### DASH 合并

B站 DASH 格式视频/音频分离，需 ffmpeg 合并：

```bash
ffmpeg -i 视频流.mp4 -i 音频流.m4a -c copy 输出.mp4
```

## 📕 小红书笔记下载指南

直接输入笔记链接即可提取全部图片/视频。工具解析 `__INITIAL_STATE__` 获取真实CDN地址，而非Logo占位图。

如遇私密笔记，提供小红书Cookie即可。

## 🍪 Cookie设置说明

部分网站需要登录Cookie才能提取内容。通用获取方法：

1. 浏览器中登录目标网站
2. 按 **F12** → **Application** → **Cookies**
3. 复制对应Cookie值粘贴到工具的Cookie设置面板

| 网站输入框 | 获取方式 |
|-----------|----------|
| B站 SESSDATA | Cookies中找到SESSDATA |
| 小红书 Cookie | 复制整个Cookie字符串或仅a1值 |
| 微博 Cookie | 复制Cookie中的SUB字段 |
| 知乎 Cookie | 复制完整Cookie字符串 |
| 抖音 Cookie | 复制Cookie中的ttwid/msToken |
| Pixiv Cookie | 复制PHPSESSID |

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

**带Cookie分析**
```bash
curl -X POST http://127.0.0.1:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.bilibili.com/video/BV1xxxx", "cookies": {"SESSDATA": "xxx"}}'
```

**开始下载**
```bash
curl -X POST http://127.0.0.1:5000/api/download \
  -H "Content-Type: application/json" \
  -d '{"resources": [{"url": "https://example.com/file.pdf", "name": "file.pdf"}]}'
```

## 📄 许可证

MIT License
