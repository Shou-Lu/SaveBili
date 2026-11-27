import asyncio
import base64
import io
import json
import os
import random
import string
import time
from pathlib import Path

import aiohttp
import qrcode
from quart import jsonify, request

from astrbot.api import logger

PLUGIN_NAME = "astrbot_plugin_bili_downloader"
# 所有出站请求都带超时，避免网络异常时挂住事件循环
BILI_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=8, sock_read=10)
QR_LOGIN_TIMEOUT = 180

# 支持扫码登录的平台；其余平台只提供登录页与手动 Cookie 指引
QR_PLATFORMS = {
    "bilibili": {
        "label": "B 站",
        "supported": True,
        "login_url": "https://passport.bilibili.com/login",
        "hint": "使用 B 站 App 扫码，登录后自动保存 Cookie。",
    },
    "weibo": {
        "label": "微博",
        "supported": True,
        "login_url": "https://weibo.com/login.php",
        "hint": "使用微博 App 扫码，登录后自动保存 Cookie。",
    },
    "douyin": {
        "label": "抖音",
        "supported": True,
        "login_url": "https://www.douyin.com/",
        "hint": "使用抖音 App 扫码。抖音接口风控较严，失败时请手动填写 Cookie。",
    },
    "xiaohongshu": {
        "label": "小红书",
        "supported": False,
        "login_url": "https://www.xiaohongshu.com/",
        "hint": "小红书暂不提供稳定的扫码接口，请在浏览器登录后手动复制 Cookie。",
    },
    "youtube": {
        "label": "YouTube",
        "supported": False,
        "login_url": "https://accounts.google.com/ServiceLogin?service=youtube",
        "hint": "YouTube 使用 Google 账号登录，暂不支持扫码；公开视频通常无需 Cookie。",
    },
    "tiktok": {
        "label": "TikTok",
        "supported": False,
        "login_url": "https://www.tiktok.com/login",
        "hint": "TikTok 暂不提供稳定的扫码接口，请在浏览器登录后手动复制 Cookie。",
    },
    "twitter": {
        "label": "X（Twitter）",
        "supported": False,
        "login_url": "https://x.com/login",
        "hint": "X 暂不支持扫码获取 Cookie，请手动填写。",
    },
    "instagram": {
        "label": "Instagram",
        "supported": False,
        "login_url": "https://www.instagram.com/accounts/login/",
        "hint": "Instagram 暂不支持扫码获取 Cookie，请手动填写。",
    },
    "facebook": {
        "label": "Facebook",
        "supported": False,
        "login_url": "https://www.facebook.com/login/",
        "hint": "Facebook 暂不支持扫码获取 Cookie，请手动填写。",
    },
    "vimeo": {
        "label": "Vimeo",
        "supported": False,
        "login_url": "https://vimeo.com/log_in",
        "hint": "Vimeo 暂不支持扫码获取 Cookie，请手动填写。",
    },
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class PluginAPI:
    def __init__(self, plugin):
        self.plugin = plugin
        # platform -> {status, message, image, created}
        self.qr_sessions = {}
        # platform -> asyncio.Task
        self._qr_tasks = {}

    def register(self, context):
        routes = [
            ("/api/qrcode/generate", "handle_qrcode_generate", ["GET"]),
            ("/api/qrcode/status", "handle_qrcode_status", ["GET"]),
            ("/api/stats", "handle_stats", ["GET"]),
            ("/api/cookies", "handle_get_cookies", ["GET"]),
            ("/api/cookies/add", "handle_add_cookie", ["POST"]),
            ("/api/cookies/update", "handle_update_cookie", ["POST"]),
            ("/api/cookies/delete", "handle_delete_cookie", ["POST"]),
            ("/api/cookies/clear", "handle_clear_cookies", ["POST"]),
            ("/api/config", "handle_get_config", ["GET"]),
            ("/api/config/update", "handle_update_config", ["POST"]),
            # 新增 FFmpeg 相关接口
            ("/api/ffmpeg/status", "handle_ffmpeg_status", ["GET"]),
            ("/api/ffmpeg/check", "handle_ffmpeg_check", ["POST"]),
            ("/api/ffmpeg/download", "handle_ffmpeg_download", ["POST"]),
        ]
        for route, handler_name, methods in routes:
            handler = getattr(self, handler_name)
            context.register_web_api(
                f"/{PLUGIN_NAME}{route}",
                handler,
                methods,
                f"Video Manager: {handler_name}",
            )

    async def cancel_tasks(self):
        """插件停止/重载时取消所有扫码轮询任务并关闭连接。"""
        for task in list(self._qr_tasks.values()):
            if task and not task.done():
                task.cancel()
        self._qr_tasks.clear()
        for session in self.qr_sessions.values():
            client = session.pop("_client", None)
            if client is not None:
                try:
                    await client.close()
                except Exception:
                    pass

    # ============ 扫码登录 ============
    @staticmethod
    def _qr_platform() -> str:
        try:
            value = request.args.get("platform", "bilibili")
        except Exception:
            value = "bilibili"
        return str(value or "bilibili").strip().lower()

    async def _cancel_qr_task(self, platform: str) -> None:
        task = self._qr_tasks.pop(platform, None)
        if task and not task.done():
            task.cancel()
        old_session = self.qr_sessions.get(platform)
        if old_session is not None:
            client = old_session.pop("_client", None)
            if client is not None:
                try:
                    await client.close()
                except Exception:
                    pass

    async def handle_qrcode_generate(self):
        platform = self._qr_platform()
        meta = QR_PLATFORMS.get(platform)
        if meta is None:
            return jsonify({
                "success": False,
                "supported": False,
                "platform": platform,
                "message": "未知平台。",
                "login_url": "",
            })
        if not meta["supported"]:
            return jsonify({
                "success": False,
                "supported": False,
                "platform": platform,
                "message": f"{meta['label']}暂不支持自动扫码，请手动填写 Cookie。",
                "login_url": meta["login_url"],
            })

        await self._cancel_qr_task(platform)
        session = {
            "status": "pending",
            "message": "正在生成二维码...",
            "image": "",
            "created": time.time(),
        }
        self.qr_sessions[platform] = session
        try:
            image_url, state = await self._start_qr(platform)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[扫码登录] {platform} 生成二维码失败: {e}")
            session["status"] = "error"
            session["message"] = f"生成二维码失败：{e}"
            return jsonify({
                "success": False,
                "supported": True,
                "platform": platform,
                "message": session["message"],
                "error": str(e),
                "login_url": meta["login_url"],
            })

        session["image"] = image_url
        session["status"] = "waiting"
        session["message"] = "等待扫码"
        session["_client"] = state.get("client")
        task = asyncio.create_task(self._poll_qr(platform, session, state))
        self._qr_tasks[platform] = task
        return jsonify({
            "success": True,
            "supported": True,
            "platform": platform,
            "status": "waiting",
            "message": "等待扫码",
            "image_data_url": image_url,
        })

    async def handle_qrcode_status(self):
        platform = self._qr_platform()
        session = self.qr_sessions.get(platform)
        if session is None:
            meta = QR_PLATFORMS.get(platform) or {}
            return jsonify({
                "success": True,
                "platform": platform,
                "status": "idle",
                "supported": bool(meta.get("supported")),
                "message": meta.get("hint") or "",
            })
        return jsonify({
            "success": True,
            "platform": platform,
            "status": session.get("status", "idle"),
            "supported": True,
            "message": session.get("message", ""),
        })

    async def _start_qr(self, platform: str):
        if platform == "bilibili":
            return await self._start_bilibili_qr()
        if platform == "weibo":
            return await self._start_weibo_qr()
        if platform == "douyin":
            return await self._start_douyin_qr()
        raise RuntimeError("该平台暂不支持扫码登录")

    async def _poll_qr(self, platform: str, session: dict, state: dict):
        deadline = time.time() + QR_LOGIN_TIMEOUT
        try:
            while time.time() < deadline and session.get("status") in ("waiting", "scanned", "pending"):
                await asyncio.sleep(3)
                try:
                    result = await self._poll_platform(platform, state)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(f"[扫码登录] {platform} 轮询失败: {e}")
                    continue

                status = result.get("status")
                if status:
                    session["status"] = status
                if result.get("message"):
                    session["message"] = result["message"]
                if status == "confirmed":
                    cookie = result.get("cookie") or ""
                    if cookie:
                        self._save_platform_cookie(
                            platform, cookie, result.get("remark") or "扫码登录"
                        )
                        session["message"] = "登录成功，Cookie 已保存"
                    else:
                        session["status"] = "error"
                        session["message"] = "登录成功，但未获取到 Cookie"
                    return
                if status in ("expired", "error"):
                    return

            if session.get("status") not in ("confirmed", "error", "expired"):
                session["status"] = "expired"
                session["message"] = "二维码已过期，请重新生成"
        finally:
            session.pop("_client", None)
            close = state.get("close")
            if close:
                try:
                    await close()
                except Exception:
                    pass

    async def _poll_platform(self, platform: str, state: dict):
        if platform == "bilibili":
            return await self._poll_bilibili(state)
        if platform == "weibo":
            return await self._poll_weibo(state)
        if platform == "douyin":
            return await self._poll_douyin(state)
        return {"status": "error", "message": "该平台暂不支持扫码登录"}

    def _save_platform_cookie(self, platform: str, cookie: str, remark: str = "") -> bool:
        cookie = (cookie or "").strip()
        if not cookie:
            return False
        platform = (platform or "bilibili").lower()
        for item in self.plugin.cookies:
            if (
                (item.get("platform") or "bilibili").lower() == platform
                and item.get("cookie") == cookie
            ):
                item["enabled"] = True
                item["remark"] = remark or item.get("remark") or "扫码登录"
                self.plugin._save_cookies()
                return True
        self.plugin.cookies.append({
            "cookie": cookie,
            "remark": remark or "扫码登录",
            "priority": 10,
            "enabled": True,
            "platform": platform,
        })
        self.plugin._save_cookies()
        return True

    # ---------- B 站 ----------
    @staticmethod
    def _make_qr_data_url(text: str) -> str:
        img = qrcode.make(text)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    async def _start_bilibili_qr(self):
        client = aiohttp.ClientSession(timeout=BILI_TIMEOUT)
        try:
            async with client.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                headers={"User-Agent": USER_AGENT},
            ) as resp:
                data = await resp.json(content_type=None)
            if data.get("code") != 0:
                raise RuntimeError(data.get("message") or "生成二维码失败")
            payload = data.get("data") or {}
            qrcode_key = payload.get("qrcode_key")
            url = payload.get("url")
            if not qrcode_key or not url:
                raise RuntimeError("B 站未返回二维码")
            return self._make_qr_data_url(url), {
                "client": client,
                "key": qrcode_key,
                "close": client.close,
            }
        except Exception:
            await client.close()
            raise

    async def _poll_bilibili(self, state: dict) -> dict:
        client = state["client"]
        async with client.get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
            params={"qrcode_key": state["key"]},
            headers={"User-Agent": USER_AGENT},
        ) as resp:
            data = await resp.json(content_type=None)
            code = (data.get("data") or {}).get("code")
            if code == 0:
                cookie = self._extract_cookie_from_response(data, resp)
                return {
                    "status": "confirmed",
                    "cookie": cookie,
                    "remark": "B 站扫码登录",
                }
        if code == 86038:
            return {"status": "expired", "message": "二维码已失效"}
        if code == 86090:
            return {"status": "scanned", "message": "已扫码，请在手机上确认"}
        if code == 86101:
            return {"status": "waiting", "message": "等待扫码"}
        return {"status": "waiting", "message": "等待扫码"}

    def _extract_cookie_from_response(self, data, resp) -> str:
        set_cookies = resp.headers.getall("Set-Cookie", [])
        if set_cookies:
            cookies = []
            for c in set_cookies:
                parts = c.split(";")
                if parts:
                    cookies.append(parts[0].strip())
            if cookies:
                return "; ".join(cookies)
        url = (data.get("data") or {}).get("url", "")
        if "SESSDATA" in url:
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(url).query)
            sessdata = query.get("SESSDATA", [""])[0]
            bili_jct = query.get("bili_jct", [""])[0]
            dedeuserid = query.get("DedeUserID", [""])[0]
            return f"SESSDATA={sessdata}; bili_jct={bili_jct}; DedeUserID={dedeuserid}"
        return ""

    # ---------- 微博 ----------
    async def _start_weibo_qr(self):
        client = aiohttp.ClientSession(
            timeout=BILI_TIMEOUT,
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        )
        callback = f"STK_{int(time.time() * 1000)}"
        try:
            async with client.get(
                "https://login.sina.com.cn/sso/qrcode/image",
                params={"entry": "weibo", "size": "180", "callback": callback},
                headers=self._platform_headers("weibo"),
            ) as resp:
                data = self._parse_jsonp(await resp.text())
            payload = data.get("data") or {}
            qrid = payload.get("qrid")
            image = payload.get("image") or ""
            if not qrid:
                raise RuntimeError(data.get("msg") or "微博未返回二维码")
            if image.startswith("//"):
                image = "https:" + image
            image_url = await self._fetch_image_data_url(client, image, "weibo")
            return image_url or image, {
                "client": client,
                "qrid": qrid,
                "close": client.close,
            }
        except Exception:
            await client.close()
            raise

    async def _poll_weibo(self, state: dict) -> dict:
        client = state["client"]
        callback = f"STK_{int(time.time() * 1000)}"
        async with client.get(
            "https://login.sina.com.cn/sso/qrcode/check",
            params={"entry": "weibo", "qrid": state["qrid"], "callback": callback},
            headers=self._platform_headers("weibo"),
        ) as resp:
            data = self._parse_jsonp(await resp.text())
        retcode = str(data.get("retcode") or "")
        if retcode == "20000000":
            payload = data.get("data") or {}
            alt = payload.get("alt") or ""
            cross_url = payload.get("url") or ""
            if not alt and not cross_url:
                return {"status": "error", "message": "微博扫码成功，但缺少登录凭据"}
            cookie = await self._weibo_finish(state, alt, cross_url)
            if not cookie:
                return {"status": "error", "message": "微博登录失败，未获取到 Cookie"}
            return {"status": "confirmed", "cookie": cookie, "remark": "微博扫码登录"}
        if retcode == "50114004":
            return {"status": "expired", "message": "二维码已失效"}
        if retcode in ("50114002", "50114003"):
            return {"status": "scanned", "message": "已扫码，请在手机上确认"}
        if retcode == "50114001":
            return {"status": "waiting", "message": "等待扫码"}
        return {"status": "waiting", "message": "等待扫码"}

    async def _weibo_finish(self, state: dict, alt: str, cross_url: str = "") -> str:
        client = state["client"]
        headers = self._platform_headers("weibo")
        try:
            if cross_url:
                try:
                    await client.get(cross_url, headers=headers)
                except Exception:
                    pass

            urls = []
            for entry in ("qrcodesso", "miniblog"):
                if not alt:
                    break
                callback = f"STK_{int(time.time() * 1000)}"
                async with client.get(
                    "https://login.sina.com.cn/sso/login.php",
                    params={
                        "entry": entry,
                        "returntype": "TEXT",
                        "crossdomain": "1",
                        "cdult": "3",
                        "domain": "weibo.com",
                        "alt": alt,
                        "savestate": "30",
                        "callback": callback,
                    },
                    headers=headers,
                ) as resp:
                    data = self._parse_jsonp(await resp.text())
                urls = (
                    data.get("crossDomainUrlList")
                    or (data.get("data") or {}).get("crossDomainUrlList")
                    or []
                )
                if urls:
                    break

            for url in urls:
                try:
                    await client.get(url, headers=headers)
                except Exception:
                    continue

            # 再访问一次主站，确保 sessionid / SUB 等写入 CookieJar
            try:
                await client.get("https://weibo.com/", headers=headers)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"[扫码登录] 微博换取 Cookie 失败: {e}")
            return ""
        return self._dump_cookies(client)

    # ---------- 抖音（尽力而为，接口可能触发风控） ----------
    async def _start_douyin_qr(self):
        verify_fp = self._gen_verify_fp()
        client = aiohttp.ClientSession(
            timeout=BILI_TIMEOUT,
            cookie_jar=aiohttp.CookieJar(unsafe=True),
            cookies={"s_v_web_id": verify_fp},
        )
        headers = self._platform_headers("douyin")
        try:
            # 先访问主站拿 ttwid 等基础 Cookie
            try:
                await client.get("https://www.douyin.com/", headers=headers)
            except Exception:
                pass
            params = {
                "service": "https://www.douyin.com",
                "need_logo": "false",
                "need_short_url": "false",
                "passport_jssdk_version": "1.0.20",
                "aid": "6383",
                "account_sdk_source": "sso",
                "sdk_version": "2.2.7",
                "language": "zh",
                "verifyFp": verify_fp,
                "fp": verify_fp,
            }
            async with client.get(
                "https://sso.douyin.com/get_qrcode/",
                params=params,
                headers=headers,
            ) as resp:
                text = await resp.text()
            if not text.lstrip().startswith("{"):
                raise RuntimeError("抖音扫码接口返回了验证页，可能触发了风控")
            data = json.loads(text)
            payload = data.get("data") or {}
            token = payload.get("token")
            image = payload.get("qrcode") or ""
            if not token or not image:
                raise RuntimeError(data.get("message") or "抖音未返回二维码")
            if not image.startswith("data:"):
                image = "data:image/png;base64," + image
            return image, {
                "client": client,
                "token": token,
                "verify_fp": verify_fp,
                "close": client.close,
            }
        except Exception:
            await client.close()
            raise

    async def _poll_douyin(self, state: dict) -> dict:
        client = state["client"]
        params = {
            "service": "https://www.douyin.com",
            "need_logo": "false",
            "need_short_url": "false",
            "passport_jssdk_version": "1.0.20",
            "aid": "6383",
            "account_sdk_source": "sso",
            "sdk_version": "2.2.7",
            "language": "zh",
            "verifyFp": state["verify_fp"],
            "fp": state["verify_fp"],
            "token": state["token"],
        }
        async with client.get(
            "https://sso.douyin.com/check_qrconnect/",
            params=params,
            headers=self._platform_headers("douyin"),
        ) as resp:
            text = await resp.text()
        if not text.lstrip().startswith("{"):
            return {"status": "error", "message": "抖音扫码接口触发了风控，请手动填写 Cookie"}
        data = json.loads(text)
        payload = data.get("data") or {}
        code = str(payload.get("status") or "")
        if code == "1":
            return {"status": "waiting", "message": "等待扫码"}
        if code == "2":
            return {"status": "scanned", "message": "已扫码，请在手机上确认"}
        if code == "5":
            return {"status": "expired", "message": "二维码已失效"}
        if code in ("3", "4") or payload.get("redirect_url"):
            redirect_url = payload.get("redirect_url")
            try:
                if redirect_url:
                    await client.get(redirect_url, headers=self._platform_headers("douyin"))
                await client.get("https://www.douyin.com/", headers=self._platform_headers("douyin"))
            except Exception:
                pass
            cookie = self._dump_cookies(client)
            if not cookie:
                return {"status": "error", "message": "抖音登录成功，但未获取到 Cookie"}
            return {"status": "confirmed", "cookie": cookie, "remark": "抖音扫码登录"}
        return {"status": "waiting", "message": "等待扫码"}

    # ---------- 扫码登录辅助 ----------
    @staticmethod
    def _platform_headers(platform: str) -> dict:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if platform == "weibo":
            headers["Referer"] = "https://weibo.com/"
            headers["Origin"] = "https://weibo.com"
        elif platform == "douyin":
            headers["Referer"] = "https://www.douyin.com/"
            headers["Origin"] = "https://www.douyin.com"
        return headers

    @staticmethod
    def _parse_jsonp(text: str) -> dict:
        text = (text or "").strip()
        start = text.find("(")
        end = text.rfind(")")
        if start != -1 and end > start:
            text = text[start + 1:end]
        return json.loads(text)

    @staticmethod
    def _dump_cookies(client) -> str:
        pairs = {}
        try:
            for cookie in client.cookie_jar:
                if cookie.key:
                    pairs[cookie.key] = cookie.value
        except Exception:
            return ""
        return "; ".join(f"{name}={value}" for name, value in pairs.items())

    @staticmethod
    def _gen_verify_fp() -> str:
        table = "0123456789abcdefghijklmnopqrstuvwxyz"
        number = int(time.time() * 1000)
        base36 = ""
        while number > 0:
            base36 = table[number % 36] + base36
            number //= 36
        chars = string.ascii_letters + string.digits
        rand = "".join(random.choice(chars) for _ in range(36))
        return f"verify_{base36}_{rand}"

    async def _fetch_image_data_url(self, client, url: str, platform: str) -> str:
        if not url:
            return ""
        try:
            async with client.get(url, headers=self._platform_headers(platform)) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.read()
                if not data or len(data) > 2 * 1024 * 1024:
                    return ""
                content_type = (resp.headers.get("content-type") or "image/png").split(";")[0]
                if not content_type.startswith("image/"):
                    content_type = "image/png"
            return f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"
        except Exception:
            return ""

    # ---------- 数据概览 ----------
    @staticmethod
    def _scan_downloads(path: str) -> dict:
        """统计下载目录的文件数与占用大小（粗略，最多扫描 20000 个文件）。"""
        files = 0
        total = 0
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        if not entry.is_file():
                            continue
                        files += 1
                        total += entry.stat().st_size
                    except OSError:
                        continue
                    if files >= 20000:
                        break
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"统计下载目录失败: {e}")
        return {"files": files, "bytes": total}

    async def handle_stats(self):
        try:
            stats = self.plugin.build_stats()
            stats["storage"] = await asyncio.to_thread(
                self._scan_downloads, self.plugin.download_dir
            )
            return jsonify({"success": True, "stats": stats})
        except Exception as e:
            logger.error(f"获取统计数据失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    # ---------- Cookie 管理 ----------
    async def handle_get_cookies(self):
        return jsonify({"success": True, "cookies": self.plugin.cookies})

    async def handle_add_cookie(self):
        data = await request.get_json()
        cookie_str = str(data.get("cookie", "")).strip()
        remark = str(data.get("remark", "")).strip()
        priority = int(data.get("priority", 100))
        enabled = bool(data.get("enabled", True))
        platform = str(data.get("platform") or "bilibili").strip().lower()

        if not cookie_str:
            return jsonify({"success": False, "error": "Cookie 不能为空"})

        if platform == "bilibili" and "=" not in cookie_str:
            cookie_str = f"SESSDATA={cookie_str}"

        self.plugin.cookies.append({
            "cookie": cookie_str,
            "remark": remark or "手动添加",
            "priority": priority,
            "enabled": enabled,
            "platform": platform,
        })
        self.plugin._save_cookies()
        return jsonify({"success": True})

    async def handle_update_cookie(self):
        data = await request.get_json()
        index = data.get("index")
        if index is None or index < 0 or index >= len(self.plugin.cookies):
            return jsonify({"success": False, "error": "无效的索引"})
        updates = {}
        if "cookie" in data:
            updates["cookie"] = str(data["cookie"]).strip()
        if "remark" in data:
            updates["remark"] = str(data["remark"]).strip()
        if "priority" in data:
            updates["priority"] = int(data["priority"])
        if "enabled" in data:
            updates["enabled"] = bool(data["enabled"])
        if "platform" in data:
            updates["platform"] = str(data["platform"] or "bilibili").strip().lower()
        self.plugin.cookies[index].update(updates)
        self.plugin._save_cookies()
        return jsonify({"success": True})

    async def handle_delete_cookie(self):
        data = await request.get_json()
        index = data.get("index")
        if index is None or index < 0 or index >= len(self.plugin.cookies):
            return jsonify({"success": False, "error": "无效的索引"})
        del self.plugin.cookies[index]
        self.plugin._save_cookies()
        return jsonify({"success": True})

    async def handle_clear_cookies(self):
        self.plugin.cookies = []
        self.plugin._save_cookies()
        return jsonify({"success": True})

    # ---------- 配置管理 ----------
    async def handle_get_config(self):
        return jsonify({
            "success": True,
            "config": {
                "download_dir": self.plugin.download_dir,
                "max_size_mb": self.plugin.max_size_mb,
                "quality": self.plugin.quality,
                "ytdlp_enabled": self.plugin.ytdlp_enabled,
                "ytdlp_proxy": self.plugin.ytdlp_proxy,
                "ytdlp_cookie": self.plugin.ytdlp_cookie,
                "ytdlp_cookiefile": self.plugin.ytdlp_cookiefile,
                "ytdlp_allow_any_site": self.plugin.ytdlp_allow_any_site,
                "group_download_mode": self.plugin.group_download_mode,
                "group_download_list": self.plugin.group_download_list,
                "private_download_enabled": self.plugin.private_download_enabled,
                "parse_all_group_messages": self.plugin.parse_all_group_messages,
                "parse_template": self.plugin.parse_template,
            },
            "ytdlp": self.plugin.ytdlp_status(),
        })

    async def handle_update_config(self):
        data = await request.get_json()
        if not data:
            return jsonify({"success": False, "error": "无数据"})
        previous_dir = self.plugin.download_dir
        if "download_dir" in data:
            self.plugin.download_dir = self.plugin._resolve_download_dir(data.get("download_dir"))
        if "max_size_mb" in data:
            self.plugin.max_size_mb = float(data["max_size_mb"])
        if "quality" in data:
            self.plugin.quality = int(data["quality"])
        if "ytdlp_enabled" in data:
            self.plugin.ytdlp_enabled = bool(data["ytdlp_enabled"])
        if "ytdlp_proxy" in data:
            self.plugin.ytdlp_proxy = str(data.get("ytdlp_proxy") or "").strip()
        if "ytdlp_cookie" in data:
            self.plugin.ytdlp_cookie = str(data.get("ytdlp_cookie") or "").strip()
        if "ytdlp_cookiefile" in data:
            self.plugin.ytdlp_cookiefile = str(data.get("ytdlp_cookiefile") or "").strip()
        if "ytdlp_allow_any_site" in data:
            self.plugin.ytdlp_allow_any_site = bool(data["ytdlp_allow_any_site"])
        if "group_download_mode" in data:
            mode = str(data.get("group_download_mode") or "all").lower()
            if mode not in ("all", "whitelist", "blacklist"):
                mode = "all"
            self.plugin.group_download_mode = mode
        if "group_download_list" in data:
            self.plugin.group_download_list = self.plugin._normalize_group_list(
                data.get("group_download_list")
            )
        if "private_download_enabled" in data:
            self.plugin.private_download_enabled = bool(data["private_download_enabled"])
        if "parse_all_group_messages" in data:
            self.plugin.parse_all_group_messages = bool(data["parse_all_group_messages"])
        if "parse_template" in data:
            self.plugin.parse_template = str(data.get("parse_template") or "").strip()
        # 先确认目录可用再落盘，避免保存一个写不进去的路径
        try:
            os.makedirs(self.plugin.download_dir, exist_ok=True)
        except Exception as e:
            self.plugin.download_dir = previous_dir
            logger.error(f"创建下载目录失败: {e}")
            return jsonify({"success": False, "error": f"下载目录不可用: {e}"})
        self.plugin._save_plugin_config()
        return jsonify({"success": True})

    # ---------- FFmpeg 状态与下载 ----------
    async def handle_ffmpeg_status(self):
        return jsonify({
            "success": True,
            "status": self.plugin.ffmpeg_status
        })

    async def handle_ffmpeg_check(self):
        try:
            # 重新扫描 PATH、常见安装路径与插件目录（全异步，不阻塞事件循环）
            found = await self.plugin._detect_ffmpeg()
            return jsonify({
                "success": True,
                "found": bool(found),
                "status": self.plugin.ffmpeg_status,
            })
        except Exception as e:
            logger.error(f"检测 FFmpeg 失败: {e}")
            return jsonify({"success": False, "error": str(e)})

    async def handle_ffmpeg_download(self):
        try:
            # 触发后台异步下载，绝不阻塞当前请求
            await self.plugin.trigger_ffmpeg_download()
            return jsonify({"success": True, "message": "已开始下载 FFmpeg"})
        except Exception as e:
            logger.error(f"触发 FFmpeg 下载失败: {e}")
            return jsonify({"success": False, "error": str(e)})
