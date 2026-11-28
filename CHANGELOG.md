# 更新日志

本项目的重要变更记录在此文件中。

## [1.3.3] - 2026-11-28

按需下载、解析历史与清晰度下拉。

### 新增

- 新增按需下载：解析后回复「下载」或发送 `/bd1`，直接使用缓存结果下载，不重新解析；`/saveany` 作为显式下载可绕过群聊默认下载限制。
- 新增 `/bd list`（`/bd 列表`、`/bd 历史`）查看本会话解析历史，格式为 `1. 标题 + 链接（状态）`。
- Web 管理页的 B 站清晰度改为下拉选择，不再需要手动输入画质代码。

## [1.3.2] - 2026-11-27

自定义解析文本、QQ 官方机器人适配与群聊下载权限。

### 新增

- 声明支持 QQ 官方机器人适配器：`qq_official`（WebSocket）与 `qq_official_webhook`（Webhook）。
- 新增 `parse_template` 自定义解析文本模板，支持 `{image}`（封面）、`{title}`、`{owner}`、`{desc}`、`{platform}`、`{duration}`、`{view}`、`{like}`、`{url}`、`{type}`、`{status}` 等占位符。
- 新增 `/groupid`（别名 `/群号`）指令，便于查看 OpenID 群号并配置下载白名单/黑名单。
- 新增群聊下载权限：`group_download_mode`、`group_download_list`、`private_download_enabled`，解析始终可用，未开启下载的群聊只回复视频信息。
- 新增 `/parse`（别名 `/解析`）仅解析指令；`parse_all_group_messages` 可让群聊无需 @ 也解析链接（仅解析，不下载）。

## [1.3.1] - 2026-11-27

### 变更

- 插件作者统一为「守禄」，仓库地址同步为 <https://github.com/shou-lu/SaveBili>。

## [1.3.0] - 2026-11-27

多平台下载、分平台扫码登录与平台统计。

### 新增

- 新增 yt-dlp 多平台下载：抖音、小红书、微博、YouTube、TikTok、X（Twitter）、Instagram、Facebook、Vimeo 等站点可通过 `/saveany` 或 @机器人 触发；B 站继续使用原生解析，番剧、专栏、动态等能力不受影响。
- 新增多平台扫码登录：B 站、微博、抖音可在「扫码登录」中切换平台扫码；小红书、YouTube、TikTok、X 等平台提供登录页与手动 Cookie 指引。
- Cookie 存储新增 `platform` 字段，旧 B 站 Cookie 自动兼容；「Cookie 管理」支持按平台筛选，多平台 Cookie 互不覆盖。
- 数据概览新增「平台分布」，最近下载记录增加平台列；统计文件新增 `platforms` 字段，旧数据自动归入 B 站。
- 新增多平台配置项：`ytdlp_enabled`、`ytdlp_proxy`、`ytdlp_cookie`、`ytdlp_cookiefile`、`ytdlp_allow_any_site`，可在 Web 管理页「多平台下载」中修改。
- `/saveany` 改为从整条消息中提取链接，支持直接粘贴带分享文案的抖音口令；抖音短链会自动跟随跳转并规整为标准链接。
- 媒体下载统一应用 `max_size_mb` 限制，B 站与多平台下载均生效。

### 变更

- 仓库地址更新：`https://github.com/SATA-F5/SaveBili` → `https://github.com/Shou-Lu/SaveBili`（GitHub 账号改名，旧地址会由 GitHub 自动跳转）。
- 作者名称更改：`SATA-F5` → `守禄`。`main.py` 的 `@register`、`astrbot_plugin.json`、`metadata.yaml` 中的作者与仓库字段均已同步，插件 ID 随之变为 `守禄/astrbot_plugin_bili_downloader`。
- 历史变更记录中的 `SATA-F5` 为旧署名，按"不改写历史"原则保留原文。

## [1.2.2] - 2026-11-07

多平台兼容、发送流程修复与审核合规整改。

### 变更

- FFmpeg 探测改为多路径：`PATH` → `/usr/bin`、`/usr/local/bin`、`/bin`、`/snap/bin`、`/opt/homebrew/bin` 等常见位置 → 用户目录 → 插件目录，并用 `-version` 实际校验。服务环境 PATH 被裁剪时也能识别系统自带的 ffmpeg，不再误判成"未安装"。
- 新增「重新检测」按钮与 `POST /api/ffmpeg/check`；已就绪时隐藏「一键下载」，未就绪时给出对应平台的安装命令提示。
- 自动下载按平台分流：Windows x64、Linux x64 / arm64 分别取对应构建；macOS 与其他系统不再错误地下载 Linux 二进制，改为提示用 `brew`/包管理器安装。
- 文件名按 UTF-8 字节数截断（Linux 上限 255 字节），避免超长中文标题在 Ubuntu 上写文件失败。

### 修复

- 修复「发链接后卡住无反应」：原先在第一个 `yield` 之前调用 `event.stop_event()`，AstrBot 调度器检测到事件已终止后会 `break`，不再恢复该生成器，后续的下载与发送全部不执行。现在改为所有消息 `yield` 完毕后在 `finally` 里调用 `stop_event()`，并补充注释说明原因。
- 修复 `sys.stdout.reconfigure` 在 `pythonw` / 重定向输出等环境下导入即报错的问题。

### 合规

按 AstrBot 插件市场审核规则逐条对齐：

