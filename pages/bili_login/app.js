import { TEMPLATE } from './template.js';
const { createApp, ref, reactive, onMounted, onUnmounted, computed } = Vue;

const TYPE_LABELS = {
    video: '视频',
    bangumi: '番剧',
    article: '专栏',
    opus: '动态',
    favlist: '收藏夹',
    collection: '合集',
    douyin: '抖音',
    xiaohongshu: '小红书',
    weibo: '微博',
    youtube: 'YouTube',
    tiktok: 'TikTok',
    twitter: 'X',
    instagram: 'Instagram',
    facebook: 'Facebook',
    vimeo: 'Vimeo',
    ytdlp: '其他站点',
    generic: '其他站点',
};

const PLATFORM_LABELS = {
    bilibili: 'B 站',
    douyin: '抖音',
    xiaohongshu: '小红书',
    weibo: '微博',
    youtube: 'YouTube',
    tiktok: 'TikTok',
    twitter: 'X',
    instagram: 'Instagram',
    facebook: 'Facebook',
    vimeo: 'Vimeo',
    generic: '其他站点',
    ytdlp: '其他站点',
};

const QR_PLATFORMS = [
    { key: 'bilibili', label: 'B 站', supported: true },
    { key: 'weibo', label: '微博', supported: true },
    { key: 'douyin', label: '抖音', supported: true },
    { key: 'xiaohongshu', label: '小红书', supported: false, loginUrl: 'https://www.xiaohongshu.com/' },
    { key: 'youtube', label: 'YouTube', supported: false, loginUrl: 'https://accounts.google.com/ServiceLogin?service=youtube' },
    { key: 'tiktok', label: 'TikTok', supported: false, loginUrl: 'https://www.tiktok.com/login' },
    { key: 'twitter', label: 'X', supported: false, loginUrl: 'https://x.com/login' },
    { key: 'instagram', label: 'Instagram', supported: false, loginUrl: 'https://www.instagram.com/accounts/login/' },
    { key: 'facebook', label: 'Facebook', supported: false, loginUrl: 'https://www.facebook.com/login/' },
    { key: 'vimeo', label: 'Vimeo', supported: false, loginUrl: 'https://vimeo.com/log_in' },
];

const emptyStats = () => ({
    totals: { count: 0, success: 0, failed: 0, bytes: 0 },
    today: { count: 0, success: 0, failed: 0, bytes: 0 },
    days: [],
    types: {},
    platforms: {},
    recent: [],
    success_rate: 0,
    storage: { files: 0, bytes: 0 },
    cookies: { enabled: 0, total: 0 },
});

