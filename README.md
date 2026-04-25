# 🌐 网页资源下载器

输入网址，自动发现网页中的所有资源（PDF、DOCX、视频、音频、图片等），用户自行选择后批量下载到本地。

这个东西是今天参加trae family突然想做的，还不完善。

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

| 层级   | 技术                                      |
| ---- | --------------------------------------- |
| 后端   | Python 3 + Flask                        |
| 网页解析 | requests + BeautifulSoup4 + lxml        |
| 并发下载 | concurrent.futures (ThreadPoolExecutor) |
| 进度推送 | Server-Sent Events (SSE)                |
| 前端   | HTML + CSS + JavaScript                 |

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

访问 <http://127.0.0.1:5000>

## 🌍 支持的网站

### ✅ 无需登录即可提取

| 网站         | 提取内容                | 说明                                 |
| ---------- | ------------------- | ---------------------------------- |
| **GitHub** | 仓库文件、Release资源、代码文件 | 支持Repo/Release/Blob页面              |
| **CSDN**   | 博客文章图片              | 自动提取博文中的全部图片                       |
| **酷狗音乐**   | 歌曲封面、排行榜图片          | 首页及歌曲页面                            |
| **网易云音乐**  | 歌曲封面、歌手图片           | 通过API获取歌曲详情                        |
| **酷安**     | 帖子图片                | 自动去除缩略图后缀获取原图                      |
| **快手**     | 短视频/封面              | 解析 `__APOLLO_STATE__`              |
| **Lofter** | 博客图片                | 解析CDN图片URL                         |
| **小红书**    | 笔记图片/视频             | 解析 `__INITIAL_STATE__`，私密笔记需Cookie |
| **B站**     | 视频/音频流              | 未登录480P，提供SESSDATA可获取1080P+        |

### 🔑 需要登录Cookie才能提取

| 网站            | 关键Cookie字段         | 提取内容                |
| ------------- | ------------------ | ------------------- |
| **知乎**        | `_xsrf`、`z_c0`     | 专栏文章图片/视频（未登录返回403） |
| **百度贴吧**      | `BDUSS`            | 帖子图片（未登录返回403）      |
| **抖音**        | `ttwid`、`msToken`  | 短视频/图集（JS加密页面）      |
| **微博**        | `SUB`              | 微博原图/视频             |
| **Pixiv**     | `PHPSESSID`        | 插画原图                |
| **Twitter/X** | `auth_token`、`ct0` | 推文图片/视频             |
| **Instagram** | `sessionid`        | 帖子图片/视频             |
| **Pinterest** | `_pinterest_sess`  | Pin大图/视频            |

### 提取策略

每个网站采用**多级回退策略**：

1. **专用API** — 优先调用网站API获取结构化数据（最高质量）
2. **嵌入JS解析** — 提取 `__INITIAL_STATE__`、`_ROUTER_DATA`、`__APOLLO_STATE__` 等嵌入数据
3. **HTML正则** — 匹配CDN图片/视频URL模式
4. **og:meta** — 提取 OpenGraph 标签中的媒体URL
5. **通用抓取** — 解析所有 `<img>`、`<video>`、`<a>` 标签

### B站DASH视频合并说明

B站 DASH 格式视频/音频分离，需 ffmpeg 合并：

```bash
ffmpeg -i 视频流.mp4 -i 音频流.m4a -c copy 输出.mp4
```

## 🍪 Cookie设置说明

部分网站需要登录Cookie才能提取内容。工具提供10个网站的Cookie输入框，点击「🍪 网站Cookie设置」展开。

### 通用获取方法

1. 浏览器中登录目标网站
2. 按 **F12** 打开开发者工具
3. 切到 **Application（应用）** 标签 → 左侧 **Cookies** → 选择对应域名
4. 在右侧列表中找到目标Cookie，双击Value列复制值
5. 粘贴到工具的对应输入框

> 💡 **快捷方式**：也可以在 **Network（网络）** 标签中，随便点一个请求，在请求头 Request Headers 里找到 `Cookie:` 行，复制整行内容粘贴到输入框。工具会自动解析。

***

### 🎬 B站 (SESSDATA)

**用途**：未登录仅能获取 480P/360P 视频，登录后可获取 1080P60/1080P/720P。

**获取步骤**：

