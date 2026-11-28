# Savebili 文档

## 功能

- 通过 `/saveany <链接或BV号>` 或 `@机器人 <链接>` 下载视频并发送文件。
- B 站原生解析：视频、番剧、专栏、动态、收藏夹、合集；支持 b23.tv 等短链自动还原。
- 多平台解析（基于 yt-dlp）：抖音、小红书、微博、YouTube、TikTok、X（Twitter）、Instagram、Facebook、Vimeo 等。
- 群聊中仅响应 @机器人 的消息；私聊可直接发送链接。
- 支持 B 站、微博、抖音扫码登录，其他平台提供登录页与手动 Cookie 配置；Cookie 按平台分开管理。
- Web 管理页面提供数据概览、多平台扫码登录、Cookie 管理、配置修改和多平台设置。
- 数据概览展示今日/累计下载、成功率、7 天趋势、内容类型、平台分布和最近下载记录。
- 解析信息卡片支持自定义文本模板，可用 `{image}`（封面）、`{title}`、`{owner}` 等占位符。
- 解析后可回复「下载」或发送 `/bd1` 按需下载，不重新解析；`/saveany` 可显式下载。
- 配置修改后自动保存并生效。

## 使用方法

1. 在插件管理界面启用本插件，等待依赖（含 yt-dlp）安装完成。
2. 打开插件管理页面，在「扫码登录」中选择平台扫码；扫码不可用的平台请手动添加 Cookie。
3. 在聊天中发送 `/saveany <链接>`，或 @机器人 后发送链接、BV 号、短链。
4. 机器人会自动解析并下载视频后发送。

> 抖音等平台的分享文案很长（例如“复制打开抖音…”），可以直接整段粘贴，插件会从文本中提取链接。

### 指令与群聊下载权限

| 指令 | 作用 |
| --- | --- |
| `/saveany <链接>` | 显式解析并下载视频；不受群聊「默认下载」限制 |
| `/parse <链接>`（别名 `/解析`） | 只解析并缓存，不下载；之后可回复「下载」或发送 `/bd1` |
| `/bd1` / `/bd 1` | 下载指定编号的已解析内容，不重新解析 |
| `下载` / `下载吧` | 下载最近一条已解析内容，不重新解析 |
| `/groupid`（别名 `/群号`） | 查看当前群号，便于配置下载白名单/黑名单 |

- **解析始终可用**：即使群聊没有开启默认下载，也会回复视频信息卡片，并附带「回复「下载」或发送 /bd1」提示。
- **默认下载按群聊控制**：`group_download_mode` 支持 `all`（全部允许）、`whitelist`（仅白名单）、`blacklist`（黑名单禁止），配合 `group_download_list` 群号列表使用；该限制只影响自动下载。
- 未开启默认下载时，用户仍可用 `/bd1` 或回复「下载」使用已解析结果，也可以直接用 `/saveany` 显式下载。
- `private_download_enabled` 控制私聊是否允许默认下载。
- `parse_all_group_messages` 开启后，群聊里不 @ 机器人也会解析视频链接；此时只解析并缓存，回复「下载」或发送 `/bd1` 即可下载。

### 自定义解析文本

配置项 `parse_template` 可以替换解析后的信息卡片文案；留空则使用内置文案。

示例：

```text
{image}
{status}：{title}

作者：{owner}
平台：{platform}
时长：{duration}
播放：{view}
简介：{desc}
```

可用占位符：

| 占位符 | 说明 |
| --- | --- |
| `{image}` | 视频封面；可放在任意位置，不写则不发送封面 |
| `{title}` | 标题 |
| `{owner}` / `{author}` / `{uploader}` | 作者 / UP 主 |
| `{desc}` / `{description}` | 简介（自动截断） |
| `{platform}` | 平台，如 B 站、抖音、YouTube |
| `{duration}` | 时长，如 `3:25` |
| `{view}` / `{play}` | 播放量 |
| `{like}` | 点赞数 |
| `{url}` | 原始链接 |
| `{id}` | 视频 ID |
| `{type}` | 视频 / 番剧 |
| `{status}` | 正在下载 / 视频信息 / 番剧信息 |
| `{date}` | 发布日期 |
| `{note}` | 番剧整季提示 |
| `{index}` / `{episode}` | 番剧集数 |
| `{episodes}` | 番剧总集数 |
| `{ep_title}` | 番剧本集标题 |

模板应用于 B 站视频、番剧和 yt-dlp 视频信息卡片。未知占位符会原样保留，方便发现拼写错误；模板渲染为空时会回退到内置文案。

### 扫码登录支持情况

| 平台 | 扫码登录 | 说明 |
| --- | --- | --- |
| B 站 | 支持 | 使用 B 站 App 扫码，自动保存 B 站 Cookie |
| 微博 | 支持 | 使用微博 App 扫码，自动保存微博 Cookie |
| 抖音 | 尽力支持 | 抖音接口风控较严，失败时会提示，请手动填写 Cookie |
| 小红书、YouTube、TikTok、X、Instagram、Facebook、Vimeo | 不支持 | 页面会提供登录页链接，登录后手动复制 Cookie |

所有平台的 Cookie 都保存在「Cookie 管理」中，可按平台筛选、启用/禁用和调整优先级。

### 抖音提示需要 Cookies 时

抖音的网页端接口经常要求浏览器 Cookie（yt-dlp 会提示 `Fresh cookies ... are needed`），可以这样配置：

1. 在电脑浏览器打开 <https://www.douyin.com/>（登录与否都可以，能正常播放视频即可）。
2. 按 `F12` 打开开发者工具，切换到 Network（网络）面板，刷新页面并点开任意一个请求。
3. 在 Request Headers（请求头）里找到 `Cookie:`，复制整行内容。
4. 在插件管理页「Cookie 输入」中把平台选为「抖音」，粘贴 Cookie 并保存；也可以在「配置插件 → 多平台下载」里填写全局 Cookie（会作为所有平台的兜底）。

