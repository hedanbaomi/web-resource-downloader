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

**开始下载**

```bash
curl -X POST http://127.0.0.1:5000/api/download \
  -H "Content-Type: application/json" \
  -d '{"resources": [{"url": "https://example.com/file.pdf", "name": "file.pdf"}], "save_dir": ""}'
```

## 📄 许可证

MIT License