- 日志统一使用 `from astrbot.api import logger`，移除导入期的 `print`，不再触碰 `sys.stdout`。
- 数据目录改用官方的 `StarTools.get_data_dir()`（`data/plugin_data/astrbot_plugin_bili_downloader`），并把旧目录 `saveany_bilibili_downloader` 的 `cookies.json` / `plugin_config.json` / `stats.json` 自动迁移一次。
- FFmpeg 探测由同步 `subprocess.run` 改为 `asyncio.create_subprocess_exec`，`find_ffmpeg()` 改为异步，避免阻塞事件循环。
- 扫码登录相关 HTTP 请求补上超时（`total=15/connect=8/sock_read=10`）。
- 媒体下载仅对 `bilibili.com` 主域附带 Cookie，视频/图片 CDN 域名只带 Referer，避免凭据外发。
- `cookies.json` 在 POSIX 下写入后收紧为 `0600`（迁移过来的文件同样处理）。
- 注册名与 `metadata.yaml` / 目录名统一为 `astrbot_plugin_bili_downloader`。

## [1.2.1] - 2026-11-07

对标 `astrbot_plugin_bili_resolver` 重做消息发送流程，并重做 WebUI。

### 新增

- WebUI 新增「数据概览」页：今日下载、累计下载、成功率、下载目录占用、可用 Cookie、FFmpeg 状态六张指标卡。
- 近 7 天下载趋势柱状图、下载类型分布条，以及最近 12 条下载记录（时间 / 类型 / 标题 / 大小 / 状态）。
- 新增 `GET /api/stats` 接口；统计结果持久化到插件数据目录的 `stats.json`（保留 60 天每日数据与最近 30 条明细）。
- 概览数据每 30 秒自动刷新，也支持手动刷新。
- Vue 改为随插件内置（`pages/bili_login/vendor/vue.global.prod.js`），不再依赖 jsDelivr CDN，国内网络或离线环境下页面也能正常加载。

### 变更

- 移除无用的账密登录：删除侧边栏入口、登录表单及 `/api/login/password` 占位接口。
- WebUI 默认进入「数据概览」页。
- 所有指令/事件处理器改为生成器，用 `yield event.plain_result()` / `yield event.chain_result()` 交给 AstrBot 发送，不再在后台任务里调用 `event.send()`，消息顺序与失败重试由框架统一处理。
- 去掉「已接收您的请求」这条独立提示，文案与封面合并为一张信息卡片，减少一条消息。
- 前文与图片合并进同一条消息链：视频/番剧卡片（封面 + 文案）、动态正文与全部配图都只发一条。
- 封面改为 `Comp.Image.fromURL()` 直接引用，不再下载到临时文件，消除临时文件残留。
- 整季番剧「仅下载第 1 集」的提示并入信息卡片；专栏的标题/摘要与保存路径合并为一条消息。
- 同步注册信息：作者 `SATA-F5`，版本 `1.2.1`，补充仓库地址。
- `_init_.py` 更正为 `__init__.py`。

## [1.2.0] - 2026-10-29

### 变更

- 版本号统一为 `1.2.0`：此前 `astrbot_plugin.json`（1.0.0）、`metadata.yaml`（1.1.9）与代码注册（1.3.5）三处不一致。下方 `1.3.5` 条目作为历史记录保留。
- 默认下载目录由 `./downloads`（相对进程工作目录）改为插件数据目录下的 `downloads`；配置中的相对路径也统一基于插件数据目录解析，留空即使用默认值。
- `author` 与 `repo` 中的不间断连字符（U+2011）改为普通连字符，修复仓库链接无法访问的问题。

### 修复

- 修复 `astrbot_plugin.json` 末尾多余的 `}` 导致的非法 JSON。

### 安全加固

- FFmpeg 下载改为 GitHub 官方源优先，镜像仅作备用，不再默认信任第三方加速镜像。
- 下载后校验文件大小与压缩包完整性（zip 使用 `testzip` 做 CRC 校验），解压时只写入固定目标文件名、不创建归档内路径；解压后实际执行一次 `ffmpeg -version` 校验可执行性，失败则删除文件并报错。

## [1.3.5] - 2026-10-25

### 新增

- 支持 B 站短链识别与解析：`b23.tv`、`bili2233.cn`、`bili22.cn`、`bili23.cn`、`bili33.cn`。
- 支持不带 `http(s)://` 前缀的 B 站链接与短链。
- 短链解析支持多级跳转、HEAD 请求失败后回退 GET，以及 `b23.tv/BVxxx`、`b23.tv/avxxx` 路径兜底。
- `/saveany` 指令和 @机器人 触发均支持短链。

### 变更

- 消息接收改用 AstrBot 内置的 `event.is_at_or_wake_command` 判断：
  - 群聊中仅响应 @机器人 或唤醒词消息；
  - 私聊消息正常响应；
  - 不再自动处理群聊中未 @机器人 的普通 B 站链接。
- 删除旧的 `_is_mentioned()` 自定义 @ 判断逻辑。
- 移除 `bot_qq` 配置项，以及 Web 配置页中的对应输入框。

### 修复

- 修复群聊中未 @机器人 也会自动下载 B 站链接的问题。
- 修复 `www.bilibili.com/...` 等无协议头链接无法识别的问题。
- 修复链接后紧跟中文分享文案时，链接被错误截取的问题。
- 修复链接末尾包含中英文标点或括号时解析失败的问题。

### 优化

- 消息接收和消息内容不再写入日志，改为静默处理。

---

更早版本的更新记录未保留。