也可以把浏览器导出的 Netscape 格式 Cookies 文件路径填到 **Cookies 文件路径**。Cookie 属于敏感信息，请勿分享给他人。

## 支持的平台

| 平台 | 支持的输入 | 说明 |
| --- | --- | --- |
| B 站 | BV 号、av 号、视频/番剧/专栏/动态/收藏夹/合集链接、b23.tv 短链 | 原生 API 解析，支持扫码登录与高清画质 |
| 抖音 | `www.douyin.com/video/...`、`v.douyin.com/...` 分享链接 | yt-dlp 解析，部分作品需要 Cookie |
| 快手 | - | yt-dlp 暂未提供稳定解析，暂不支持 |
| 小红书 | `www.xiaohongshu.com/...`、`xhslink.com/...` | yt-dlp 解析 |
| 微博 | `weibo.com`、`weibo.cn` 视频链接 | yt-dlp 解析 |
| YouTube | `youtube.com`、`youtu.be` | yt-dlp 解析，通常需要代理 |
| TikTok | `tiktok.com` | yt-dlp 解析 |
| X（Twitter） | `x.com`、`twitter.com` | yt-dlp 解析 |
| Instagram / Facebook / Vimeo | 对应站点链接 | yt-dlp 解析 |

- 默认只响应上表中的常见视频平台，避免误下载普通网页；可在配置中开启「允许任意 yt-dlp 支持的站点」。
- 图文/图片作品、直播暂不支持。
- 站点结构经常变化，若某个平台突然失效，通常是 yt-dlp 需要升级：重新安装插件依赖或执行 `pip install -U yt-dlp`。

## 系统与运行环境

- Windows / Linux（x64、arm64）/ macOS：系统已安装的 ffmpeg 会被自动识别（PATH、`/usr/bin`、`/usr/local/bin`、`/snap/bin`、`/opt/homebrew/bin` 等常见位置都会探测）。
- 一键下载仅支持 Windows x64 与 Linux（x64 / arm64）；macOS 及其他系统请用 `brew install ffmpeg` 或系统包管理器安装，再点「重新检测」。
- 下载文件名按 UTF-8 字节数截断，适配 Linux 255 字节的文件名限制。
- 部分平台需要 FFmpeg 合并音视频，建议提前安装或使用页面上的「一键下载 FFmpeg」。

## 消息平台

已声明支持以下 AstrBot 平台适配器：

- `aiocqhttp`：NapCat / LLOneBot 等 OneBot 实现。
- `qq_official`：QQ 官方机器人（WebSocket）。
- `qq_official_webhook`：QQ 官方机器人（Webhook）。
- `telegram`。

QQ 官方机器人接入方式：

1. 在 AstrBot「平台」中添加「QQ 官方机器人（WebSocket）」或「QQ 官方机器人（Webhook）」。官方文档：<https://docs.astrbot.app/platform/qqofficial/websockets.html>、<https://docs.astrbot.app/platform/qqofficial/webhook.html>。
2. 按 AstrBot 文档填写 AppID / AppSecret / Token 等信息并启用适配器。
3. 启用本插件。插件会通过官方适配器发送文本、封面和视频文件。

注意事项：

- QQ 官方机器人群聊需要 @ 机器人；群号是 OpenID，可在群里发送 `/groupid` 查看，再填入下载白名单。
- 官方机器人对主动消息频率和媒体大小有限制，建议按平台限制调整 `max_size_mb`。
- 视频通过适配器的媒体上传接口发送；上传失败通常是平台限制或网络问题，控制台日志会给出原因。

## 配置项

- `download_dir`：视频下载保存目录。留空时使用插件数据目录下的 `downloads`；填写相对路径时也基于插件数据目录解析（不再跟随进程工作目录）。
- `max_size_mb`：允许下载的最大视频大小(MB)，`0` 表示不限制。
- `quality`：B 站默认清晰度：`16`=360P、`32`=480P、`64`=720P、`80`=1080P、`112`=1080P+、`116`=1080P60、`120`=4K、`125`=HDR、`127`=8K。
- `ytdlp_enabled`：是否启用多平台下载，默认开启。
- `ytdlp_proxy`：yt-dlp 使用的代理地址，例如 `http://127.0.0.1:7890`，留空表示直连。
- `ytdlp_cookie`：全局兜底 Cookie 字符串，建议优先在「Cookie 输入」中按平台添加。
- `ytdlp_cookiefile`：Netscape 格式 Cookies 文件路径，相对路径基于插件数据目录。
- `ytdlp_allow_any_site`：允许任意 yt-dlp 支持的站点，默认关闭。
- `group_download_mode`：群聊下载权限模式，`all` / `whitelist` / `blacklist`。
- `group_download_list`：群号列表，白名单/黑名单模式下使用。
- `private_download_enabled`：私聊是否允许下载，默认开启。
- `parse_all_group_messages`：群聊无需 @ 也解析链接（仅解析、不下载），默认关闭。
- `parse_template`：自定义解析文本模板，留空使用内置文案；支持 `{image}` 等占位符。

## 依赖

- `aiohttp`、`quart`、`qrcode[pil]`、`Pillow`：B 站解析、扫码登录与 Web 管理页。
- `yt-dlp`：多平台解析与下载。

## 注意事项

- 请勿泄露 B 站 Cookie 或多平台 Cookie。
- 下载高清视频可能需要登录。
- 部分平台可能不支持视频消息。
- 禁止将视频二次分发，否则版主追责，概不负责！
