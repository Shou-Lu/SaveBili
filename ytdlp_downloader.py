"""yt-dlp 多平台下载封装。

B 站继续走原有的原生 API 解析（番剧、专栏、动态等能力无法用 yt-dlp 平替），
其余平台（抖音、小红书、微博、YouTube、TikTok 等）统一交给 yt-dlp。

yt-dlp 是同步库，所有耗时操作都通过 asyncio.to_thread 放到工作线程执行，
避免阻塞 AstrBot 的事件循环。
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from astrbot.api import logger

try:
    import yt_dlp

    YTDLP_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - 只在依赖缺失/损坏时触发
    yt_dlp = None
    YTDLP_IMPORT_ERROR = exc

# 站点域名 -> 平台标识。只用于识别与展示，真正能否下载由 yt-dlp 决定。
PLATFORM_HOSTS: dict[str, str] = {
    "douyin.com": "douyin",
    "iesdouyin.com": "douyin",
    "xiaohongshu.com": "xiaohongshu",
    "xhslink.com": "xiaohongshu",
    "weibo.com": "weibo",
    "weibo.cn": "weibo",
    "youtube.com": "youtube",
    "youtu.be": "youtube",
    "tiktok.com": "tiktok",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "fb.watch": "facebook",
    "vimeo.com": "vimeo",
    "bilibili.com": "bilibili",
    "b23.tv": "bilibili",
}

PLATFORM_LABELS: dict[str, str] = {
    "bilibili": "B 站",
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "weibo": "微博",
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "twitter": "X（Twitter）",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "vimeo": "Vimeo",
    "ytdlp": "其他站点",
    "generic": "其他站点",
}

SUPPORTED_PLATFORM_TEXT = (
    "抖音、小红书、微博、YouTube、TikTok、X（Twitter）、Instagram、Facebook、Vimeo 等"
)

# 需要先跟随跳转才能拿到作品 ID 的短链域名
SHORT_LINK_HOSTS = {
    "v.douyin.com",
    "xhslink.com",
    "v.xiaohongshu.com",
    "b23.tv",
    "bili2233.cn",
    "bili22.cn",
    "bili23.cn",
    "bili33.cn",
}

# 用户直接粘贴 Cookie 字符串时，按平台写入对应的 Cookie 域。
# yt-dlp 新版本不再接受 http_headers 里的 Cookie，必须用 Netscape 文件。
COOKIE_DOMAINS: dict[str, list[str]] = {
    "douyin": [".douyin.com", ".iesdouyin.com"],
    "xiaohongshu": [".xiaohongshu.com"],
    "weibo": [".weibo.com", ".weibo.cn"],
    "youtube": [".youtube.com", ".google.com"],
    "tiktok": [".tiktok.com"],
    "twitter": [".x.com", ".twitter.com"],
    "instagram": [".instagram.com"],
    "facebook": [".facebook.com"],
    "vimeo": [".vimeo.com"],
}

# 和 main.py 保持一致：只匹配 ASCII URL 字符，避免把后面的中文分享文案吞进去
_URL_RE = re.compile(r"https?://[^\s<>\"'，。；：！？、）)\]】》」』”’]+", re.I)
_URL_TRAILING = " \t\r\n\"'`.,;:!?，。；：！？、）)]}】》」』”’…"

_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "avif", "heic"}
_AUDIO_EXTS = {"m4a", "mp3", "opus", "ogg", "aac", "wav", "flac"}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

PROBE_TIMEOUT = 90
DOWNLOAD_TIMEOUT = 3600


class YtDlpError(RuntimeError):
    """可读的 yt-dlp 下载错误，消息可以直接回给用户。"""


def ytdlp_available() -> bool:
    return yt_dlp is not None


def ytdlp_version() -> str:
    if yt_dlp is None:
        return ""
    try:
        return str(getattr(yt_dlp.version, "__version__", "") or "")
    except Exception:
        return ""


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def detect_platform(url: str) -> Optional[str]:
    """根据域名识别平台，未知站点返回 None。"""
    host = _host(url)
    if not host:
        return None
    for domain, platform in PLATFORM_HOSTS.items():
        if host == domain or host.endswith("." + domain):
            return platform
    return None


def is_supported_url(url: str, allow_any: bool = False) -> bool:
    """是否交给 yt-dlp 处理。

    B 站由上层的原生解析负责，这里只认非 B 站链接；allow_any 打开后
    任何 http(s) 链接都会尝试交给 yt-dlp（由其判断是否支持）。
    """
    platform = detect_platform(url)
    if platform and platform != "bilibili":
        return True
    return bool(allow_any) and bool(_host(url))


def extract_urls(text: str) -> list[str]:
    """从一段消息里提取所有 http(s) 链接，已去掉尾部标点。"""
    results: list[str] = []
    for match in _URL_RE.finditer(str(text or "")):
        url = match.group(0).rstrip(_URL_TRAILING)
        if url and url not in results:
            results.append(url)
    return results


def is_short_link(url: str) -> bool:
    return _host(url) in SHORT_LINK_HOSTS


def normalize_url(url: str) -> str:
    """把抖音常见的分享页地址规整成 yt-dlp 认识的形式。"""
    if not url:
        return url
    host = _host(url)
    if host.endswith("douyin.com") or host.endswith("iesdouyin.com"):
        modal_id = (parse_qs(urlparse(url).query).get("modal_id") or [""])[0]
        if modal_id.isdigit():
            return f"https://www.douyin.com/video/{modal_id}"
        match = re.search(r"/(?:share/)?video/(\d+)", url)
        if match:
            return f"https://www.douyin.com/video/{match.group(1)}"
        match = re.search(r"/(?:share/)?note/(\d+)", url)
        if match:
            return f"https://www.douyin.com/note/{match.group(1)}"
    return url


class _YdlLogger:
    """把 yt-dlp 的日志接到 AstrBot 日志里，方便排查失败原因。"""

    def debug(self, msg: str) -> None:
        text = str(msg)
        if text.startswith("[debug] "):
            return
        logger.debug(f"[yt-dlp] {text}")

    def info(self, msg: str) -> None:
        self.debug(msg)

    def warning(self, msg: str) -> None:
        logger.warning(f"[yt-dlp] {msg}")

    def error(self, msg: str) -> None:
        logger.error(f"[yt-dlp] {msg}")


def _base_opts(
    *,
    out_dir: Optional[Path] = None,
    ffmpeg_path: Optional[str] = None,
    proxy: str = "",
    cookiefile: str = "",
    max_size_mb: float = 0,
    progress_hooks: Optional[list] = None,
) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "no_color": True,
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 20,
        "http_headers": {"User-Agent": _USER_AGENT},
        "logger": _YdlLogger(),
    }

    if out_dir is not None:
        opts.update({
            "outtmpl": str(Path(out_dir) / "%(title).150B [%(id)s].%(ext)s"),
            "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
            "merge_output_format": "mp4/mkv",
            "windowsfilenames": os.name == "nt",
            "continuedl": True,
        })

    if ffmpeg_path:
        opts["ffmpeg_location"] = str(ffmpeg_path)
    if proxy:
        opts["proxy"] = proxy
    if cookiefile:
        opts["cookiefile"] = cookiefile
    if max_size_mb and max_size_mb > 0:
        opts["max_filesize"] = int(max_size_mb * 1024 * 1024)
    if progress_hooks:
        opts["progress_hooks"] = progress_hooks
    return opts


def _translate_error(exc: BaseException) -> YtDlpError:
    """把 yt-dlp 的原始异常翻译成用户能看懂的一句话。"""
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(exc) or exc.__class__.__name__).strip()
    low = msg.lower()

    if "unsupported url" in low:
        return YtDlpError("yt-dlp 暂不支持该链接。")
    if "max-filesize" in low or "larger than max" in low or "file is larger" in low:
        return YtDlpError("视频超过配置的大小限制。")
    if "ffmpeg" in low and ("not installed" in low or "not found" in low):
        return YtDlpError("需要 FFmpeg 合并音视频，请先在插件页面安装或检测 FFmpeg。")
    if any(key in low for key in ("sign in", "log in", "login", "cookies", "account", "private")):
        return YtDlpError("该平台需要登录 Cookies，请在插件配置中填写 Cookie 或 Cookies 文件。")
    if "timed out" in low or "timeout" in low:
        return YtDlpError("请求超时，请检查网络或代理设置。")
    if "http error 404" in low:
        return YtDlpError("页面不存在（HTTP 404），请检查链接是否正确。")
    if "unable to download webpage" in low or "http error 403" in low:
        return YtDlpError("站点拒绝了请求（可能触发风控），请稍后重试或配置 Cookies。")

    if len(msg) > 300:
        msg = msg[:300] + "..."
    return YtDlpError(msg)


def _summary(info: dict, fallback_url: str) -> dict[str, Any]:
    title = (info.get("title") or info.get("fulltitle") or info.get("description") or "").strip()
    uploader = (
        info.get("uploader")
        or info.get("channel")
        or info.get("creator")
        or info.get("uploader_id")
        or ""
    )
    thumbnail = info.get("thumbnail")
    if not thumbnail:
        thumbnails = info.get("thumbnails") or []
        if thumbnails and isinstance(thumbnails[-1], dict):
            thumbnail = thumbnails[-1].get("url")

    webpage_url = info.get("webpage_url") or info.get("original_url") or fallback_url
    platform = detect_platform(webpage_url) or detect_platform(fallback_url)
    if not platform:
        platform = str(info.get("extractor_key") or "ytdlp").lower()

    return {
        "id": str(info.get("id") or ""),
        "title": title or f"{PLATFORM_LABELS.get(platform, platform)}视频",
        "uploader": str(uploader or ""),
        "description": str(info.get("description") or ""),
        "thumbnail": str(thumbnail or ""),
        "duration": info.get("duration"),
        "view": info.get("view_count") or 0,
        "like": info.get("like_count") or 0,
        "upload_date": info.get("upload_date") or "",
        "is_live": bool(info.get("is_live")),
        "platform": platform,
        "webpage_url": webpage_url,
        "download_url": webpage_url,
        "filesize": info.get("filesize") or info.get("filesize_approx") or 0,
        "ext": str(info.get("ext") or ""),
    }


def _first_entry(info: dict) -> tuple[dict, int]:
    """合集/图文作品取第一个条目，并返回条目总数。"""
    if not isinstance(info, dict) or info.get("_type") != "playlist":
        return info, 0
    entries = [entry for entry in (info.get("entries") or []) if isinstance(entry, dict)]
    if not entries:
        raise YtDlpError("该链接没有可下载的内容。")
    return entries[0], len(entries)


def _cookie_file_from_header(cookie: str, url: str) -> Optional[str]:
    """把 `a=b; c=d` 形式的 Cookie 字符串写成 Netscape Cookie 文件。

    yt-dlp 新版本会丢弃 http_headers 里的 Cookie（安全考虑），所以这里按平台
    域名生成临时 Cookie 文件交给它读取。
    """
    pairs: list[tuple[str, str]] = []
    raw = re.sub(r"^\s*cookie\s*:\s*", "", str(cookie or ""), flags=re.I)
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = re.sub(r"[\t\r\n]", "", name.strip())
        value = re.sub(r"[\t\r\n]", "", value.strip())
        if name:
            pairs.append((name, value))
    if not pairs:
        return None

    platform = detect_platform(url) or ""
    domains = list(COOKIE_DOMAINS.get(platform, []))
    if not domains:
        host = _host(url)
        base = ".".join(host.split(".")[-2:]) if host else ""
        if base and "." in base:
            domains = [base if base.startswith(".") else "." + base]
        elif host:
            domains = [host]
    if not domains:
        return None

    expiry = int(time.time()) + 30 * 86400
    lines = ["# Netscape HTTP Cookie File", "# Generated by SaveBili", ""]
    for domain in domains:
        for name, value in pairs:
            lines.append("\t".join([domain, "TRUE", "/", "TRUE", str(expiry), name, value]))

    fd, path = tempfile.mkstemp(prefix="savebili_cookies_", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
        if os.name != "nt":
            os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        return None
    return path


def _prepare_cookie_file(cookie: str, cookiefile: str, url: str) -> tuple[str, Optional[str]]:
    """返回 (交给 yt-dlp 的 cookie 文件, 需要清理的临时文件)。"""
    if cookiefile:
        if not os.path.isfile(cookiefile):
            raise YtDlpError(f"Cookies 文件不存在：{cookiefile}")
        return cookiefile, None
    if cookie:
        temp_file = _cookie_file_from_header(cookie, url)
        if temp_file:
            return temp_file, temp_file
    return "", None


def _cleanup_temp(path: Optional[str]) -> None:
    if not path:
        return
    try:
        os.unlink(path)
    except OSError:
        pass


async def probe(
    url: str,
    *,
    proxy: str = "",
    cookie: str = "",
    cookiefile: str = "",
) -> dict[str, Any]:
    """只解析元信息，不下载。"""
    if not ytdlp_available():
        raise YtDlpError("未安装 yt-dlp，无法使用多平台下载。")

    def _run() -> dict[str, Any]:
        cookie_file, temp_file = _prepare_cookie_file(cookie, cookiefile, url)
        try:
            opts = _base_opts(proxy=proxy, cookiefile=cookie_file)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except YtDlpError:
                raise
            except Exception as exc:
                raise _translate_error(exc) from exc

            if not isinstance(info, dict):
                raise YtDlpError("解析失败：未获取到视频信息。")
            info, count = _first_entry(info)
            summary = _summary(info, url)
            summary["playlist_count"] = count
            if summary["is_live"]:
                raise YtDlpError("暂不支持直播/实时流。")
            return summary
        finally:
            _cleanup_temp(temp_file)

    try:
        return await asyncio.wait_for(asyncio.to_thread(_run), timeout=PROBE_TIMEOUT)
    except asyncio.TimeoutError:
        raise YtDlpError("解析超时，请检查网络或代理设置。")


def _final_path(ydl: Any, info: dict) -> Optional[str]:
    for item in info.get("requested_downloads") or []:
        if isinstance(item, dict) and item.get("filepath"):
            return str(item["filepath"])
    for key in ("filepath", "_filename"):
        if info.get(key):
            return str(info[key])
    try:
        return str(ydl.prepare_filename(info))
    except Exception:
        return None


async def download(
    url: str,
    *,
    out_dir: str,
    max_size_mb: float = 0,
    ffmpeg_path: Optional[str] = None,
    proxy: str = "",
    cookie: str = "",
    cookiefile: str = "",
) -> dict[str, Any]:
    """下载视频，返回文件路径与元信息。"""
    if not ytdlp_available():
        raise YtDlpError("未安装 yt-dlp，无法使用多平台下载。")

    out_path = Path(out_dir)

    def _run() -> dict[str, Any]:
        out_path.mkdir(parents=True, exist_ok=True)
        cookie_file, temp_file = _prepare_cookie_file(cookie, cookiefile, url)
        try:
            opts = _base_opts(
                out_dir=out_path,
                ffmpeg_path=ffmpeg_path,
                proxy=proxy,
                cookiefile=cookie_file,
                max_size_mb=max_size_mb,
            )
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if not isinstance(info, dict):
                        raise YtDlpError("下载失败：未获取到视频信息。")
                    info, _ = _first_entry(info)
                    filepath = _final_path(ydl, info)
            except YtDlpError:
                raise
            except Exception as exc:
                raise _translate_error(exc) from exc

            if not filepath or not Path(filepath).is_file():
                raise YtDlpError("下载完成但未找到视频文件，可能是站点返回了空内容。")

            target = Path(filepath)
            ext = target.suffix.lower().lstrip(".")
            if ext in _IMAGE_EXTS:
                try:
                    target.unlink()
                except OSError:
                    pass
                raise YtDlpError("该作品是图文/图片，不是视频，暂不支持。")
            if ext in _AUDIO_EXTS:
                try:
                    target.unlink()
                except OSError:
                    pass
                raise YtDlpError("只获取到音频流，无法作为视频发送。")

            size = target.stat().st_size
            limit = int(max_size_mb * 1024 * 1024) if max_size_mb and max_size_mb > 0 else 0
            if limit and size > limit:
                try:
                    target.unlink()
                except OSError:
                    pass
                raise YtDlpError(f"视频超过配置的大小限制（{max_size_mb:g} MB）。")

            result = _summary(info, url)
            result.update({
                "path": str(target.resolve()),
                "filesize": size,
                "ext": ext,
            })
            return result
        finally:
            _cleanup_temp(temp_file)

    try:
        return await asyncio.wait_for(asyncio.to_thread(_run), timeout=DOWNLOAD_TIMEOUT)
    except asyncio.TimeoutError:
        raise YtDlpError("下载超时，请稍后重试。")
