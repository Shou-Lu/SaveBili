const ASCII_ART = `
       ________ __    _____    __                  __   _        
      / ____/ //_/   / ___/   / /_   __  __   ____/ /  (_)  ____ 
     / / __/ ,<      \\__ \\   / __/  / / / /  / __  /  / /  / __ \\
    / /_/ / /| |    ___/ /  / /_   / /_/ /  / /_/ /  / /  / /_/ /
    \\____/_/ |_|   /____/   \\__/   \\__,_/   \\__,_/  /_/   \\____/ 
`;

export const TEMPLATE = `
<div class="manager-container">
    <aside class="sidebar">
        <div class="sidebar-title">SaveBili</div>
        <div class="nav-item" :class="{ active: activeSection === 'dashboard' }" @click="activeSection = 'dashboard'">数据概览</div>
        <div class="nav-item" :class="{ active: activeSection === 'qrcode' }" @click="openQrSection">扫码登录</div>
        <div class="nav-item" :class="{ active: activeSection === 'cookie-input' }" @click="activeSection = 'cookie-input'">Cookie 输入</div>
        <div class="nav-item" :class="{ active: activeSection === 'cookie-manage' }" @click="activeSection = 'cookie-manage'">Cookie 管理</div>
        <div class="nav-item" :class="{ active: activeSection === 'config' }" @click="activeSection = 'config'">配置插件</div>
    </aside>
    <main class="content">
        <div class="status-bar">{{ statusText }}</div>

        <!-- 数据概览 -->
        <section v-if="activeSection === 'dashboard'" class="dashboard">
            <div class="section-head">
                <h2>数据概览</h2>
                <button class="ghost" @click="refreshStats" :disabled="statsLoading">{{ statsLoading ? '刷新中...' : '刷新数据' }}</button>
            </div>

            <div class="stat-grid">
                <div class="stat-card">
                    <div class="stat-label">今日下载</div>
                    <div class="stat-value">{{ stats.today.count }}</div>
                    <div class="stat-sub">成功 {{ stats.today.success }} · 失败 {{ stats.today.failed }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">累计下载</div>
                    <div class="stat-value">{{ stats.totals.count }}</div>
                    <div class="stat-sub">累计流量 {{ formatBytes(stats.totals.bytes) }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">成功率</div>
                    <div class="stat-value">{{ stats.success_rate }}<span class="stat-unit">%</span></div>
                    <div class="stat-sub">成功 {{ stats.totals.success }} · 失败 {{ stats.totals.failed }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">下载目录</div>
                    <div class="stat-value">{{ stats.storage.files }}<span class="stat-unit">个文件</span></div>
                    <div class="stat-sub">占用 {{ formatBytes(stats.storage.bytes) }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">可用 Cookie</div>
                    <div class="stat-value">{{ stats.cookies.enabled }}<span class="stat-unit">/ {{ stats.cookies.total }}</span></div>
                    <div class="stat-sub">B 站 {{ (stats.cookies.platforms || {}).bilibili || 0 }} · 其他平台 {{ stats.cookies.enabled - ((stats.cookies.platforms || {}).bilibili || 0) }}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">FFmpeg</div>
                    <div class="stat-value stat-small" :class="ffmpegStatus.status === 'ready' ? 'ok' : 'warn'">
                        {{ ffmpegStatus.status === 'ready' ? '就绪' : (ffmpegStatus.status === 'downloading' ? '下载中' : '未就绪') }}
                    </div>
                    <div class="stat-sub">{{ ffmpegStatus.message }}</div>
                </div>
            </div>

            <div class="panel-grid">
                <div class="glass-card">
                    <h2>近 7 天下载趋势</h2>
                    <div class="chart">
                        <div v-for="d in stats.days" :key="d.date" class="chart-col">
                            <div class="chart-bar-wrap" :title="d.date + '：' + d.count + ' 次'">
                                <div class="chart-bar" :style="{ height: barHeight(d.count) }"></div>
                            </div>
                            <div class="chart-value">{{ d.count }}</div>
                            <div class="chart-label">{{ d.label }}</div>
                        </div>
                    </div>
                </div>

                <div class="glass-card">
                    <h2>内容类型</h2>
                    <div v-if="typeRows.length === 0" class="empty">暂无下载数据</div>
                    <div v-for="t in typeRows" :key="t.key" class="type-row">
                        <span class="type-name">{{ t.label }}</span>
                        <div class="type-track"><div class="type-fill" :style="{ width: t.pct + '%' }"></div></div>
                        <span class="type-count">{{ t.count }}</span>
                    </div>
                </div>

                <div class="glass-card">
                    <h2>平台分布</h2>
                    <div v-if="platformRows.length === 0" class="empty">暂无下载数据</div>
                    <div v-for="p in platformRows" :key="p.key" class="type-row">
                        <span class="type-name">{{ p.label }}</span>
                        <div class="type-track"><div class="type-fill" :style="{ width: p.pct + '%' }"></div></div>
                        <span class="type-count">{{ p.count }}</span>
                    </div>
                </div>
            </div>

            <div class="glass-card">
                <h2>最近下载</h2>
                <table class="recent-table" v-if="stats.recent.length > 0">
                    <thead>
                        <tr><th>时间</th><th>平台</th><th>类型</th><th>标题</th><th>大小</th><th>状态</th></tr>
                    </thead>
                    <tbody>
                        <tr v-for="(r, i) in stats.recent" :key="i">
                            <td class="mono">{{ formatTime(r.ts) }}</td>
                            <td><span class="platform-badge">{{ platformLabel(r.platform) }}</span></td>
                            <td>{{ typeLabel(r.type) }}</td>
                            <td class="title-cell" :title="r.title">{{ r.title || '（无标题）' }}</td>
                            <td class="mono">{{ r.bytes ? formatBytes(r.bytes) : '-' }}</td>
                            <td><span class="pill" :class="r.ok ? 'ok' : 'bad'">{{ r.ok ? '成功' : '失败' }}</span></td>
                        </tr>
                    </tbody>
                </table>
                <div v-else class="empty">还没有下载记录，发个视频链接试试</div>
            </div>
        </section>

        <!-- 扫码登录 -->
        <section v-if="activeSection === 'qrcode'">
            <div class="glass-card">
                <h2>扫码登录</h2>
                <div class="platform-tabs">
                    <button
                        v-for="p in qrPlatforms"
                        :key="p.key"
                        class="ghost platform-tab"
                        :class="{ active: qrPlatform === p.key }"
                        @click="selectQrPlatform(p.key)"
                    >{{ p.label }}</button>
                </div>
                <p class="hint">{{ qrHint }}</p>
                <div v-if="qrSupported">
                    <div v-if="qrUrl" class="qr-box">
                        <img :src="qrUrl" alt="二维码">
                    </div>
                    <p class="hint" v-if="qrMessage">{{ qrMessage }}</p>
                    <button @click="generateQR" :disabled="isLoading">{{ isLoading ? '生成中...' : '重新生成二维码' }}</button>
                    <div><a v-if="qrStatus === 'error' && qrLoginUrl" :href="qrLoginUrl" target="_blank" rel="noopener" class="login-link">打开登录页</a></div>
                </div>
                <div v-else>
                    <p class="hint">{{ qrMessage }}</p>
                    <a v-if="qrLoginUrl" :href="qrLoginUrl" target="_blank" rel="noopener" class="login-link">打开登录页</a>
                </div>
                <p class="hint">扫码成功后可在「Cookie 管理」查看对应平台的 Cookie。</p>
            </div>
        </section>

        <!-- Cookie 输入 -->
        <section v-if="activeSection === 'cookie-input'">
            <div class="form-group">
                <h2>手动添加 Cookie</h2>
                <label>平台</label>
                <select v-model="manualCookie.platform">
                    <option v-for="p in platformOptions" :key="p.key" :value="p.key">{{ p.label }}</option>
                </select>
                <label>Cookie 字符串</label>
                <textarea v-model="manualCookie.cookie" rows="4" placeholder="粘贴对应平台的 Cookie 字符串；B 站也可以只填 SESSDATA 值"></textarea>
                <label>备注</label>
                <input v-model="manualCookie.remark" type="text" placeholder="例如：大会员账号 / 抖音小号">
                <label>优先级（数字越小越优先）</label>
                <input v-model="manualCookie.priority" type="number" min="1" max="999">
                <label>
                    <input type="checkbox" v-model="manualCookie.enabled"> 启用
                </label>
                <button @click="addManualCookie">添加 Cookie</button>
            </div>
        </section>

        <!-- Cookie 管理 -->
        <section v-if="activeSection === 'cookie-manage'">
            <div class="glass-card">
                <h2>Cookie 管理</h2>
                <label>平台筛选</label>
                <select v-model="cookieFilter">
                    <option value="all">全部平台</option>
                    <option v-for="p in platformOptions" :key="p.key" :value="p.key">{{ p.label }}</option>
                </select>
                <button class="danger" @click="requestClearAll" v-if="cookies.length > 0">清除全部 Cookie</button>
                <div v-if="cookies.length === 0" class="empty">暂无 Cookie</div>
                <div
                    v-for="(c, index) in cookies"
                    :key="index"
                    class="cookie-item"
                    v-show="cookieFilter === 'all' || platformOf(c) === cookieFilter"
                >
                    <div class="cookie-info">
                        <div class="cookie-remark">
                            <span class="platform-badge">{{ platformLabel(platformOf(c)) }}</span>
                            {{ c.remark || '未命名' }}
                        </div>
                        <div class="cookie-preview">{{ c.cookie.substring(0, 50) }}...</div>
                        <div class="cookie-meta">
                            <label>优先级: <input type="number" :value="c.priority" @change="updatePriority(index, $event.target.value)"></label>
                            <label><input type="checkbox" :checked="c.enabled" @change="toggleCookie(index)"> 启用</label>
                        </div>
                    </div>
                    <button class="danger" @click="requestDeleteCookie(index)">删除</button>
                </div>
            </div>
        </section>

        <!-- 配置插件 -->
        <section v-if="activeSection === 'config'">
            <div class="form-group">
                <h2>配置插件</h2>
                <label>下载目录</label>
                <input v-model="configForm.download_dir" type="text">
                <label>最大文件大小 (MB)</label>
                <input v-model="configForm.max_size_mb" type="number" min="1">
                <label>画质代码（B 站）</label>
                <input v-model="configForm.quality" type="number" min="1">
            </div>

            <div class="form-group" style="margin-top: 20px;">
                <h2>多平台下载（yt-dlp）</h2>
                <p class="hint">
                    抖音、小红书、微博、YouTube、TikTok、X、Instagram 等站点由 yt-dlp 解析。
                    B 站仍然使用原生解析，不受这里影响。
                </p>
                <div style="margin: 10px 0; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 8px;">
                    <span>yt-dlp：</span>
                    <span :style="{ color: ytdlpInfo.available ? '#00d2ff' : '#ff416c' }">
                        {{ ytdlpInfo.available ? ('v' + ytdlpInfo.version + ' 已就绪') : '未安装（请检查插件依赖）' }}
                    </span>
                </div>
                <label><input type="checkbox" v-model="configForm.ytdlp_enabled"> 启用多平台下载</label>
                <label>代理地址（可选）</label>
                <input v-model="configForm.ytdlp_proxy" type="text" placeholder="http://127.0.0.1:7890">
                <label>Cookie（可选，抖音等平台触发风控时需要）</label>
                <input v-model="configForm.ytdlp_cookie" type="password" placeholder="ttwid=...; passport_csrf_token=...">
                <label>Cookies 文件路径（可选，Netscape 格式）</label>
                <input v-model="configForm.ytdlp_cookiefile" type="text" placeholder="留空则不使用，相对路径基于插件数据目录">
                <label><input type="checkbox" v-model="configForm.ytdlp_allow_any_site"> 允许任意 yt-dlp 支持的站点</label>
                <p class="hint">默认只响应常见视频平台链接，避免误下载普通网页。</p>
                <button @click="saveConfig" :disabled="configLoading">{{ configLoading ? '保存中...' : '保存配置' }}</button>
            </div>

            <div class="form-group" style="margin-top: 20px;">
                <h2>群聊与解析</h2>
                <p class="hint">
                    解析始终可用；这里控制哪些群聊可以真正下载并发送视频。
                    未开启下载的群聊仍会回复视频信息卡片，但不会发送视频文件。
                </p>
                <label>群聊下载权限</label>
                <select v-model="configForm.group_download_mode">
                    <option value="all">全部群聊允许</option>
                    <option value="whitelist">仅白名单群聊</option>
                    <option value="blacklist">黑名单群聊禁止</option>
                </select>
                <label>群号列表（白名单/黑名单模式下使用）</label>
                <textarea v-model="configForm.group_download_list" rows="4" placeholder="每行一个群号，也可以用逗号分隔"></textarea>
                <label><input type="checkbox" v-model="configForm.private_download_enabled"> 私聊允许下载</label>
                <label><input type="checkbox" v-model="configForm.parse_all_group_messages"> 群聊中无需 @ 也解析链接（仅解析，不下载）</label>
                <p class="hint">
                    开启后，普通群消息里的视频链接会回复信息卡片；下载仍需 @ 机器人，且该群已开启下载。
                </p>
                <button @click="saveConfig" :disabled="configLoading">{{ configLoading ? '保存中...' : '保存配置' }}</button>
            </div>

            <div class="form-group" style="margin-top: 20px;">
                <h2>FFmpeg 环境配置</h2>
                <p class="hint">FFmpeg 用于合并 DASH 格式的分离音视频流，缺少它视频将无声。已安装的系统版本会被自动识别。</p>
                <div style="margin: 10px 0; padding: 10px; background: rgba(0,0,0,0.2); border-radius: 8px;">
                    <span>当前状态：</span>
                    <span :style="{ color: ffmpegStatus.status === 'ready' ? '#00d2ff' : (ffmpegStatus.status === 'error' ? '#ff416c' : '#aaa') }">
                        {{ ffmpegStatus.message }}
                    </span>
                    <div v-if="ffmpegStatus.version" class="hint mono-line">{{ ffmpegStatus.version }}</div>
                    <div v-if="ffmpegStatus.path" class="hint mono-line">路径：{{ ffmpegStatus.path }}</div>
                </div>
                <div class="row-actions">
                    <button class="ghost" @click="checkFFmpeg" :disabled="ffmpegStatus.status === 'downloading'">
                        {{ checkingFFmpeg ? '检测中...' : '重新检测' }}
                    </button>
                    <button v-if="ffmpegStatus.status !== 'ready'" @click="downloadFFmpeg" :disabled="ffmpegStatus.status === 'downloading'">
                        {{ ffmpegStatus.status === 'downloading' ? '正在下载中，请稍候...' : '一键下载 FFmpeg' }}
                    </button>
                </div>
                <p class="hint" v-if="ffmpegStatus.status !== 'ready'">{{ ffmpegHint }}</p>
            </div>
        </section>
    </main>
    <!-- ASCII 水印背景 -->
    <pre class="ascii-art">${ASCII_ART}</pre>
    <!-- Toast 通知 -->
    <div class="toast" :class="{ show: toastVisible }">{{ toastMessage }}</div>
    <!-- 删除确认弹窗 -->
    <div v-if="showClearConfirm" class="modal-overlay" @click.self="cancelDeleteCookie">
        <div class="modal-panel">
            <h3>警告</h3>
            <p>确定要删除这条 Cookie 吗？删除后可能影响高清视频下载。</p>
            <div class="modal-actions">
                <button @click="cancelDeleteCookie">取消</button>
                <button class="danger" @click="confirmDeleteCookie">确认删除</button>
            </div>
        </div>
    </div>
    <!-- 清除全部确认弹窗 -->
    <div v-if="showClearAllConfirm" class="modal-overlay" @click.self="cancelClearAll">
        <div class="modal-panel">
            <h3>严重警告</h3>
            <p>确定要清除所有 Cookie 吗？此操作不可撤销，所有账号登录状态将丢失。</p>
            <div class="modal-actions">
                <button @click="cancelClearAll">取消</button>
                <button class="danger" @click="confirmClearAll">确认全部清除</button>
            </div>
        </div>
    </div>
</div>
`;