createApp({
    setup() {
        const bridge = window.AstrBotPluginPage;
        const activeSection = ref('dashboard'); // dashboard | qrcode | cookie-input | cookie-manage | config
        const statusText = ref('数据每 30 秒自动刷新');
        const hasCookie = ref(false);
        const isLoading = ref(false);
        const showClearConfirm = ref(false);
        const clearTargetIndex = ref(null);
        const showClearAllConfirm = ref(false);

        // 数据概览
        const stats = ref(emptyStats());
        const statsLoading = ref(false);

        // FFmpeg 状态
        const ffmpegStatus = ref({ status: 'idle', message: '尚未检测 FFmpeg' });

        // Toast 通知
        const toastMessage = ref('');
        const toastVisible = ref(false);
        let toastTimer = null;
        const showToast = (msg) => {
            toastMessage.value = msg;
            toastVisible.value = true;
            if (toastTimer) clearTimeout(toastTimer);
            toastTimer = setTimeout(() => { toastVisible.value = false; }, 2500);
        };
        // 扫码
        const qrUrl = ref('');
        const qrPlatform = ref('bilibili');
        const qrStatus = ref('idle');
        const qrMessage = ref('');
        const qrSupported = ref(true);
        const qrLoginUrl = ref('');
        let qrPollTimer = null;
        let statsTimer = null;
        // Cookie 输入
        const manualCookie = reactive({ cookie: '', remark: '', priority: 10, enabled: true, platform: 'bilibili' });
        // Cookie 列表
        const cookies = ref([]);
        const cookieFilter = ref('all');
        // 配置
        const configForm = reactive({
            download_dir: '',
            max_size_mb: 2000,
            quality: 80,
            ytdlp_enabled: true,
            ytdlp_proxy: '',
            ytdlp_cookie: '',
            ytdlp_cookiefile: '',
            ytdlp_allow_any_site: false,
            group_download_mode: 'all',
            group_download_list: '',
            private_download_enabled: true,
            parse_all_group_messages: false,
        });
        const configLoading = ref(false);
        const ytdlpInfo = ref({ available: false, version: '', platforms: '' });
        const apiGet = (path, params) => bridge.apiGet(path, params);
        const apiPost = (path, data) => bridge.apiPost(path, data);

        // ---------- 格式化 & 图表 ----------
        const formatBytes = (bytes) => {
            const n = Number(bytes) || 0;
            if (n < 1024) return n + ' B';
            const units = ['KB', 'MB', 'GB', 'TB'];
            let value = n;
            let idx = -1;
            do {
                value /= 1024;
                idx += 1;
            } while (value >= 1024 && idx < units.length - 1);
            return value.toFixed(value >= 10 ? 0 : 1) + ' ' + units[idx];
        };
        const formatTime = (ts) => {
            if (!ts) return '-';
            const d = new Date(ts * 1000);
            const pad = (x) => String(x).padStart(2, '0');
            return pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
        };
        const typeLabel = (key) => TYPE_LABELS[key] || key || '其他';
        const platformLabel = (key) => PLATFORM_LABELS[key] || key || '其他';
        const platformOf = (c) => (c && (c.platform || 'bilibili')) || 'bilibili';
        const platformOptions = computed(() => {
            const keys = ['bilibili', 'douyin', 'weibo', 'xiaohongshu', 'youtube', 'tiktok', 'twitter', 'instagram', 'facebook', 'vimeo'];
            return keys.map((key) => ({ key, label: PLATFORM_LABELS[key] || key }));
        });
        const qrHint = computed(() => {
            const item = QR_PLATFORMS.find((p) => p.key === qrPlatform.value);
            if (!item || !item.supported) return '该平台暂不支持自动扫码，请在浏览器登录后手动复制 Cookie。';
            if (qrPlatform.value === 'douyin') return '使用抖音 App 扫码。抖音接口风控较严，失败时请手动填写 Cookie。';
            if (qrPlatform.value === 'weibo') return '使用微博 App 扫码，登录后自动保存 Cookie。';
            return '使用 B 站 App 扫码，登录后自动保存 Cookie。';
        });
        const hasPlatformCookie = (platform) => cookies.value.some((c) => c.enabled && platformOf(c) === platform);
        const typeRows = computed(() => {
            const entries = Object.entries(stats.value.types || {})
                .filter(([, count]) => Number(count) > 0)
                .sort((a, b) => b[1] - a[1]);
            const max = entries.length ? entries[0][1] : 1;
            return entries.map(([key, count]) => ({
                key,
                label: typeLabel(key),
                count,
                pct: Math.max(6, Math.round((count / max) * 100)),
            }));
        });
        const platformRows = computed(() => {
            const entries = Object.entries(stats.value.platforms || {})
                .filter(([, count]) => Number(count) > 0)
                .sort((a, b) => b[1] - a[1]);
            const max = entries.length ? entries[0][1] : 1;
            return entries.map(([key, count]) => ({
                key,
                label: platformLabel(key),
                count,
                pct: Math.max(6, Math.round((count / max) * 100)),
            }));
        });
        const maxDayCount = computed(() => {
            const counts = (stats.value.days || []).map((d) => Number(d.count) || 0);
            return Math.max(1, ...counts);
        });
        const barHeight = (count) => {
            const c = Number(count) || 0;
            if (c === 0) return '3%';
            return Math.max(8, Math.round((c / maxDayCount.value) * 100)) + '%';
        };
        const ffmpegHint = computed(() => {
            const tag = (ffmpegStatus.value && ffmpegStatus.value.platform) || '';
            if (tag === 'linux') return 'Ubuntu/Debian：sudo apt install ffmpeg；CentOS/RHEL：sudo dnf install ffmpeg。装好后点“重新检测”。';
            if (tag === 'darwin') return 'macOS：brew install ffmpeg（本插件不自动下载 macOS 二进制）。';
            if (tag === 'windows') return 'Windows：winget install ffmpeg，或直接使用上方按钮下载。';
            return '请用系统包管理器安装 ffmpeg，然后点“重新检测”。';
        });

        // ---------- 数据概览 ----------
        const loadStats = async () => {
            try {
                const data = await apiGet('api/stats');
                if (data && data.success && data.stats) {
                    stats.value = Object.assign(emptyStats(), data.stats);
                }
            } catch (e) { console.error(e); }
        };
        const refreshStats = async () => {
            statsLoading.value = true;
            try {
                await loadStats();
                statusText.value = '数据已刷新';
            } finally {
                statsLoading.value = false;
            }
        };

        // 状态加载
        const loadStatus = async () => {
            try {
                const data = await apiGet('api/cookies');
                cookies.value = data.cookies || [];
                hasCookie.value = cookies.value.some(c => c.enabled && platformOf(c) === 'bilibili');
            } catch (e) { console.error(e); }
        };
        // 扫码
        const clearQrPolling = () => {
            if (qrPollTimer) clearInterval(qrPollTimer);
            qrPollTimer = null;
        };
        const qrPlatformMeta = (key) => QR_PLATFORMS.find((p) => p.key === key);
        const selectQrPlatform = async (key) => {
            qrPlatform.value = key;
            clearQrPolling();
            qrUrl.value = '';
            qrStatus.value = 'idle';
            qrMessage.value = '';
            qrLoginUrl.value = '';
            qrSupported.value = true;
            const meta = qrPlatformMeta(key);
            if (!meta || !meta.supported) {
                qrSupported.value = false;
                qrLoginUrl.value = meta ? meta.loginUrl : '';
                qrStatus.value = 'unsupported';
                qrMessage.value = meta ? meta.hint : '该平台暂不支持自动扫码。';
                return;
            }
            if (hasPlatformCookie(key)) {
                qrStatus.value = 'has_cookie';
                qrMessage.value = `已有可用的 ${meta.label} Cookie，可直接下载；需要换账号时再生成二维码。`;
                return;
            }
            await generateQR();
        };
        const openQrSection = () => {
            activeSection.value = 'qrcode';
            return selectQrPlatform(qrPlatform.value);
        };
        const generateQR = async () => {
            clearQrPolling();
            isLoading.value = true;
            qrUrl.value = '';
            qrStatus.value = 'loading';
            qrMessage.value = '正在生成二维码...';
            statusText.value = '正在生成二维码...';
            try {
                const data = await apiGet('api/qrcode/generate', { platform: qrPlatform.value });
                if (!data.success) {
                    qrSupported.value = data.supported !== false;
                    qrLoginUrl.value = data.login_url || qrLoginUrl.value;
                    qrStatus.value = data.supported === false ? 'unsupported' : 'error';
                    qrMessage.value = data.error || data.message || '生成二维码失败';
                    statusText.value = qrMessage.value;
                    return;
                }
                qrSupported.value = true;
                qrUrl.value = data.image_data_url;
                qrStatus.value = data.status || 'waiting';
                qrMessage.value = data.message || '等待扫码';
                statusText.value = qrMessage.value;
                startQrPolling();
            } catch (e) {
                qrStatus.value = 'error';
                qrMessage.value = '请求异常：' + e.message;
                statusText.value = qrMessage.value;
            } finally {
                isLoading.value = false;
            }
        };
        const startQrPolling = () => {
            clearQrPolling();
            qrPollTimer = setInterval(async () => {
                try {
                    const data = await apiGet('api/qrcode/status', { platform: qrPlatform.value });
                    if (!data.success) return;
                    qrStatus.value = data.status || 'idle';
                    qrMessage.value = data.message || '';
                    if (['confirmed', 'expired', 'error', 'unsupported'].includes(qrStatus.value)) {
                        clearQrPolling();
                        if (qrStatus.value === 'confirmed') {
                            hasCookie.value = true;
                            statusText.value = '登录成功！Cookie 已保存';
                            showToast('登录成功');
                            await loadStatus();
                            await loadStats();
                        } else {
                            statusText.value = qrMessage.value || qrStatus.value;
                        }
                    }
                } catch (e) { console.error(e); }
            }, 2500);
        };
        // 手动添加 Cookie
        const addManualCookie = async () => {
            if (!manualCookie.cookie) {
                statusText.value = 'Cookie 不能为空';
                return;
            }
            try {
                const data = await apiPost('api/cookies/add', {
                    cookie: manualCookie.cookie,
                    remark: manualCookie.remark,
                    priority: manualCookie.priority,
                    enabled: manualCookie.enabled,
                    platform: manualCookie.platform,
                });
                if (data.success) {
                    statusText.value = 'Cookie 添加成功';
                    showToast('Cookie 添加成功');
                    manualCookie.cookie = '';
                    manualCookie.remark = '';
                    manualCookie.priority = 10;
                    manualCookie.enabled = true;
                    await loadStatus();
                    await loadStats();
                } else {
                    statusText.value = '添加失败：' + (data.error || '未知错误');
                }
            } catch (e) {
                statusText.value = '请求异常：' + e.message;
            }
        };
        // Cookie 管理
        const toggleCookie = async (index) => {
            const c = cookies.value[index];
            const data = await apiPost('api/cookies/update', {
                index,
                enabled: !c.enabled,
            });
            if (data.success) {
                await loadStatus();
                await loadStats();
                showToast(c.enabled ? '已禁用该 Cookie' : '已启用该 Cookie');
            }
        };
        const updatePriority = async (index, priority) => {
            const data = await apiPost('api/cookies/update', {
                index,
                priority: parseInt(priority) || 100,
            });
            if (data.success) {
                await loadStatus();
                showToast('优先级已更新');
            }
        };
        const requestDeleteCookie = (index) => {
            clearTargetIndex.value = index;
            showClearConfirm.value = true;
        };
        const confirmDeleteCookie = async () => {
            showClearConfirm.value = false;
            if (clearTargetIndex.value === null) return;
            const data = await apiPost('api/cookies/delete', { index: clearTargetIndex.value });
            if (data.success) {
                statusText.value = 'Cookie 已删除';
                showToast('Cookie 已删除');
                clearTargetIndex.value = null;
                await loadStatus();
                await loadStats();
            }
        };
        const cancelDeleteCookie = () => {
            showClearConfirm.value = false;
            clearTargetIndex.value = null;
        };
        const requestClearAll = () => {
            showClearAllConfirm.value = true;
        };
        const confirmClearAll = async () => {
            showClearAllConfirm.value = false;
            const data = await apiPost('api/cookies/clear', {});
            if (data.success) {
                statusText.value = '所有 Cookie 已清除';
                showToast('所有 Cookie 已清除');
                await loadStatus();
                await loadStats();
            }
        };
        const cancelClearAll = () => {
            showClearAllConfirm.value = false;
        };
        // 配置
        const loadConfig = async () => {
            const data = await apiGet('api/config');
            if (data.success) {
                configForm.download_dir = data.config.download_dir;
                configForm.max_size_mb = data.config.max_size_mb;
                configForm.quality = data.config.quality;
                configForm.ytdlp_enabled = data.config.ytdlp_enabled !== false;
                configForm.ytdlp_proxy = data.config.ytdlp_proxy || '';
                configForm.ytdlp_cookie = data.config.ytdlp_cookie || '';
                configForm.ytdlp_cookiefile = data.config.ytdlp_cookiefile || '';
                configForm.ytdlp_allow_any_site = data.config.ytdlp_allow_any_site === true;
                configForm.group_download_mode = data.config.group_download_mode || 'all';
                configForm.group_download_list = (data.config.group_download_list || []).join('\n');
                configForm.private_download_enabled = data.config.private_download_enabled !== false;
                configForm.parse_all_group_messages = data.config.parse_all_group_messages === true;
                if (data.ytdlp) ytdlpInfo.value = data.ytdlp;
            }
        };
        const saveConfig = async () => {
            configLoading.value = true;
            try {
                const data = await apiPost('api/config/update', {
                    download_dir: configForm.download_dir,
                    max_size_mb: configForm.max_size_mb,
                    quality: configForm.quality,
                    ytdlp_enabled: configForm.ytdlp_enabled,
                    ytdlp_proxy: configForm.ytdlp_proxy,
                    ytdlp_cookie: configForm.ytdlp_cookie,
                    ytdlp_cookiefile: configForm.ytdlp_cookiefile,
                    ytdlp_allow_any_site: configForm.ytdlp_allow_any_site,
                    group_download_mode: configForm.group_download_mode,
                    group_download_list: configForm.group_download_list,
                    private_download_enabled: configForm.private_download_enabled,
                    parse_all_group_messages: configForm.parse_all_group_messages,
                });
                if (data.success) {
                    statusText.value = '配置已保存';
                    showToast('配置已保存');
                    await loadStats();
                } else {
                    statusText.value = '保存失败：' + (data.error || '未知错误');
                }
            } catch (e) {
                statusText.value = '请求异常：' + e.message;
            } finally {
                configLoading.value = false;
            }
        };

        // ---------- FFmpeg ----------
        const checkingFFmpeg = ref(false);
        const loadFFmpegStatus = async () => {
            try {
                const data = await apiGet('api/ffmpeg/status');
                if (data.success) {
                    ffmpegStatus.value = data.status;
                }
            } catch (e) { console.error(e); }
        };

        const checkFFmpeg = async () => {
            checkingFFmpeg.value = true;
            try {
                const data = await apiPost('api/ffmpeg/check', {});
                if (data.success) {
                    ffmpegStatus.value = data.status;
                    statusText.value = data.found ? '已检测到 FFmpeg' : '仍未检测到 FFmpeg';
                    showToast(data.found ? '已检测到 FFmpeg' : '仍未检测到 FFmpeg');
                    await loadStats();
                } else {
                    showToast(data.error || '检测失败');
                }
            } catch (e) {
                showToast('检测异常：' + e.message);
            } finally {
                checkingFFmpeg.value = false;
            }
        };

        const downloadFFmpeg = async () => {
            ffmpegStatus.value = { status: 'downloading', message: '正在下载中...' };
            try {
                const data = await apiPost('api/ffmpeg/download', {});
                if (data.success) {
                    showToast('下载任务已启动，请耐心等待');
                    const timer = setInterval(async () => {
                        await loadFFmpegStatus();
                        if (ffmpegStatus.value.status !== 'downloading') {
                            clearInterval(timer);
                            if (ffmpegStatus.value.status === 'ready') showToast('FFmpeg 配置成功');
                            else showToast('下载失败，请查看日志');
                            await loadStats();
                        }
                    }, 3000);
                } else {
                    showToast(data.error || '启动下载失败');
                    await loadFFmpegStatus();
                }
            } catch (e) {
                showToast('请求异常：' + e.message);
                await loadFFmpegStatus();
            }
        };

        onMounted(async () => {
            await Promise.all([loadStatus(), loadConfig(), loadFFmpegStatus(), loadStats()]);
            statsTimer = setInterval(loadStats, 30000);
            if (cookies.value.length === 0) {
                activeSection.value = 'qrcode';
                await generateQR();
            }
        });
        onUnmounted(() => {
            clearQrPolling();
            if (toastTimer) clearTimeout(toastTimer);
            if (statsTimer) clearInterval(statsTimer);
        });
        return {
            activeSection,
            statusText,
            qrUrl,
            qrPlatform,
            qrStatus,
            qrMessage,
            qrSupported,
            qrLoginUrl,
            qrPlatforms: QR_PLATFORMS,
            qrHint,
            isLoading,
            manualCookie,
            cookies,
            cookieFilter,
            platformOptions,
            configForm,
            configLoading,
            ytdlpInfo,
            showClearConfirm,
            showClearAllConfirm,
            toastMessage,
            toastVisible,
            ffmpegStatus,
            stats,
            statsLoading,
            typeRows,
            platformRows,
            barHeight,
            ffmpegHint,
            checkingFFmpeg,
            formatBytes,
            formatTime,
            typeLabel,
            platformLabel,
            platformOf,
            generateQR,
            selectQrPlatform,
            openQrSection,
            addManualCookie,
            toggleCookie,
            updatePriority,
            requestDeleteCookie,
            confirmDeleteCookie,
            cancelDeleteCookie,
            requestClearAll,
            confirmClearAll,
            cancelClearAll,
            saveConfig,
            downloadFFmpeg,
            checkFFmpeg,
            refreshStats,
        };
    },
    template: TEMPLATE,
}).mount('#app');