1. 登录 [bilibili.com](https://www.bilibili.com)
2. F12 → Application → Cookies → `https://www.bilibili.com`
3. 找到 **SESSDATA**，复制其 Value 值
4. 粘贴到「B站 SESSDATA」输入框

**示例值**：`a1b2c3d4%2Ce5f6g7h8...`（一串很长的URL编码字符串）

> ⚠️ SESSDATA 有效期约 30 天，过期需重新获取。

***

### 📕 小红书 (Cookie)

**用途**：获取笔记真实图片/视频（无Cookie只能看到Logo占位图）。

**获取步骤**：

1. 登录 [xiaohongshu.com](https://www.xiaohongshu.com)
2. 打开任意一篇笔记页面
3. F12 → Network → 刷新页面 → 点击第一个HTML请求
4. 在 Request Headers 中找到 `Cookie:` 行，**复制整行**
5. 粘贴到「小红书 Cookie」输入框

**也可以只粘贴关键字段**：

- 找到 Cookie 中的 `a1=xxxxx` 部分，只复制 `xxxxx` 值即可

**示例值**：`a1=1892abc3d4e5f6...; webId=xxx; ...` 或仅 `1892abc3d4e5f6`

***

### 📱 微博 (Cookie)

**用途**：获取微博正文图片（原图大图）和视频。无Cookie可能只能获取有限资源。

**获取步骤**：

1. 登录 [weibo.com](https://weibo.com)
2. F12 → Application → Cookies → `https://weibo.com`
3. 找到 **SUB** 字段，复制其 Value 值
4. 粘贴到「微博 Cookie」输入框

**也可以粘贴完整Cookie**：在 Network 面板复制整行 `Cookie:` 值粘贴，工具会自动提取 SUB。

**示例值**：`_2A25xxx...`（SUB字段的值）

***

### 🎓 知乎 (Cookie)

**用途**：知乎对未登录用户直接返回 403，必须提供Cookie才能访问。

**获取步骤**：

1. 登录 [zhihu.com](https://www.zhihu.com)
2. F12 → Network → 刷新页面 → 点击任意请求
3. 在 Request Headers 中找到 `Cookie:` 行，**复制整行**
4. 粘贴到「知乎 Cookie」输入框

**关键Cookie字段**：`_xsrf`、`z_c0`（登录token），工具会自动解析。

**示例值**：`_xsrf=abc123; z_c0=2|1:0|10:...; ...`

***

### 🎵 抖音 (Cookie)

**用途**：抖音对未登录用户使用JS加密，无法从HTML中提取内容。提供Cookie后可通过API获取视频。

**获取步骤**：

1. 登录 [douyin.com](https://www.douyin.com)
2. F12 → Network → 刷新页面 → 点击任意请求
3. 在 Request Headers 中找到 `Cookie:` 行，**复制整行**
4. 粘贴到「抖音 Cookie」输入框

**关键Cookie字段**：`ttwid`、`msToken`、`sessionid`，工具会自动解析整段Cookie。

**示例值**：`ttwid=xxx; msToken=xxx; sessionid=xxx; ...`

***

### 🎨 Pixiv (Cookie)

**用途**：获取Pixiv插画原图。无Cookie只能获取首页缩略图。

**获取步骤**：

1. 登录 [pixiv.net](https://www.pixiv.net)
2. F12 → Application → Cookies → `https://www.pixiv.net`
3. 找到 **PHPSESSID**，复制其 Value 值
4. 粘贴到「Pixiv Cookie」输入框

**也可以粘贴完整Cookie**：整行Cookie字符串均可，工具会自动提取 PHPSESSID。

**示例值**：`12345678_abcdef0123456789` 或仅 `12345678_abcdef`

***

### 🐦 Twitter/X (Cookie)

**用途**：获取推文中的图片/视频原始质量。无Cookie只能获取首页少量资源。

**获取步骤**：

1. 登录 [x.com](https://x.com)
2. F12 → Network → 刷新页面 → 点击任意 `api/graphql` 请求
3. 在 Request Headers 中找到 `Cookie:` 行，**复制整行**
4. 粘贴到「Twitter/X Cookie」输入框

**关键Cookie字段**：`auth_token`、`ct0`（CSRF token）

**示例值**：`auth_token=abc123; ct0=xyz789; ...`

***

### 📸 Instagram (Cookie)

**用途**：获取帖子图片/视频。无Cookie几乎无法提取内容。

**获取步骤**：

1. 登录 [instagram.com](https://www.instagram.com)
2. F12 → Network → 刷新页面 → 点击任意请求
3. 在 Request Headers 中找到 `Cookie:` 行，**复制整行**
4. 粘贴到「Instagram Cookie」输入框

**关键Cookie字段**：`sessionid`、`ds_user_id`

**示例值**：`sessionid=12345%3Aabc%3A12; ds_user_id=12345; ...`

***

### 📌 Pinterest (Cookie)

**用途**：获取Pin大图和视频。无Cookie只能获取首页缩略图。

**获取步骤**：

1. 登录 [pinterest.com](https://www.pinterest.com)
2. F12 → Network → 刷新页面 → 点击任意请求
3. 在 Request Headers 中找到 `Cookie:` 行，**复制整行**
4. 粘贴到「Pinterest Cookie」输入框

**示例值**：`_pinterest_sess=xxx; csrftoken=xxx; ...`

***

### 💬 百度贴吧 (Cookie)

**用途**：获取帖子中的图片。贴吧对未登录用户返回403。

**获取步骤**：

1. 登录 [tieba.baidu.com](https://tieba.baidu.com)
2. F12 → Application → Cookies → `https://tieba.baidu.com`
3. 找到 **BDUSS**，复制其 Value 值
4. 粘贴到「百度贴吧 Cookie」输入框

**也可以粘贴完整Cookie**：整行Cookie字符串均可。

**示例值**：`BDUSS` 的值是一串很长的Base64风格字符串

> ⚠️ BDUSS 是百度账号的核心登录凭证，切勿泄露给他人！

## 📡 API 接口

| 端点                       | 方法        | 说明     |
| ------------------------ | --------- | ------ |
| `/`                      | GET       | 主页面    |
| `/api/analyze`           | POST      | 分析网页资源 |
| `/api/download`          | POST      | 开始批量下载 |
| `/api/download/progress` | GET (SSE) | 下载进度推送 |
| `/api/download/cancel`   | POST      | 取消下载任务 |

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
