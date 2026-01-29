"""
弹幕和礼物测试窗口 - 用于调试弹幕和礼物捕获功能
使用与正式版相同的接口和模块
"""
import os
import sys
from datetime import datetime

# 环境优化
os.environ["QT_GL_DEFAULT_BACKEND"] = "software"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--no-sandbox --disable-gpu --disable-software-rasterizer "
    "--ignore-gpu-blocklist --disable-background-timer-throttling"
)

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QCheckBox
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtWebChannel import QWebChannel

# 导入正式版的模块
from danmu_monitor import DanmuBridge, DanmuMonitor, global_signal


# 测试窗口日志文件路径
_test_log_file = None

def _get_test_log_file():
    """获取测试窗口日志文件路径"""
    global _test_log_file
    if _test_log_file is None:
        try:
            from path_utils import get_log_dir
            log_dir = get_log_dir()
        except ImportError:
            log_dir = "logs"
            os.makedirs(log_dir, exist_ok=True)
        # 使用带时间戳的文件名，方便区分不同测试会话
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _test_log_file = os.path.join(log_dir, f"test_danmu_{timestamp}.log")
    return _test_log_file

def _write_test_log(message):
    """写入测试日志到文件"""
    try:
        log_file = _get_test_log_file()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")
            f.flush()
    except Exception:
        pass  # 忽略日志写入错误，避免影响主流程


class TestDanmuWindow(QWidget):
    """弹幕和礼物测试窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("弹幕和礼物测试窗口 | 开发者: 故里何日还")
        self.resize(1350, 950)
        
        # 设置窗口图标
        try:
            if getattr(sys, 'frozen', False):
                base_dir = sys._MEIPASS
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(base_dir, "favicon.ico")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(os.getcwd(), "favicon.ico")
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except:
            pass
        
        # 创建浏览器
        self.browser = QWebEngineView()
        
        # 获取会话目录路径
        try:
            from path_utils import get_session_dir
            session_path = get_session_dir("test")
        except ImportError:
            session_path = os.path.join(os.getcwd(), "douyin_sessions", "test")
            os.makedirs(session_path, exist_ok=True)
        
        # 创建独立的profile
        self.profile = QWebEngineProfile("DouyinBot_Test", None)
        self.profile.setPersistentStoragePath(session_path)
        cache_path = os.path.join(session_path, "cache")
        os.makedirs(cache_path, exist_ok=True)
        self.profile.setCachePath(cache_path)
        
        # 创建页面实例
        page = QWebEnginePage(self.profile, self.browser)
        self.browser.setPage(page)
        
        # 创建WebChannel桥接
        self.bridge = DanmuBridge()
        self.channel = QWebChannel()
        self.channel.registerObject("pyBridge", self.bridge)
        self.browser.page().setWebChannel(self.channel)
        
        # 创建弹幕监控器
        self.danmu_monitor = DanmuMonitor("")  # 不过滤任何昵称，用于测试
        self.danmu_monitor.set_callback(self._on_danmu_received)
        
        # 初始化日志文件
        self.log_file = _get_test_log_file()
        _write_test_log(f"[初始化] 测试窗口启动，日志文件: {self.log_file}")
        
        # 去重缓存（用于弹幕和实时信息）
        self.danmu_cache = {}  # key: user+content, value: timestamp
        self.realtime_cache = {}  # key: infoType+user, value: timestamp
        self.gift_cache = {}  # key: user+gift_name+gift_count, value: timestamp
        self.cache_ttl = 10  # 10秒去重时间
        
        # 初始化UI
        self._init_ui()
        
        # 绑定信号
        self.browser.page().loadFinished.connect(self._on_page_loaded)
        global_signal.received.connect(self._on_danmu_signal)
        
    def _init_ui(self):
        """初始化用户界面"""
        layout = QVBoxLayout(self)
        
        # 导航栏
        nav = QHBoxLayout()
        nav.addWidget(QLabel("直播间地址:"))
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴直播间地址...")
        nav.addWidget(self.url_input)
        
        self.btn_go = QPushButton("🚀 启动")
        self.btn_go.setFixedWidth(80)
        self.btn_go.setStyleSheet("background:#FE2C55; color:white; font-weight:bold;")
        self.btn_go.clicked.connect(self.load_url)
        nav.addWidget(self.btn_go)
        
        nav.addWidget(QLabel("我的昵称(用于过滤):"))
        self.nickname_input = QLineEdit()
        self.nickname_input.setPlaceholderText("输入昵称以过滤自己的弹幕...")
        self.nickname_input.setFixedWidth(150)
        self.nickname_input.textChanged.connect(self._on_nickname_changed)
        nav.addWidget(self.nickname_input)
        
        nav.addStretch()
        
        self.cb_verbose = QCheckBox("详细日志")
        self.cb_verbose.setChecked(True)
        self.cb_verbose.setToolTip("启用后输出所有DOM元素和详细信息，方便分析")
        nav.addWidget(self.cb_verbose)
        
        btn_clear = QPushButton("🗑️ 清空日志")
        btn_clear.setFixedWidth(100)
        btn_clear.clicked.connect(self._clear_log)
        nav.addWidget(btn_clear)
        
        layout.addLayout(nav)
        
        # 浏览器和日志显示（上下布局）
        layout.addWidget(self.browser, stretch=3)
        
        # 日志显示
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet(
            "background:#000000; color:#00FF41; font-family:'Microsoft YaHei UI'; font-size:14px;"
        )
        
        # 添加初始提示
        log_file_info = f"日志文件: {self.log_file}"
        self.log_display.setHtml(
            f"<span style='color:#FFD700;'>【提示】</span> "
            f"<span style='color:#87CEEB;'>这是弹幕和礼物测试窗口，用于调试弹幕和礼物捕获功能。</span><br>"
            f"<span style='color:#87CEEB;'>所有捕获到的弹幕、礼物、在线人数等信息都会显示在下方。</span><br>"
            f"<span style='color:#98FB98;'>【日志文件】</span> <span style='color:#87CEEB;'>{log_file_info}</span><br><br>"
        )
        _write_test_log(f"[提示] 测试窗口已启动，日志文件: {self.log_file}")
        
        layout.addWidget(self.log_display, stretch=1)
        
    def _on_nickname_changed(self, text):
        """昵称改变时更新监控器"""
        self.danmu_monitor.set_nickname(text.strip())
        self.add_log(f"<span style='color:#98FB98;'>[设置]</span> 过滤昵称已更新: {text.strip() or '(无)'}")
        
    def load_url(self):
        """加载URL"""
        url = self.url_input.text().strip()
        if url:
            self.browser.load(QUrl(url))
            self.add_log(f"<span style='color:#98FB98;'>[启动]</span> 正在加载: {url}")
        else:
            self.add_log(f"<span style='color:#FF6B6B;'>[错误]</span> URL不能为空")
    
    def _on_page_loaded(self, success):
        """页面加载完成"""
        if success:
            self.add_log(f"<span style='color:#98FB98;'>[页面加载]</span> 页面加载完成，正在注入JavaScript...")
            # 延迟注入，确保页面完全加载
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(1000, self._inject_js)
        else:
            self.add_log(f"<span style='color:#FF6B6B;'>[错误]</span> 页面加载失败")
    
    def _inject_js(self):
        """注入JavaScript代码（增强版，输出详细DOM信息）"""
        instance_id = "test"
        import hashlib
        instance_hash = hashlib.md5(instance_id.encode('utf-8')).hexdigest()[:8]
        verbose_mode = self.cb_verbose.isChecked()
        
        js_code = rf"""
        (function() {{
            if (!window.sendToPy) {{
                window.sendToPy = function(data) {{
                    if (window.qt && window.qt.webChannelTransport) {{
                        window.qt.webChannelTransport.send(JSON.stringify({{
                            type: 6, id: Math.floor(Math.random() * 99999), 
                            object: "pyBridge", method: "post_danmu", args: [JSON.stringify(data)]
                        }}));
                    }}
                }};
            }}
            const instanceId = "{instance_hash}";
            const activeFlag = "v59_active_" + instanceId;
            if (window[activeFlag]) return;
            
            const cachePrefix = "idxCache_" + instanceId;
            if (!window[cachePrefix]) window[cachePrefix] = new Set();
            const idxCache = window[cachePrefix];
            
            // 礼物去重缓存（使用内容+时间戳，防止重复捕获）
            const giftContentCache = new Map(); // key: user+giftName+giftCount, value: timestamp
            const GIFT_CACHE_TTL = 60000; // 60秒内相同内容不重复捕获（延长去重时间，避免重复捕获）
            
            // 左下角用户列表礼物容器缓存（防止重复扫描同一容器）
            const giftContainerCache = new Set();
            
            // 礼物更新间隔追踪
            let lastGiftUpdateTime = 0; // 上次礼物更新时间
            const giftUpdateIntervals = []; // 记录最近的更新间隔（最多保留10个）
            const MAX_INTERVALS = 10;
            let currentScanInterval = 500; // 当前扫描间隔（毫秒），初始500ms
            let scanTimer = null; // 扫描定时器
            
            let lastViewerCount = '';
            let viewerCountUpdateTime = 0;
            
            function checkReplyBox() {{
                const ed = document.querySelector('[data-slate-editor="true"]') || 
                          document.querySelector('.ace-line')?.parentElement ||
                          document.querySelector('textarea[placeholder*="说点什么"]') ||
                          document.querySelector('textarea[placeholder*="发送"]');
                const detected = ed !== null && ed !== undefined;
                if (window.replyBoxDetected !== detected) {{
                    window.replyBoxDetected = detected;
                    window.sendToPy({{type: 'reply_box_detected', detected: detected}});
                }}
            }}
            
            checkReplyBox();
            setInterval(checkReplyBox, 3000);
            
            // 详细日志输出函数
            const verboseMode = {str(verbose_mode).lower()};
            function logVerbose(type, message, data = null) {{
                if (verboseMode) {{
                    const logData = {{
                        type: 'debug_log',
                        log_type: type,
                        message: message,
                        data: data,
                        timestamp: Date.now()
                    }};
                    window.sendToPy(logData);
                }}
            }}
            
            // 获取元素的详细信息
            function getElementInfo(node) {{
                if (!node) return null;
                const info = {{
                    tag: node.tagName,
                    id: node.id || '',
                    classes: Array.from(node.classList || []).join(' '),
                    dataIndex: node.getAttribute('data-index') || '',
                    innerText: (node.innerText || '').substring(0, 200),
                    textContent: (node.textContent || '').substring(0, 200),
                    children: []
                }};
                
                // 获取直接子元素的文本内容
                Array.from(node.children || []).slice(0, 5).forEach(child => {{
                    const childText = (child.innerText || child.textContent || '').trim().substring(0, 50);
                    if (childText) {{
                        info.children.push({{
                            tag: child.tagName,
                            class: child.className || '',
                            text: childText
                        }});
                    }}
                }});
                
                return info;
            }}
            
            // 检查是否是实时信息（非弹幕、非礼物）
            function isRealtimeInfo(text) {{
                const patterns = [
                    /加入了直播间/,
                    /分享了直播间/,
                    /成为了观众TOP/,
                    /为主播点了赞/,
                    /为主播点赞了/,
                    /点赞了/,
                    /为主播加了/,
                    /来了$/
                ];
                return patterns.some(pattern => pattern.test(text));
            }}
            
            // 检查是否是礼物列表（需要过滤的多余信息）
            function isGiftList(text) {{
                // 礼物列表特征：包含多个礼物名称和"钻"字
                const giftListPatterns = [
                    /日照金山|雪落生花|星愿雪淞|冰封誓约|萌狐戏雪|冰雪城堡|嘉年华|跑车|抖音1号|热气球/,
                    /\d+钻.*\d+钻/,  // 包含多个"数字+钻"的模式
                    /更多.*充值/,  // 包含"更多"和"充值"
                ];
                return giftListPatterns.some(pattern => pattern.test(text));
            }}
            
            // 检查是否是礼物信息
            function isGiftInfo(text) {{
                // 更精确的礼物信息判断：必须包含"送出了"且不包含冒号（弹幕格式是"用户名：内容"）
                // 弹幕区的礼物信息格式是"用户名：送出了 × 1"，所以包含冒号
                // 左下角的礼物信息格式是"用户名 送 礼物名"，不包含冒号
                return text.includes('送出了') && !text.includes('：') && !text.includes(':');
            }}
            
            function scanDanmu() {{
                const nodes = document.querySelectorAll('div[data-index]');
                
                nodes.forEach(node => {{
                    let idx = node.getAttribute('data-index');
                    if (idxCache.has(idx)) return;
                    
                    const allText = node.innerText || node.textContent || '';
                    
                    // 优先检查是否是礼物或实时信息，如果是则跳过（由专门的扫描函数处理）
                    if (isGiftInfo(allText)) return;
                    // 检查是否是弹幕区的礼物信息（包含"送出了"和冒号，格式："用户名：送出了 × 1"）
                    if (allText.includes('送出了') && (allText.includes('：') || allText.includes(':'))) {{
                        return; // 跳过弹幕区的礼物信息（这些信息没有具体的礼物名称）
                    }}
                    if (isRealtimeInfo(allText)) return;
                    
                    // 获取所有span元素
                    let spans = Array.from(node.querySelectorAll('span')).map(s => s.innerText.trim()).filter(t => t.length > 0);
                    
                    if (spans.length >= 2) {{
                        let user = spans[0].replace('：','').replace('：','');
                        let contentNode = node.querySelector('[class*="ent-with-emoji-text"]');
                        let content = contentNode ? contentNode.innerText.trim() : spans[spans.length - 1];
                        
                        if (user && content && !content.includes('进入')) {{
                            idxCache.add(idx);
                            if(idxCache.size > 200) idxCache.delete(idxCache.values().next().value);
                            
                            // 输出弹幕信息（粉色标记）
                            const elementInfo = getElementInfo(node);
                            window.sendToPy({{type: 'danmu', user: user, content: content}});
                            logVerbose('danmu_captured', '[弹幕捕获]', {{
                                user: user,
                                content: content,
                                dataIndex: idx,
                                element: elementInfo,
                                allText: allText.substring(0, 200),
                                spans: spans
                            }});
                        }}
                    }}
                }});
            }}
            
            const giftCachePrefix = "giftCache_" + instanceId;
            if (!window[giftCachePrefix]) window[giftCachePrefix] = new Set();
            const giftCache = window[giftCachePrefix];
            
            // 礼物关键词映射（扩展版）
            if (!window.giftKeywords) {{
                window.giftKeywords = [
                    {{ keywords: ['点亮', '粉丝', '团'], name: '点亮粉丝团' }},
                    {{ keywords: ['粉丝', '团', '灯牌'], name: '粉丝团灯牌' }},
                    {{ keywords: ['粉丝', '团'], name: '粉丝团' }},
                    {{ keywords: ['灯牌'], name: '灯牌' }},
                    {{ keywords: ['小心', '心'], name: '小心心' }},
                    {{ keywords: ['人气', '票'], name: '人气票' }},
                    {{ keywords: ['爱心'], name: '爱心' }},
                    {{ keywords: ['真好看'], name: '真好看' }},
                    {{ keywords: ['最好看'], name: '最好看' }},
                    {{ keywords: ['星光', '闪耀'], name: '星光闪耀' }},
                    {{ keywords: ['为你', '闪耀'], name: '为你闪耀' }},
                    {{ keywords: ['闪耀'], name: '闪耀' }},
                ];
            }}
            
            // 礼物关键词列表（用于快速检查）
            const giftKeywordList = ['粉丝团', '灯牌', '点亮', '小心心', '人气票', '爱心', '真好看', '最好看', '闪耀', '星光'];
            
            // 从节点中提取礼物名称（改进版）
            function getGiftNameFromNode(node) {{
                const allText = node.innerText || node.textContent || '';
                
                // 方法0: 从父元素和兄弟元素中查找（优先检查，因为礼物名称可能在父容器中）
                // 检查父元素（最多向上查找3层）
                let currentParent = node.parentElement;
                let parentLevel = 0;
                while (currentParent && parentLevel < 3) {{
                    parentLevel++;
                    const parentText = (currentParent.innerText || currentParent.textContent || '').trim();
                    // 如果父元素包含"送出了"，尝试从父元素中提取
                    if (parentText.includes('送出了') && parentText !== allText) {{
                        // 查找父元素中包含礼物关键词的元素
                        const parentGiftElements = currentParent.querySelectorAll('*');
                        for (let elem of parentGiftElements) {{
                            // 跳过当前节点本身
                            if (elem === node || node.contains(elem)) continue;
                            const elemText = (elem.innerText || elem.textContent || '').trim();
                            if (elemText && elemText.length > 0 && elemText !== allText) {{
                                // 跳过包含"送出了"、"："的元素（可能是用户名或数量）
                                if (elemText.includes('送出了') || elemText.includes('：') || /^[×xX]\s*\d+$/.test(elemText)) {{
                                    continue;
                                }}
                                // 如果文本是"来了"或以"来了"结尾，说明这是实时信息，不是礼物名称
                                if (elemText === '来了' || elemText.endsWith('来了')) {{
                                    continue;
                                }}
                                // 尝试匹配礼物关键词
                                for (let kw of window.giftKeywords) {{
                                    const matchedKeywords = kw.keywords.filter(k => elemText.includes(k));
                                    if (matchedKeywords.length >= Math.ceil(kw.keywords.length / 2)) {{
                                        return kw.name;
                                    }}
                                }}
                                // 如果元素文本包含礼物关键词，直接返回
                                if (elemText.includes('粉丝团') || elemText.includes('灯牌') || elemText.includes('点亮') || 
                                    elemText.includes('小心心') || elemText.includes('人气票') || elemText.includes('爱心') ||
                                    elemText.includes('真好看') || elemText.includes('最好看')) {{
                                    return elemText;
                                }}
                            }}
                        }}
                    }}
                    currentParent = currentParent.parentElement;
                }}
                
                // 检查兄弟元素
                if (node.parentElement) {{
                    const siblings = Array.from(node.parentElement.children);
                    for (let sibling of siblings) {{
                        if (sibling === node) continue;
                        const siblingText = (sibling.innerText || sibling.textContent || '').trim();
                        if (siblingText && siblingText.length > 0) {{
                            // 跳过包含"送出了"、"："的元素
                            if (siblingText.includes('送出了') || siblingText.includes('：') || /^[×xX]\s*\d+$/.test(siblingText)) {{
                                continue;
                            }}
                            // 如果文本是"来了"或以"来了"结尾，说明这是实时信息，不是礼物名称
                            if (siblingText === '来了' || siblingText.endsWith('来了')) {{
                                continue;
                            }}
                            // 尝试匹配礼物关键词
                            for (let kw of window.giftKeywords) {{
                                const matchedKeywords = kw.keywords.filter(k => siblingText.includes(k));
                                if (matchedKeywords.length >= Math.ceil(kw.keywords.length / 2)) {{
                                    return kw.name;
                                }}
                            }}
                            // 如果兄弟元素文本包含礼物关键词，直接返回
                            if (siblingText.includes('粉丝团') || siblingText.includes('灯牌') || siblingText.includes('点亮') || 
                                siblingText.includes('小心心') || siblingText.includes('人气票') || siblingText.includes('爱心') ||
                                siblingText.includes('真好看') || siblingText.includes('最好看')) {{
                                return siblingText;
                            }}
                        }}
                    }}
                }}
                
                // 方法1: 从"送出了"后面的文本中提取
                const parts = allText.split('送出了');
                if (parts.length >= 2) {{
                    let giftText = parts[1].trim();
                    
                    // 移除数量标识（× 1、×1、个等）
                    giftText = giftText.replace(/[×xX]\s*\d+/g, '').replace(/\d+\s*[个xX×]/g, '').replace(/^\d+\s*/, '').trim();
                    
                    // 如果移除数量后没有内容，说明只有数量没有礼物名称
                    if (!giftText || giftText.length === 0) {{
                        // 继续尝试其他方法
                    }} else {{
                        // 尝试匹配已知礼物关键词
                        for (let kw of window.giftKeywords) {{
                            const matchedKeywords = kw.keywords.filter(k => giftText.includes(k));
                            if (matchedKeywords.length >= Math.ceil(kw.keywords.length / 2)) {{
                                return kw.name;
                            }}
                        }}
                        
                        // 如果没有匹配到，尝试提取有意义的文本
                        if (giftText && giftText.length > 0) {{
                            const cleaned = giftText.replace(/\d+/g, '').trim();
                            if (cleaned && cleaned.length > 0) {{
                                return cleaned;
                            }}
                        }}
                    }}
                }}
                
                // 方法2: 从图片的alt、title属性中提取
                const img = node.querySelector('img');
                if (img) {{
                    // 检查alt属性
                    if (img.alt && img.alt.trim().length > 0) {{
                        let altText = img.alt.trim();
                        // 尝试匹配礼物关键词
                        for (let kw of window.giftKeywords) {{
                            const matchedKeywords = kw.keywords.filter(k => altText.includes(k));
                            if (matchedKeywords.length >= Math.ceil(kw.keywords.length / 2)) {{
                                return kw.name;
                            }}
                        }}
                        // 如果alt包含有意义的文本，返回它
                        if (altText && !altText.includes('送出了') && !altText.includes('：') && altText.length > 0) {{
                            return altText;
                        }}
                    }}
                    
                    // 检查title属性
                    if (img.title && img.title.trim().length > 0) {{
                        let titleText = img.title.trim();
                        // 尝试匹配礼物关键词
                        for (let kw of window.giftKeywords) {{
                            const matchedKeywords = kw.keywords.filter(k => titleText.includes(k));
                            if (matchedKeywords.length >= Math.ceil(kw.keywords.length / 2)) {{
                                return kw.name;
                            }}
                        }}
                        // 如果title包含有意义的文本，返回它
                        if (titleText && !titleText.includes('送出了') && !titleText.includes('：') && titleText.length > 0) {{
                            return titleText;
                        }}
                    }}
                }}
                
                // 方法3: 从span元素中提取（查找包含礼物名称的span）
                const spans = Array.from(node.querySelectorAll('span')).map(s => s.innerText.trim()).filter(t => t.length > 0);
                for (let span of spans) {{
                    // 跳过用户名和"送出了"和数量
                    if (span.includes('：') || span.includes('送出了') || /^[×xX]\s*\d+$/.test(span)) {{
                        continue;
                    }}
                    
                    // 尝试匹配礼物关键词
                    for (let kw of window.giftKeywords) {{
                        const matchedKeywords = kw.keywords.filter(k => span.includes(k));
                        if (matchedKeywords.length >= Math.ceil(kw.keywords.length / 2)) {{
                            return kw.name;
                        }}
                    }}
                    
                    // 如果span包含有意义的内容（不是纯数字），可能是礼物名称
                    if (span && !/^\d+$/.test(span) && span.length > 0) {{
                        return span;
                    }}
                }}
                
                // 方法4: 从图片后的文本中提取（遍历所有兄弟元素）
                if (img) {{
                    let nextSibling = img.nextElementSibling;
                    let foundText = '';
                    let attempts = 0;
                    while (nextSibling && !foundText && attempts < 10) {{
                        attempts++;
                        const siblingText = (nextSibling.innerText || nextSibling.textContent || '').trim();
                        if (siblingText && siblingText.length > 0 && !siblingText.match(/^\d+$/) && !siblingText.includes('送出了') && !siblingText.includes('：')) {{
                            // 如果文本是"来了"或以"来了"结尾，说明这是实时信息，不是礼物名称
                            if (siblingText === '来了' || siblingText.endsWith('来了')) {{
                                nextSibling = nextSibling.nextElementSibling;
                                continue;  // 跳过，这是实时信息
                            }}
                            foundText = siblingText;
                            break;
                        }}
                        nextSibling = nextSibling.nextElementSibling;
                    }}
                    
                    if (foundText) {{
                        // 尝试匹配礼物关键词
                        for (let kw of window.giftKeywords) {{
                            const matchedKeywords = kw.keywords.filter(k => foundText.includes(k));
                            if (matchedKeywords.length >= Math.ceil(kw.keywords.length / 2)) {{
                                return kw.name;
                            }}
                        }}
                        // 移除数量标识
                        foundText = foundText.replace(/[×xX]\s*\d+/g, '').replace(/\d+\s*[个xX×]/g, '').replace(/^\d+\s*/, '').trim();
                        return foundText || null;
                    }}
                }}
                
                // 方法5: 在整个节点中查找包含礼物关键词的元素
                const giftKeywordElements = node.querySelectorAll('*');
                for (let elem of giftKeywordElements) {{
                    const elemText = (elem.innerText || elem.textContent || '').trim();
                    if (elemText && elemText.length > 0) {{
                        // 跳过包含"送出了"、"："的元素（可能是用户名或数量）
                        if (elemText.includes('送出了') || elemText.includes('：') || /^[×xX]\s*\d+$/.test(elemText)) {{
                            continue;
                        }}
                        // 尝试匹配礼物关键词
                        for (let kw of window.giftKeywords) {{
                            const matchedKeywords = kw.keywords.filter(k => elemText.includes(k));
                            if (matchedKeywords.length >= Math.ceil(kw.keywords.length / 2)) {{
                                return kw.name;
                            }}
                        }}
                    }}
                }}
                
                // 方法4: 从文本中查找"送出了"后的换行文本（礼物名称可能在下一行）
                if (allText.includes('送出了')) {{
                    const lines = allText.split('\n');
                    for (let i = 0; i < lines.length; i++) {{
                        if (lines[i].includes('送出了')) {{
                            // 查找下一行或下几行的文本
                            for (let j = i + 1; j < lines.length && j < i + 3; j++) {{
                                let lineText = lines[j].trim();
                                if (lineText && lineText.length > 0) {{
                                    // 跳过数量标识
                                    if (!/^[×xX]\s*\d+$/.test(lineText) && !/^\d+\s*[个xX×]$/.test(lineText) && !lineText.includes('送出了') && !lineText.includes('：')) {{
                                        // 如果文本是"来了"或以"来了"结尾，说明这是实时信息，不是礼物名称
                                        if (lineText === '来了' || lineText.endsWith('来了')) {{
                                            continue;  // 跳过，这是实时信息
                                        }}
                                        // 尝试匹配礼物关键词
                                        for (let kw of window.giftKeywords) {{
                                            const matchedKeywords = kw.keywords.filter(k => lineText.includes(k));
                                            if (matchedKeywords.length >= Math.ceil(kw.keywords.length / 2)) {{
                                                return kw.name;
                                            }}
                                        }}
                                        // 移除数量标识
                                        let cleaned = lineText.replace(/[×xX]\s*\d+/g, '').replace(/\d+\s*[个xX×]/g, '').replace(/^\d+\s*/, '').trim();
                                        if (cleaned && cleaned.length > 0) {{
                                            return cleaned;
                                        }}
                                    }}
                                }}
                            }}
                        }}
                    }}
                }}
                
                return null;
            }}
            
            // 扫描实时信息（加入了直播间、分享了直播间等）
            function scanRealtimeInfo() {{
                // 方法1: 扫描所有带data-index的div
                const nodes1 = document.querySelectorAll('div[data-index]');
                scanRealtimeInfoFromNodes(nodes1, 'data-index-div');
                
                // 方法2: 扫描所有div元素（不限于data-index）
                const allDivs = document.querySelectorAll('div');
                const realtimeDivs = Array.from(allDivs).filter(div => {{
                    const text = div.innerText || div.textContent || '';
                    return isRealtimeInfo(text) && !div.hasAttribute('data-index');
                }});
                scanRealtimeInfoFromNodes(realtimeDivs, 'realtime-div');
            }}
            
            function scanRealtimeInfoFromNodes(nodes, sourceType) {{
                const realtimeCachePrefix = "realtimeCache_" + instanceId;
                if (!window[realtimeCachePrefix]) window[realtimeCachePrefix] = new Set();
                const realtimeCache = window[realtimeCachePrefix];
                
                nodes.forEach(node => {{
                    // 生成唯一标识
                    let uniqueId = '';
                    if (node.hasAttribute('data-index')) {{
                        uniqueId = 'data-index-' + node.getAttribute('data-index');
                    }} else {{
                        // 使用元素在DOM中的位置作为标识
                        const path = [];
                        let current = node;
                        while (current && current !== document.body) {{
                            const parent = current.parentElement;
                            if (parent) {{
                                const index = Array.from(parent.children).indexOf(current);
                                path.unshift(index);
                            }}
                            current = parent;
                        }}
                        uniqueId = sourceType + '-' + path.join('-');
                    }}
                    
                    if (realtimeCache.has(uniqueId)) return;
                    
                    const allText = node.innerText || node.textContent || '';
                    
                    if (isRealtimeInfo(allText)) {{
                        let spans = Array.from(node.querySelectorAll('span')).map(s => s.innerText.trim()).filter(t => t.length > 0);
                        let user = '';
                        
                        // 提取用户名（从文本中提取，支持多种格式）
                        if (spans.length > 0) {{
                            user = spans[0].replace('：', '').replace(':', '').trim();
                        }}
                        
                        // 如果span中没有用户名，尝试从文本中提取
                        if (!user) {{
                            // 格式1: "用户名：为主播点赞了"
                            const match1 = allText.match(/^([^：:]+)[：:]/);
                            if (match1) {{
                                user = match1[1].trim();
                            }} else {{
                                // 格式2: "用户名加入了直播间"
                                const match2 = allText.match(/^([^加]+)加入了直播间/);
                                if (match2) {{
                                    user = match2[1].trim();
                                }}
                            }}
                        }}
                        
                        let infoType = 'other';
                        let infoContent = allText;
                        
                        if (allText.includes('加入了直播间')) {{
                            infoType = 'enter';
                            // 只提取用户名，不包含其他内容
                            if (!user) {{
                                const enterMatch = allText.match(/^([^加]+)加入了直播间/);
                                if (enterMatch) {{
                                    user = enterMatch[1].trim();
                                }}
                            }}
                            infoContent = '';  // 进入直播间不需要额外内容
                        }} else if (allText.includes('分享了直播间')) {{
                            infoType = 'share';
                            infoContent = '';
                        }} else if (allText.includes('成为了观众TOP')) {{
                            infoType = 'top';
                            infoContent = '';
                        }} else if (allText.includes('为主播点了赞') || allText.includes('为主播点赞了') || allText.includes('点赞了')) {{
                            infoType = 'like';
                            // 提取点赞信息中的用户名
                            if (!user) {{
                                const likeMatch = allText.match(/^([^：:]+)[：:]/);
                                if (likeMatch) {{
                                    user = likeMatch[1].trim();
                                }}
                            }}
                            infoContent = '';  // 点赞信息不需要额外内容
                        }} else if (allText.includes('为主播加了')) {{
                            infoType = 'score';
                            // 提取加分信息中的用户名和分数
                            if (!user) {{
                                const scoreMatch = allText.match(/^([^为]+)为主播加了/);
                                if (scoreMatch) {{
                                    user = scoreMatch[1].trim();
                                }}
                            }}
                            // 提取分数（如"10分"）
                            const scoreMatch = allText.match(/(\d+)\s*分/);
                            if (scoreMatch) {{
                                infoContent = scoreMatch[1] + '分';
                            }} else {{
                                infoContent = '';
                            }}
                        }} else if (allText.endsWith('来了')) {{
                            infoType = 'enter';
                            // 提取"来了"信息中的用户名
                            if (!user) {{
                                const comeMatch = allText.match(/^([^来]+)来了$/);
                                if (comeMatch) {{
                                    user = comeMatch[1].trim();
                                }}
                            }}
                            infoContent = '';  // 进入直播间不需要额外内容
                        }}
                        
                        // 检查是否包含页面结构关键词（这些不应该被捕获为实时信息）
                        const pageStructureKeywords = ['在线观众', '全部', '高等级用户', '1000贡献用户', '需先登录', '本场点赞', '关注', '小时榜', '人气榜'];
                        if (pageStructureKeywords.some(keyword => allText.includes(keyword))) {{
                            return;  // 跳过页面结构容器
                        }}
                        
                        // 检查是否包含多个弹幕（通过统计"："的数量来判断）
                        const danmuMatches = allText.match(/[^：:]+[：:]/g);
                        if (danmuMatches && danmuMatches.length > 1) {{
                            return;  // 跳过包含多个弹幕的容器
                        }}
                        
                        // 使用文本内容作为唯一标识的一部分，避免重复捕获相同内容
                        // 只使用关键信息（类型+用户名），不包含整个文本内容
                        const contentKey = infoType + '-' + (user || '');
                        if (realtimeCache.has(contentKey)) return;
                        
                        if (user || infoContent) {{
                            realtimeCache.add(uniqueId);
                            realtimeCache.add(contentKey);
                            if (realtimeCache.size > 500) {{
                                const firstKey = realtimeCache.values().next().value;
                                realtimeCache.delete(firstKey);
                            }}
                            window.sendToPy({{type: 'realtime_info', info_type: infoType, user: user, content: infoContent}});
                            logVerbose('realtime_sent', '已发送实时信息: ' + infoType + ' - ' + user + ' - ' + infoContent);
                        }}
                    }}
                }});
            }}
            
            function scanGifts() {{
                // 禁用弹幕区的礼物扫描，只使用左下角的礼物信息
                // 弹幕区的礼物信息（"送出了 × 1"）没有具体的礼物名称，无法准确提取
                // 左下角的礼物信息包含完整的礼物名称，是唯一可靠的来源
                
                // 方法1: 扫描所有带data-index的div（已禁用）
                // const nodes1 = document.querySelectorAll('div[data-index]');
                // const giftNodes1 = Array.from(nodes1).filter(div => {{
                //     const text = div.innerText || div.textContent || '';
                //     return text.includes('送出了') || (text.includes('送') && (
                //         text.includes('点亮') || text.includes('粉丝团') || text.includes('灯牌') ||
                //         text.includes('小心心') || text.includes('人气票') || text.includes('爱心') ||
                //         text.includes('真好看') || text.includes('最好看')
                //     ));
                // }});
                // scanGiftsFromNodes(giftNodes1, 'data-index-div');
                
                // 方法2: 扫描所有div元素（已禁用）
                // const allDivs = document.querySelectorAll('div');
                // const giftDivs = Array.from(allDivs).filter(div => {{
                //     const text = div.innerText || div.textContent || '';
                //     return (text.includes('送出了') || 
                //            (text.includes('送') && (
                //                text.includes('点亮') || 
                //                text.includes('粉丝团') || 
                //                text.includes('灯牌') ||
                //                text.includes('小心心') ||
                //                text.includes('人气票') ||
                //                text.includes('爱心') ||
                //                text.includes('真好看') ||
                //                text.includes('最好看')
                //            ))) && !div.hasAttribute('data-index');
                // }});
                // scanGiftsFromNodes(giftDivs, 'gift-div');
            }}
            
            function scanGiftsFromNodes(nodes, sourceType) {{
                const now = Date.now();
                let processedCount = 0;
                let skippedCount = 0;
                let debugInfo = [];
                
                nodes.forEach(node => {{
                    // 生成唯一标识
                    let uniqueId = '';
                    if (node.hasAttribute('data-index')) {{
                        uniqueId = 'data-index-' + node.getAttribute('data-index');
                    }} else {{
                        // 使用元素在DOM中的位置作为标识
                        const path = [];
                        let current = node;
                        while (current && current !== document.body) {{
                            const parent = current.parentElement;
                            if (parent) {{
                                const index = Array.from(parent.children).indexOf(current);
                                path.unshift(index);
                            }}
                            current = parent;
                        }}
                        uniqueId = sourceType + '-' + path.join('-');
                    }}
                    
                    // DOM节点去重（防止同一节点重复处理）
                    if (giftCache.has(uniqueId)) {{
                        skippedCount++;
                        return;
                    }}
                    
                    const allText = node.innerText || node.textContent || '';
                    const textPreview = allText.substring(0, 100);
                    
                    // 先检查是否是礼物列表（需要过滤）
                    if (isGiftList(allText)) {{
                        skippedCount++;
                        // 不记录礼物列表的过滤日志，减少冗余
                        return;  // 跳过礼物列表
                    }}
                    
                    // 检查是否是实时信息（应该由实时信息扫描处理）
                    if (isRealtimeInfo(allText)) {{
                        skippedCount++;
                        // 不记录实时信息的过滤日志，减少冗余
                        return;  // 跳过实时信息，由实时信息扫描处理
                    }}
                    
                    // 检查是否包含多个弹幕（通过统计"："的数量来判断）
                    // 如果包含多个"用户名："格式，说明是包含多个弹幕的容器，不是单个礼物信息
                    const danmuMatches = allText.match(/[^：:]+[：:]/g);
                    if (danmuMatches && danmuMatches.length > 2) {{
                        skippedCount++;
                        // 不记录多弹幕容器的过滤日志，减少冗余
                        return;  // 跳过包含多个弹幕的容器
                    }}
                    
                    // 检查是否包含"在线观众"、"全部"、"高等级用户"等页面结构关键词
                    // 这些通常表示捕获到了整个页面容器，而不是单个礼物信息
                    const pageStructureKeywords = ['在线观众', '全部', '高等级用户', '1000贡献用户', '需先登录', '自动直播加载中'];
                    if (pageStructureKeywords.some(keyword => allText.includes(keyword))) {{
                        skippedCount++;
                        // 不记录页面结构的过滤日志，减少冗余
                        return;  // 跳过页面结构容器
                    }}
                    
                    // 扩展礼物检测：不仅检查"送出了"，还检查"送"+礼物关键词的组合
                    // 但需要确保是真正的礼物信息，而不是礼物列表或其他信息
                    const hasSendOut = allText.includes('送出了');
                    const hasSend = allText.includes('送');
                    const hasGiftKeyword = allText.includes('点亮') || allText.includes('粉丝团') || 
                                         allText.includes('灯牌') || allText.includes('小心心') ||
                                         allText.includes('人气票') || allText.includes('爱心') ||
                                         allText.includes('真好看') || allText.includes('最好看');
                    
                    // 检查是否有用户名格式（支持两种格式）：
                    // 1. "用户名："格式（弹幕区域）
                    // 2. "用户名 送"或"用户名\n送"格式（左下角用户列表区域，支持换行）
                    // 注意：用户名可能包含特殊字符和emoji（如^、-、🔮、🧊等），所以使用更宽松的匹配
                    // 使用非全局正则表达式，避免test()改变lastIndex
                    const userFormatPattern1 = /[^：:\s\n]{1,30}[：:]/;  // "用户名："格式
                    // 匹配"用户名 送"或"用户名\n送"，用户名可以是1-30个字符（支持emoji和特殊字符）
                    // 使用[\S\s]匹配所有字符（包括emoji），但排除冒号和空白字符的组合
                    // 或者使用更简单的方式：匹配非空白字符（包括emoji）后跟空白字符和"送"
                    const userFormatPattern2 = /[^\s：:]{1,30}[\s\n]+送/;  // "用户名 送"格式（支持emoji）
                    // 为了支持emoji，使用更宽松的匹配：匹配任何非空白、非冒号字符（包括emoji）
                    // emoji在JavaScript中会被识别为多个字符，所以需要更宽松的匹配
                    const userFormatPattern2Emoji = /[\u0000-\uFFFF]{1,30}[\s\n]+送/;  // 支持emoji的版本
                    // 先检查是否包含"送出了"（最简单的情况）
                    const hasSendOutFormat = allText.includes('送出了');
                    // 检查"用户名："格式
                    const hasColonFormat = userFormatPattern1.test(allText);
                    // 检查"用户名 送"格式（需要先检查hasSend，避免不必要的正则匹配）
                    // 先尝试标准匹配，如果失败再尝试支持emoji的匹配
                    let hasSendFormat = false;
                    if (hasSend) {{
                        // 重置正则表达式的lastIndex（如果之前使用过）
                        userFormatPattern2.lastIndex = 0;
                        hasSendFormat = userFormatPattern2.test(allText);
                        // 如果标准匹配失败，尝试支持emoji的匹配
                        if (!hasSendFormat) {{
                            userFormatPattern2Emoji.lastIndex = 0;
                            hasSendFormat = userFormatPattern2Emoji.test(allText);
                        }}
                    }}
                    const hasUserFormat = hasSendOutFormat || hasColonFormat || hasSendFormat;
                    
                    // 检查是否包含多个礼物信息（通过统计"送"或"送出了"的数量）
                    // 如果包含多个"用户名 送"模式，说明是容器节点，应该过滤掉
                    // 统计"用户名 送"模式的数量（用于检测多礼物容器）
                    // 使用支持emoji的正则表达式
                    const giftPatternMatches1 = allText.match(/[^\s：:]{1,30}[\s\n]+送/g);
                    const giftPatternMatches2 = allText.match(/[\u0000-\uFFFF]{1,30}[\s\n]+送/g);
                    const giftCount = Math.max(
                        giftPatternMatches1 ? giftPatternMatches1.length : 0,
                        giftPatternMatches2 ? giftPatternMatches2.length : 0
                    );
                    // 统计"送"的总数（包括"送出了"）
                    const sendMatches = allText.match(/送/g);
                    const sendCount = sendMatches ? sendMatches.length : 0;
                    // 如果包含多个"用户名 送"模式，或者"送"的总数超过2个，说明是容器节点
                    const hasMultipleGifts = giftCount > 1 || sendCount > 2;
                    
                    const textLength = allText.length;
                    
                    const isGiftMessage = (hasSendOut || (hasSend && hasGiftKeyword)) &&
                                        !isGiftList(allText) &&
                                        !isRealtimeInfo(allText) &&
                                        hasUserFormat &&
                                        !hasMultipleGifts &&  // 过滤包含多个礼物信息的容器
                                        textLength < 200;
                    
                    // 调试信息：大幅减少日志输出，只在真正需要调试时记录
                    // 如果节点通过了所有检查，直接处理，不记录日志
                    // 只在失败且需要调试时记录（减少到最少）
                    // 注释掉候选节点的详细日志，减少冗余
                    // if (!isGiftMessage && (hasSendOut || (hasSend && hasGiftKeyword))) {{
                    //     // 只记录关键失败原因，不记录所有详细信息
                    //     const failReasons = [];
                    //     if (isGiftList(allText)) failReasons.push('礼物列表');
                    //     if (isRealtimeInfo(allText)) failReasons.push('实时信息');
                    //     if (!hasUserFormat) failReasons.push('无用户格式');
                    //     if (hasMultipleGifts) failReasons.push('多礼物');
                    //     if (textLength >= 200) failReasons.push('文本过长');
                    //     
                    //     // 只在有明确失败原因时记录
                    //     if (failReasons.length > 0) {{
                    //         logVerbose('gift_candidate', '[礼物候选-失败] ' + failReasons.join(', '), {{
                    //             uniqueId: uniqueId.substring(0, 20),
                    //             textPreview: textPreview.substring(0, 50)
                    //         }});
                    //     }}
                    // }}
                    
                    if (isGiftMessage) {{
                        processedCount++;
                        // 按照DOM元素的固定顺序提取，不使用正则表达式
                        // 获取所有子节点的文本内容（按DOM顺序）
                        let childTexts = [];
                        let walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, null, false);
                        let textNode;
                        while (textNode = walker.nextNode()) {{
                            let text = textNode.textContent.trim();
                            if (text && text.length > 0) {{
                                childTexts.push(text);
                            }}
                        }}
                        
                        // 如果TreeWalker没有获取到内容，尝试从所有子元素获取
                        if (childTexts.length === 0) {{
                            let children = Array.from(node.childNodes);
                            for (let child of children) {{
                                if (child.nodeType === Node.TEXT_NODE) {{
                                    let text = child.textContent.trim();
                                    if (text && text.length > 0) {{
                                        childTexts.push(text);
                                    }}
                                }} else if (child.nodeType === Node.ELEMENT_NODE) {{
                                    let text = child.innerText || child.textContent || '';
                                    if (text && text.trim().length > 0) {{
                                        childTexts.push(text.trim());
                                    }}
                                }}
                            }}
                        }}
                        
                        // 获取所有span元素的文本（按DOM顺序）
                        let spans = Array.from(node.querySelectorAll('span')).map(s => s.innerText.trim()).filter(t => t.length > 0);
                        
                        let user = '';
                        let giftName = '';
                        let giftCount = '1';
                        
                        // 提取礼物数量（查找 × 1、×1 等格式）
                        const countMatch = allText.match(/[×xX]\s*(\d+)/);
                        if (countMatch) {{
                            giftCount = countMatch[1];
                        }} else {{
                            const countMatch2 = allText.match(/(\d+)\s*个/);
                            if (countMatch2) {{
                                giftCount = countMatch2[1];
                            }}
                        }}
                        
                        // 按照固定顺序提取：查找"送"或"送出了"的位置
                        let sendIndex = -1;
                        let sendText = '';
                        
                        // 在spans中查找"送"或"送出了"
                        for (let i = 0; i < spans.length; i++) {{
                            if (spans[i] === '送' || spans[i] === '送出了' || spans[i].includes('送出了')) {{
                                sendIndex = i;
                                sendText = spans[i];
                                break;
                            }}
                        }}
                        
                        // 如果spans中没找到，在childTexts中查找
                        if (sendIndex === -1) {{
                            for (let i = 0; i < childTexts.length; i++) {{
                                if (childTexts[i] === '送' || childTexts[i] === '送出了' || childTexts[i].includes('送出了')) {{
                                    sendIndex = i;
                                    sendText = childTexts[i];
                                    break;
                                }}
                            }}
                        }}
                        
                        if (sendIndex >= 0) {{
                            // 用户名和礼物名称提取：由于DOM可能是倒序的，需要同时检查"送"之前和之后
                            // 策略：找到"送"后，检查前后元素，确定哪个是用户名，哪个是礼物名称
                            
                            // 先尝试从"送"之前提取用户名（向后遍历）
                            let userCandidate = '';
                            for (let i = sendIndex - 1; i >= 0 && i >= sendIndex - 5; i--) {{
                                let candidate = '';
                                if (i < spans.length) {{
                                    candidate = spans[i].trim();
                                }} else if (i < childTexts.length) {{
                                    candidate = childTexts[i].trim();
                                }}
                                
                                if (candidate && candidate.length > 0) {{
                                    // 跳过"送"本身
                                    if (candidate === '送' || candidate.includes('送出了')) {{
                                        continue;
                                    }}
                                    // 跳过数量
                                    if (/^[×xX]\s*\d+$/.test(candidate) || /^\d+\s*[个xX×]$/.test(candidate)) {{
                                        continue;
                                    }}
                                    // 如果包含冒号（如":清:"或"清："），提取用户名
                                    if (candidate.includes('：') || candidate.includes(':')) {{
                                        userCandidate = candidate.replace(/^[：:]+/, '').replace(/[：:]+$/, '').trim();
                                        if (userCandidate && userCandidate.length > 0) {{
                                            break;
                                        }}
                                    }}
                                    // 如果长度较短且不包含礼物关键词，可能是用户名
                                    else if (candidate.length < 20 && !candidate.includes('粉丝团') && !candidate.includes('灯牌') && 
                                        !candidate.includes('点亮') && !candidate.includes('小心心') && !candidate.includes('人气票') &&
                                        !candidate.includes('爱心') && !candidate.includes('真好看') && !candidate.includes('最好看')) {{
                                        userCandidate = candidate;
                                        break;
                                    }}
                                }}
                            }}
                            
                            // 从"送"之后提取礼物名称（向前遍历）
                            let giftCandidate = '';
                            let searchStart = sendIndex + 1;
                            // 跳过数量
                            if (searchStart < spans.length) {{
                                let nextText = spans[searchStart].trim();
                                if (/^[×xX]\s*\d+$/.test(nextText) || /^\d+\s*[个xX×]$/.test(nextText)) {{
                                    searchStart++;
                                }}
                            }} else if (searchStart < childTexts.length) {{
                                let nextText = childTexts[searchStart].trim();
                                if (/^[×xX]\s*\d+$/.test(nextText) || /^\d+\s*[个xX×]$/.test(nextText)) {{
                                    searchStart++;
                                }}
                            }}
                            
                            // 遍历后续元素，查找礼物名称（扩大遍历范围到30个元素）
                            let maxSearchLength = Math.max(spans.length, childTexts.length);
                            let maxSearchIndex = Math.min(maxSearchLength, searchStart + 30);
                            
                            // 第一轮：优先查找包含礼物关键词的元素
                            for (let i = searchStart; i < maxSearchIndex; i++) {{
                                let candidate = '';
                                if (i < spans.length) {{
                                    candidate = spans[i].trim();
                                }} else if (i < childTexts.length) {{
                                    candidate = childTexts[i].trim();
                                }}
                                
                                if (candidate && candidate.length > 0) {{
                                    // 跳过"送"本身
                                    if (candidate === '送' || candidate.includes('送出了')) {{
                                        continue;
                                    }}
                                    // 跳过数量
                                    if (/^[×xX]\s*\d+$/.test(candidate) || /^\d+\s*[个xX×]$/.test(candidate)) {{
                                        continue;
                                    }}
                                    // 如果包含礼物关键词，是礼物名称（优先匹配）
                                    if (candidate.includes('粉丝团') || candidate.includes('灯牌') || candidate.includes('点亮') ||
                                        candidate.includes('小心心') || candidate.includes('人气票') || candidate.includes('爱心') ||
                                        candidate.includes('真好看') || candidate.includes('最好看')) {{
                                        giftCandidate = candidate;
                                        break;
                                    }}
                                }}
                            }}
                            
                            // 如果第一轮没找到，第二轮：查找其他可能的礼物名称（但不是用户名）
                            if (!giftCandidate || giftCandidate.length === 0) {{
                                for (let i = searchStart; i < maxSearchIndex; i++) {{
                                    let candidate = '';
                                    if (i < spans.length) {{
                                        candidate = spans[i].trim();
                                    }} else if (i < childTexts.length) {{
                                        candidate = childTexts[i].trim();
                                    }}
                                    
                                    if (candidate && candidate.length > 0) {{
                                        // 跳过"送"本身和数量
                                        if (candidate === '送' || candidate.includes('送出了') || 
                                            /^[×xX]\s*\d+$/.test(candidate) || /^\d+\s*[个xX×]$/.test(candidate)) {{
                                            continue;
                                        }}
                                        // 如果长度较长或包含其他内容，也可能是礼物名称（但不是用户名）
                                        if (candidate.length > 0 && !candidate.includes('：') && !candidate.includes(':')) {{
                                            // 如果这个候选不是用户名，可能是礼物名称
                                            if (!userCandidate || candidate !== userCandidate) {{
                                                giftCandidate = candidate;
                                                break;
                                            }}
                                        }}
                                    }}
                                }}
                            }}
                            
                            // 如果从"送"之前没有找到用户名，但从"送"之后找到了，可能是倒序
                            // 重新检查：如果"送"之后有用户名格式的元素，可能是倒序
                            if (!userCandidate || userCandidate.length === 0) {{
                                // 从"送"之后查找用户名（可能是倒序）
                                for (let i = searchStart; i < Math.min(Math.max(spans.length, childTexts.length), searchStart + 5); i++) {{
                                    let candidate = '';
                                    if (i < spans.length) {{
                                        candidate = spans[i].trim();
                                    }} else if (i < childTexts.length) {{
                                        candidate = childTexts[i].trim();
                                    }}
                                    
                                    if (candidate && candidate.length > 0) {{
                                        // 跳过"送"本身和数量
                                        if (candidate === '送' || candidate.includes('送出了') || 
                                            /^[×xX]\s*\d+$/.test(candidate) || /^\d+\s*[个xX×]$/.test(candidate)) {{
                                            continue;
                                        }}
                                        // 如果包含冒号，可能是用户名
                                        if (candidate.includes('：') || candidate.includes(':')) {{
                                            userCandidate = candidate.replace(/^[：:]+/, '').replace(/[：:]+$/, '').trim();
                                            break;
                                        }}
                                        // 如果长度较短且不包含礼物关键词，可能是用户名
                                        else if (candidate.length < 20 && !candidate.includes('粉丝团') && !candidate.includes('灯牌') && 
                                            !candidate.includes('点亮') && !candidate.includes('小心心') && !candidate.includes('人气票') &&
                                            !candidate.includes('爱心') && !candidate.includes('真好看') && !candidate.includes('最好看')) {{
                                            userCandidate = candidate;
                                            break;
                                        }}
                                    }}
                                }}
                            }}
                            
                            // 如果从"送"之后没有找到礼物名称，但从"送"之前找到了，可能是倒序
                            if (!giftCandidate || giftCandidate.length === 0) {{
                                // 从"送"之前查找礼物名称（可能是倒序，扩大遍历范围到30个元素）
                                let maxBackwardSearch = Math.min(sendIndex, 30);
                                for (let i = sendIndex - 1; i >= 0 && i >= sendIndex - maxBackwardSearch; i--) {{
                                    let candidate = '';
                                    if (i < spans.length) {{
                                        candidate = spans[i].trim();
                                    }} else if (i < childTexts.length) {{
                                        candidate = childTexts[i].trim();
                                    }}
                                    
                                    if (candidate && candidate.length > 0) {{
                                        // 跳过"送"本身和数量
                                        if (candidate === '送' || candidate.includes('送出了') || 
                                            /^[×xX]\s*\d+$/.test(candidate) || /^\d+\s*[个xX×]$/.test(candidate)) {{
                                            continue;
                                        }}
                                        // 如果包含礼物关键词，是礼物名称（优先匹配）
                                        if (candidate.includes('粉丝团') || candidate.includes('灯牌') || candidate.includes('点亮') ||
                                            candidate.includes('小心心') || candidate.includes('人气票') || candidate.includes('爱心') ||
                                            candidate.includes('真好看') || candidate.includes('最好看')) {{
                                            giftCandidate = candidate;
                                            break;
                                        }}
                                    }}
                                }}
                            }}
                            
                            // 如果还是没找到，扩大搜索范围：遍历父节点、兄弟节点和相邻元素
                            if (!giftCandidate || giftCandidate.length === 0) {{
                                // 方法1: 遍历当前节点的所有子元素
                                let allElements = node.querySelectorAll('*');
                                for (let elem of allElements) {{
                                    let elemText = (elem.innerText || elem.textContent || '').trim();
                                    if (elemText && elemText.length > 0) {{
                                        // 跳过"送"本身和数量
                                        if (elemText === '送' || elemText.includes('送出了') || 
                                            /^[×xX]\s*\d+$/.test(elemText) || /^\d+\s*[个xX×]$/.test(elemText)) {{
                                            continue;
                                        }}
                                        // 如果包含礼物关键词，是礼物名称
                                        if (elemText.includes('粉丝团') || elemText.includes('灯牌') || elemText.includes('点亮') ||
                                            elemText.includes('小心心') || elemText.includes('人气票') || elemText.includes('爱心') ||
                                            elemText.includes('真好看') || elemText.includes('最好看') || elemText.includes('闪耀') || elemText.includes('星光')) {{
                                            // 提取包含礼物关键词的部分
                                            if (elemText.includes('粉丝团灯牌')) {{
                                                giftCandidate = '粉丝团灯牌';
                                            }} else if (elemText.includes('点亮粉丝团')) {{
                                                giftCandidate = '点亮粉丝团';
                                            }} else if (elemText.includes('星光闪耀')) {{
                                                giftCandidate = '星光闪耀';
                                            }} else if (elemText.includes('为你闪耀')) {{
                                                giftCandidate = '为你闪耀';
                                            }} else if (elemText.includes('粉丝团')) {{
                                                giftCandidate = '粉丝团';
                                            }} else if (elemText.includes('灯牌')) {{
                                                giftCandidate = '灯牌';
                                            }} else if (elemText.includes('小心心')) {{
                                                giftCandidate = '小心心';
                                            }} else if (elemText.includes('人气票')) {{
                                                giftCandidate = '人气票';
                                            }} else if (elemText.includes('爱心')) {{
                                                giftCandidate = '爱心';
                                            }} else if (elemText.includes('真好看')) {{
                                                giftCandidate = '真好看';
                                            }} else if (elemText.includes('最好看')) {{
                                                giftCandidate = '最好看';
                                            }} else if (elemText.includes('闪耀')) {{
                                                giftCandidate = '闪耀';
                                            }} else {{
                                                giftCandidate = elemText;
                                            }}
                                            break;
                                        }}
                                    }}
                                }}
                                
                                // 方法2: 如果还没找到，搜索父节点及其兄弟节点
                                if (!giftCandidate || giftCandidate.length === 0) {{
                                    let currentParent = node.parentElement;
                                    let parentLevel = 0;
                                    while (currentParent && parentLevel < 5) {{
                                        parentLevel++;
                                        
                                        // 搜索父节点的所有子元素（包括兄弟节点）
                                        let parentChildren = currentParent.querySelectorAll('*');
                                        for (let elem of parentChildren) {{
                                            // 跳过当前节点本身
                                            if (elem === node || node.contains(elem)) continue;
                                            
                                            let elemText = (elem.innerText || elem.textContent || '').trim();
                                            if (elemText && elemText.length > 0 && elemText.length < 50) {{
                                                // 跳过"送"本身和数量
                                                if (elemText === '送' || elemText.includes('送出了') || 
                                                    /^[×xX]\s*\d+$/.test(elemText) || /^\d+\s*[个xX×]$/.test(elemText)) {{
                                                    continue;
                                                }}
                                                // 如果包含礼物关键词，是礼物名称
                                                if (elemText.includes('粉丝团') || elemText.includes('灯牌') || elemText.includes('点亮') ||
                                                    elemText.includes('小心心') || elemText.includes('人气票') || elemText.includes('爱心') ||
                                                    elemText.includes('真好看') || elemText.includes('最好看') || elemText.includes('闪耀') || elemText.includes('星光')) {{
                                                    // 提取包含礼物关键词的部分
                                                    if (elemText.includes('粉丝团灯牌')) {{
                                                        giftCandidate = '粉丝团灯牌';
                                                    }} else if (elemText.includes('点亮粉丝团')) {{
                                                        giftCandidate = '点亮粉丝团';
                                                    }} else if (elemText.includes('星光闪耀')) {{
                                                        giftCandidate = '星光闪耀';
                                                    }} else if (elemText.includes('为你闪耀')) {{
                                                        giftCandidate = '为你闪耀';
                                                    }} else if (elemText.includes('粉丝团')) {{
                                                        giftCandidate = '粉丝团';
                                                    }} else if (elemText.includes('灯牌')) {{
                                                        giftCandidate = '灯牌';
                                                    }} else if (elemText.includes('小心心')) {{
                                                        giftCandidate = '小心心';
                                                    }} else if (elemText.includes('人气票')) {{
                                                        giftCandidate = '人气票';
                                                    }} else if (elemText.includes('爱心')) {{
                                                        giftCandidate = '爱心';
                                                    }} else if (elemText.includes('真好看')) {{
                                                        giftCandidate = '真好看';
                                                    }} else if (elemText.includes('最好看')) {{
                                                        giftCandidate = '最好看';
                                                    }} else if (elemText.includes('闪耀')) {{
                                                        giftCandidate = '闪耀';
                                                    }} else {{
                                                        giftCandidate = elemText;
                                                    }}
                                                    break;
                                                }}
                                            }}
                                        }}
                                        
                                        if (giftCandidate && giftCandidate.length > 0) break;
                                        
                                        // 继续向上查找父节点
                                        currentParent = currentParent.parentElement;
                                    }}
                                }}
                                
                                // 方法3: 如果还没找到，搜索相邻的兄弟节点
                                if (!giftCandidate || giftCandidate.length === 0) {{
                                    // 搜索前一个兄弟节点
                                    let prevSibling = node.previousElementSibling;
                                    let siblingCount = 0;
                                    while (prevSibling && siblingCount < 10) {{
                                        siblingCount++;
                                        let siblingText = (prevSibling.innerText || prevSibling.textContent || '').trim();
                                        if (siblingText && siblingText.length > 0 && siblingText.length < 100) {{
                                            if (siblingText.includes('粉丝团') || siblingText.includes('灯牌') || siblingText.includes('点亮') ||
                                                siblingText.includes('小心心') || siblingText.includes('人气票') || siblingText.includes('爱心') ||
                                                siblingText.includes('真好看') || siblingText.includes('最好看') || siblingText.includes('闪耀') || siblingText.includes('星光')) {{
                                                // 从兄弟节点文本中提取礼物名称
                                                if (siblingText.includes('粉丝团灯牌')) {{
                                                    giftCandidate = '粉丝团灯牌';
                                                }} else if (siblingText.includes('点亮粉丝团')) {{
                                                    giftCandidate = '点亮粉丝团';
                                                }} else if (siblingText.includes('星光闪耀')) {{
                                                    giftCandidate = '星光闪耀';
                                                }} else if (siblingText.includes('为你闪耀')) {{
                                                    giftCandidate = '为你闪耀';
                                                }} else if (siblingText.includes('粉丝团')) {{
                                                    giftCandidate = '粉丝团';
                                                }} else if (siblingText.includes('灯牌')) {{
                                                    giftCandidate = '灯牌';
                                                }} else if (siblingText.includes('小心心')) {{
                                                    giftCandidate = '小心心';
                                                }} else if (siblingText.includes('人气票')) {{
                                                    giftCandidate = '人气票';
                                                }} else if (siblingText.includes('爱心')) {{
                                                    giftCandidate = '爱心';
                                                }} else if (siblingText.includes('真好看')) {{
                                                    giftCandidate = '真好看';
                                                }} else if (siblingText.includes('最好看')) {{
                                                    giftCandidate = '最好看';
                                                }} else if (siblingText.includes('闪耀')) {{
                                                    giftCandidate = '闪耀';
                                                }}
                                                if (giftCandidate && giftCandidate.length > 0) break;
                                            }}
                                        }}
                                        prevSibling = prevSibling.previousElementSibling;
                                    }}
                                    
                                    // 搜索后一个兄弟节点
                                    if (!giftCandidate || giftCandidate.length === 0) {{
                                        let nextSibling = node.nextElementSibling;
                                        siblingCount = 0;
                                        while (nextSibling && siblingCount < 10) {{
                                            siblingCount++;
                                            let siblingText = (nextSibling.innerText || nextSibling.textContent || '').trim();
                                            if (siblingText && siblingText.length > 0 && siblingText.length < 100) {{
                                                if (siblingText.includes('粉丝团') || siblingText.includes('灯牌') || siblingText.includes('点亮') ||
                                                    siblingText.includes('小心心') || siblingText.includes('人气票') || siblingText.includes('爱心') ||
                                                    siblingText.includes('真好看') || siblingText.includes('最好看') || siblingText.includes('闪耀') || siblingText.includes('星光')) {{
                                                    // 从兄弟节点文本中提取礼物名称
                                                    if (siblingText.includes('粉丝团灯牌')) {{
                                                        giftCandidate = '粉丝团灯牌';
                                                    }} else if (siblingText.includes('点亮粉丝团')) {{
                                                        giftCandidate = '点亮粉丝团';
                                                    }} else if (siblingText.includes('星光闪耀')) {{
                                                        giftCandidate = '星光闪耀';
                                                    }} else if (siblingText.includes('为你闪耀')) {{
                                                        giftCandidate = '为你闪耀';
                                                    }} else if (siblingText.includes('粉丝团')) {{
                                                        giftCandidate = '粉丝团';
                                                    }} else if (siblingText.includes('灯牌')) {{
                                                        giftCandidate = '灯牌';
                                                    }} else if (siblingText.includes('小心心')) {{
                                                        giftCandidate = '小心心';
                                                    }} else if (siblingText.includes('人气票')) {{
                                                        giftCandidate = '人气票';
                                                    }} else if (siblingText.includes('爱心')) {{
                                                        giftCandidate = '爱心';
                                                    }} else if (siblingText.includes('真好看')) {{
                                                        giftCandidate = '真好看';
                                                    }} else if (siblingText.includes('最好看')) {{
                                                        giftCandidate = '最好看';
                                                    }} else if (siblingText.includes('闪耀')) {{
                                                        giftCandidate = '闪耀';
                                                    }}
                                                    if (giftCandidate && giftCandidate.length > 0) break;
                                                }}
                                            }}
                                            nextSibling = nextSibling.nextElementSibling;
                                        }}
                                    }}
                                }}
                            }}
                            
                            // 设置最终的用户名和礼物名称
                            user = userCandidate;
                            giftName = giftCandidate;
                            
                            // 清理礼物名称：移除数量标识
                            if (giftName) {{
                                giftName = giftName.replace(/[×xX]\s*\d+/g, '').replace(/\d+\s*[个xX×]/g, '').replace(/^\d+\s*/, '').trim();
                                // 如果礼物名称是"来了"，说明这是实时信息，不是礼物名称，应该被过滤掉
                                if (giftName === '来了' || giftName.endsWith('来了')) {{
                                    giftName = '';
                                }}
                                // 移除可能包含的用户名（如果礼物名称后面还有"用户名："格式）
                                giftName = giftName.split(/[：:\n]/)[0].trim();
                                
                                // 检查：如果礼物名和用户名相同，说明提取错误，应该清空礼物名
                                if (user && giftName === user.trim()) {{
                                    giftName = '';
                                }}
                            }}
                        }}
                        
                        // 关键：如果没有礼物名称（只有"送出了×1"），记录详细调试信息
                        // 记录"用户送出了×"中间缺失的信息，以便分析礼物类型丢失的原因
                        if (!giftName || giftName === null || giftName === undefined || giftName.length === 0 || giftName === 'None') {{
                            // 记录详细的调试信息：记录"用户送出了×"中间缺失的信息
                            const missingInfo = {{
                                user: user || '未知用户',
                                allText: allText.substring(0, 300), // 完整文本（前300字符）
                                spans: spans.slice(0, 15), // 前15个span元素
                                childTexts: childTexts.slice(0, 15), // 前15个子文本
                                sendIndex: sendIndex, // "送"或"送出了"的位置
                                sendText: sendText, // "送"或"送出了"的文本
                                giftCount: giftCount, // 礼物数量
                                sourceType: sourceType, // 来源类型
                                // 提取"用户送出了×"中间的内容
                                betweenUserAndSend: sendIndex > 0 ? (spans[sendIndex - 1] || childTexts[sendIndex - 1] || '') : '',
                                betweenSendAndCount: sendIndex >= 0 && (sendIndex + 1 < spans.length || sendIndex + 1 < childTexts.length) ? 
                                    (spans[sendIndex + 1] || childTexts[sendIndex + 1] || '') : '',
                                // 尝试从不同位置提取礼物名称
                                afterSendText: allText.indexOf('送出了') >= 0 ? 
                                    allText.substring(allText.indexOf('送出了') + 3, allText.indexOf('×') > 0 ? allText.indexOf('×') : allText.length).trim() : '',
                                beforeCountText: allText.indexOf('×') > 0 ? 
                                    allText.substring(0, allText.indexOf('×')).split('送出了')[1]?.trim() || '' : '',
                                // 查找"送出了"和"×"之间的所有文本
                                betweenSendAndX: allText.indexOf('送出了') >= 0 && allText.indexOf('×') > allText.indexOf('送出了') ?
                                    allText.substring(allText.indexOf('送出了') + 3, allText.indexOf('×')).trim() : ''
                            }};
                            
                            logVerbose('gift_name_missing', '[礼物名称缺失] 用户送出了×中间缺失的信息', missingInfo);
                            return;
                        }}
                        
                        // 额外检查：如果礼物名和用户名相同，说明提取错误，应该过滤掉（先检查这个，避免误判）
                        if (user && (giftName === user || giftName === user.trim())) {{
                            return;
                        }}
                        
                        // 验证礼物名称：如果包含已知关键词，或者礼物名不是用户名，就允许发送
                        const hasGiftKeyword = giftKeywordList.some(keyword => giftName.includes(keyword));
                        // 如果礼物名不包含关键词，但礼物名不是用户名且长度合理，也允许发送（可能是新的礼物类型）
                        const isGiftNameValid = hasGiftKeyword || (giftName !== user && giftName.length > 0 && giftName.length < 50);
                        if (!isGiftNameValid) {{
                            return;
                        }}
                        
                        // 确保礼物信息包含用户ID和礼物类型：必须有礼物名称，用户名可以为空（但会显示为"未知用户"）
                        if (giftName && giftName !== null && giftName !== undefined && giftName.length > 0 && giftName !== 'None') {{
                            // 内容去重：检查是否在10秒内捕获过相同的礼物（使用用户名+礼物名+数量作为key）
                            const contentKey = (user || '未知用户') + '|' + giftName + '|' + (giftCount || 1);
                            const lastTime = giftContentCache.get(contentKey);
                            if (lastTime && (now - lastTime) < GIFT_CACHE_TTL) {{
                                return; // 10秒内相同内容不重复捕获
                            }}
                            
                            // 更新缓存
                            giftCache.add(uniqueId);
                            if (giftCache.size > 500) {{
                                giftCache.delete(giftCache.values().next().value);
                            }}
                            giftContentCache.set(contentKey, now);
                            
                            // 清理过期的内容缓存
                            if (giftContentCache.size > 200) {{
                                for (let [key, timestamp] of giftContentCache.entries()) {{
                                    if (now - timestamp > GIFT_CACHE_TTL) {{
                                        giftContentCache.delete(key);
                                    }}
                                }}
                            }}
                            
                            // 最终验证：确保礼物名称有效（不为空、不为null、不为undefined、不为'None'）
                            if (giftName && giftName !== null && giftName !== undefined && giftName.length > 0 && giftName !== 'None') {{
                                // 计算礼物更新间隔
                                let intervalSinceLastGift = 0;
                                if (lastGiftUpdateTime > 0) {{
                                    intervalSinceLastGift = now - lastGiftUpdateTime;
                                    // 记录间隔（只记录合理的间隔，排除异常值）
                                    if (intervalSinceLastGift > 0 && intervalSinceLastGift < 60000) {{ // 小于60秒
                                        giftUpdateIntervals.push(intervalSinceLastGift);
                                        if (giftUpdateIntervals.length > MAX_INTERVALS) {{
                                            giftUpdateIntervals.shift(); // 移除最旧的
                                        }}
                                        
                                        // 计算平均间隔，用于动态调整扫描频率
                                        if (giftUpdateIntervals.length >= 3) {{
                                            const avgInterval = giftUpdateIntervals.reduce((a, b) => a + b, 0) / giftUpdateIntervals.length;
                                            // 扫描间隔设为平均间隔的1/2，但不少于200ms，不超过2000ms
                                            currentScanInterval = Math.max(200, Math.min(2000, Math.floor(avgInterval / 2)));
                                            // 重新设置扫描定时器
                                            if (scanTimer) {{
                                                clearInterval(scanTimer);
                                            }}
                                            scanTimer = setInterval(scan, currentScanInterval);
                                        }}
                                    }}
                                }}
                                
                                // 更新上次礼物更新时间
                                lastGiftUpdateTime = now;
                                
                                // 只发送礼物信息，不记录调试日志（减少冗余）
                                window.sendToPy({{type: 'gift', user: user || '未知用户', gift_name: giftName, gift_count: giftCount}});
                                
                                // 只在礼物更新时输出日志，包含间隔信息
                                const meaningfulText = allText.split('\n').filter(line => {{
                                    const trimmed = line.trim();
                                    return trimmed.length > 0 && 
                                           (trimmed.includes(user || '') || 
                                            trimmed.includes(giftName) || 
                                            trimmed.includes('送出了') ||
                                            trimmed.includes('送'));
                                }}).join(' | ');
                                
                                // 计算平均间隔用于显示
                                const avgInterval = giftUpdateIntervals.length > 0 
                                    ? Math.floor(giftUpdateIntervals.reduce((a, b) => a + b, 0) / giftUpdateIntervals.length)
                                    : 0;
                                
                                logVerbose('gift_captured', '[礼物捕获成功]', {{
                                    user: user || '未知用户',
                                    giftName: giftName,
                                    giftCount: giftCount,
                                    intervalSinceLastGift: intervalSinceLastGift,
                                    avgInterval: avgInterval,
                                    currentScanInterval: currentScanInterval,
                                    meaningfulText: meaningfulText.substring(0, 200),
                                    dataIndex: node.hasAttribute('data-index') ? node.getAttribute('data-index') : '',
                                    uniqueId,
                                    sourceType
                                }});
                            }} else {{
                                // 如果礼物名称无效，直接返回，不记录日志（减少冗余）
                                return;
                            }}
                        }} else {{
                            // 记录未通过isGiftMessage检查的节点
                            logVerbose('gift_check_failed', '[礼物检查失败] 未通过isGiftMessage检查', {{
                                uniqueId,
                                hasSendOut,
                                hasSend,
                                hasGiftKeyword,
                                hasUserFormat,
                                textLength,
                                isGiftList: isGiftList(allText),
                                isRealtimeInfo: isRealtimeInfo(allText),
                                textPreview: textPreview
                            }});
                        }}
                    }}
                }});
                
                // 不再输出扫描统计，减少冗余日志
                // if (nodes.length > 0) {{
                //     logVerbose('gift_scan_stats', '[礼物扫描统计]', {{
                //         sourceType,
                //         totalNodes: nodes.length,
                //         processedCount,
                //         skippedCount,
                //         cachedCount: giftCache.size
                //     }});
                // }}
            }}
            
            function scanViewerCount() {{
                const viewerCountEl = document.querySelector('div[data-e2e="live-room-audience"]');
                if (viewerCountEl) {{
                    let count = viewerCountEl.innerText.trim();
                    let now = Date.now();
                    
                    if (count && count !== lastViewerCount && now - viewerCountUpdateTime > 5000) {{
                        lastViewerCount = count;
                        viewerCountUpdateTime = now;
                        window.sendToPy({{type: 'viewer_count', viewer_count: count}});
                    }}
                }}
            }}
            
            // 扫描本场点赞数量（常驻信息）
            let lastLikeCount = '';
            let likeCountUpdateTime = 0;
            function scanLikeCount() {{
                try {{
                    // 查找包含"本场点赞"的元素
                    const allElements = document.querySelectorAll('div, span, p');
                    for (let el of allElements) {{
                        const text = (el.innerText || el.textContent || '').trim();
                        if (text.includes('本场点赞')) {{
                            // 提取点赞数量（格式：XXX万本场点赞 或 XXX本场点赞）
                            const match = text.match(/([\d.]+万?)\s*本场点赞/);
                            if (match && match[1]) {{
                                let likeCount = match[1].trim();
                                let now = Date.now();
                                
                                if (likeCount && likeCount !== lastLikeCount && now - likeCountUpdateTime > 5000) {{
                                    lastLikeCount = likeCount;
                                    likeCountUpdateTime = now;
                                    window.sendToPy({{type: 'like_count', like_count: likeCount}});
                                }}
                            }}
                            break; // 找到后退出
                        }}
                    }}
                }} catch (e) {{
                    // 静默处理错误
                }}
            }}
            
            // 扫描直播画面左下角的用户列表区域（明文礼物信息）- 重要来源
            function scanLeftBottomUserList() {{
                try {{
                    // 方法1: 基于DOM选择器的定位方式（优先使用）
                    // 尝试直接找到礼物信息的DOM元素，而不是通过文本匹配
                    const domSelectorGifts = [];
                    const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
                    const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
                    
                    // 调试：记录DOM选择器扫描过程
                    let domSelectorDebugCount = 0;
                    const domSelectorDebugKey = 'dom_selector_debug';
                    const shouldLogDomDebug = !window[domSelectorDebugKey] || (Date.now() - window[domSelectorDebugKey]) > 3000;
                    
                    // 尝试多种选择器来定位礼物信息
                    // 1. 查找包含"送"字的元素，且位置在左下角区域
                    // 简化：直接查找所有div和span元素，然后过滤
                    const allElements = document.querySelectorAll('div, span, p');
                    let domSelectorChecked = 0;
                    let domSelectorMatched = 0;
                    
                    allElements.forEach(el => {{
                        const text = (el.innerText || el.textContent || '').trim();
                        if (!text || text.length < 3 || !text.includes('送')) return;
                        
                        domSelectorChecked++;
                        const rect = el.getBoundingClientRect();
                        
                        // 检查位置：左下角区域（左侧70%，底部20%以上）- 更宽松
                        // 对于包含礼物信息的文本，即使位置是left:0 top:0也要处理（可能是容器节点）
                        const isLeftSide = rect.left < viewportWidth * 0.7;
                        const isBottomArea = rect.top > viewportHeight * 0.2;
                        const isLeftArea = rect.left < viewportWidth * 0.8;
                        const isShortGiftText = text.length < 150 && text.includes('送');
                        const isZeroPosition = rect.left === 0 && rect.top === 0; // 可能是容器节点
                        
                        // 放宽位置判断：只要在左侧或文本较短，都认为是可能的礼物区域
                        // 对于left:0 top:0的位置，如果包含礼物信息，也处理（可能是容器节点）
                        if (isLeftSide || isLeftArea || isShortGiftText || isZeroPosition) {{
                            // 使用关键词匹配方式提取礼物信息
                            // 所有礼物名称列表（包括粉丝团和灯牌，按长度从长到短排序，优先匹配长名称）
                            const giftKeywords = [
                                '点亮粉丝团', '粉丝团灯牌', '浪漫雪绘', '为你闪耀',
                                '粉丝团', '灯牌', '玫瑰', '小心心', '棒棒糖', '鲜花', '亲吻', 'Thuglife', '礼花筒', '真的爱你',
                                '浪漫花火', '抖音1号', '红包', '冬雪之爱', '冰封誓约', '雪落生花', '萌狐戏雪',
                                '星愿雪淞', '冰雪城堡', '日照金山', '跑车', '热气球', '比心兔兔', '抖音飞艇',
                                '豪华邮轮', '云中秘境', 'PK宝箱', '万象烟花', '人气票', '真爱玫瑰',
                                '一束花开', '闪耀星辰', '浪漫恋人', '一路有你', '浪漫马车', '梦幻城堡',
                                '掌上明珠', '为爱启航', '花落长亭', '星际玫瑰', '海上生明月', '捏捏小脸',
                                '天空之镜', '花海泛舟', '真爱永恒', '情定三生', '梦幻蝶翼', '天使之翼',
                                '暗夜之翼', '大圣抢亲', '闪光舞台', '豪华蛋糕', '胡萝卜', '随机舞蹈',
                                '魔法镜', '逗兔棒', '游戏手柄', '拯救爱播', '摩天大厦', '环游世界',
                                '雪绒花', '火龙爆发', '荧光棒', '光之祝福', '奇幻八音盒', '龙抬头',
                                '为你举牌', '爱情树下', '星星点灯', '纸短情长', '云霄大厦', '月下瀑布',
                                '黄桃罐头', '蝶・连理枝', '趣玩泡泡', '蜜蜂叮叮', '灵龙现世', '奏响人生',
                                '永生花', 'ONE礼挑一', '冰冻战车', '炫彩射击', '拳拳出击', '爱的纸鹤',
                                '爱你哟', '大啤酒', '直升机', '嘉年华', '比心', '加油鸭', '送你花花',
                                '你最好看', '抖音', '私人飞机'
                            ];
                            
                            // 页面结构关键词（用于过滤）
                            const pageStructureKeywords = ['潇洒哥', '无畏契约', '本场点赞', '关注', '小时榜', '人气榜', '自动', '直播加载中', 'G', '100+', '万', '重庆第', '名'];
                            
                            // 查找所有"送"字的位置
                            const sendIndexes = [];
                            for (let i = 0; i < text.length; i++) {{
                                if (text[i] === '送' || (i < text.length - 1 && text.substring(i, i + 2) === '送')) {{
                                    sendIndexes.push(i);
                                }}
                            }}
                            
                            // 对每个"送"字，尝试提取礼物信息
                            sendIndexes.forEach(sendIndex => {{
                                // 提取"送"之前的文本作为潜在用户名
                                const beforeSend = text.substring(0, sendIndex).trim();
                                // 提取"送"之后的文本
                                const afterSend = text.substring(sendIndex + 1).trim();
                                
                                // 查找礼物名称（在"送"之后，优先匹配长名称）
                                let foundGift = null;
                                let giftStartIndex = -1;
                                let giftEndIndex = -1;
                                
                                for (const giftKeyword of giftKeywords) {{
                                    const index = afterSend.indexOf(giftKeyword);
                                    if (index >= 0 && index < 100) {{ // 礼物名称应该在"送"之后100字符内
                                        foundGift = giftKeyword;
                                        giftStartIndex = index;
                                        giftEndIndex = index + giftKeyword.length;
                                        break;
                                    }}
                                }}
                                
                                if (foundGift) {{
                                    // 提取用户名（"送"之前的最后一行或最后一段）
                                    let user = beforeSend;
                                    // 如果包含换行，取最后一行
                                    const lastNewlineIndex = user.lastIndexOf('\n');
                                    if (lastNewlineIndex >= 0) {{
                                        user = user.substring(lastNewlineIndex + 1).trim();
                                    }}
                                    // 如果用户名太长，可能是页面结构，跳过
                                    if (user.length > 50) {{
                                        return;
                                    }}
                                    
                                    // 提取数量（在礼物名称之后查找 x/×/X + 数字）
                                    const afterGift = afterSend.substring(giftEndIndex);
                                    const countMatch = afterGift.match(/[x×X]\s*(\d+)/);
                                    const giftCount = countMatch ? countMatch[1] : '1';
                                    
                                    // 验证用户名不是页面结构关键词
                                    const isPageStructure = pageStructureKeywords.some(keyword => 
                                        user.includes(keyword) || user === keyword
                                    );
                                    
                                    // 基本验证
                                    if (user.length > 0 && 
                                        user.length <= 50 &&
                                        !isPageStructure &&
                                        user !== '自动' && user !== '直播加载中' &&
                                        !/^\d+$/.test(user)) {{
                                        domSelectorMatched++;
                                        domSelectorGifts.push({{
                                            user: user,
                                            giftName: foundGift,
                                            giftCount: giftCount,
                                            element: el,
                                            text: text.substring(0, 100),
                                            method: 'keyword_match',
                                            position: 'left:' + Math.floor(rect.left) + ' top:' + Math.floor(rect.top)
                                        }});
                                    }}
                                }}
                            }});
                        }}
                    }});
                    
                    // 调试：记录DOM选择器扫描结果（增加详细调试信息）
                    if (shouldLogDomDebug) {{
                        window[domSelectorDebugKey] = Date.now();
                        // 记录一些匹配失败的示例文本，用于调试
                        let sampleFailedText = '';
                        if (domSelectorMatched === 0 && domSelectorChecked > 0) {{
                            // 如果匹配数为0但检查数>0，记录一个示例文本
                            const sampleEl = Array.from(allElements).find(el => {{
                                const text = (el.innerText || el.textContent || '').trim();
                                return text && text.length >= 3 && text.includes('送');
                            }});
                            if (sampleEl) {{
                                sampleFailedText = (sampleEl.innerText || sampleEl.textContent || '').substring(0, 100).replace(/\n/g, '\\n');
                            }}
                        }}
                        logVerbose('gift_scan_debug', '[DOM选择器扫描] 检查:' + domSelectorChecked + ' 匹配:' + domSelectorMatched + ' 礼物数:' + domSelectorGifts.length + (sampleFailedText ? ' 示例文本:' + sampleFailedText : ''), {{
                            checked: domSelectorChecked,
                            matched: domSelectorMatched,
                            giftsFound: domSelectorGifts.length,
                            sampleText: sampleFailedText
                        }});
                    }}
                    
                    // 如果通过DOM选择器找到了礼物信息，优先使用
                    if (domSelectorGifts.length > 0) {{
                        // 去重和排序：使用用户+礼物名+数量作为唯一标识
                        // 按时间戳排序（后出现的优先，因为可能是最新的）
                        const uniqueGifts = new Map();
                        const giftTimestamps = new Map();
                        domSelectorGifts.forEach((gift, index) => {{
                            const key = gift.user + '|' + gift.giftName + '|' + gift.giftCount;
                            // 如果已经存在，保留最新的（索引更大的）
                            if (!uniqueGifts.has(key) || (giftTimestamps.get(key) || 0) < index) {{
                                uniqueGifts.set(key, gift);
                                giftTimestamps.set(key, index);
                            }}
                        }});
                        
                        // 转换为数组并排序（按时间戳降序，最新的在前）
                        const sortedGifts = Array.from(uniqueGifts.values()).sort((a, b) => {{
                            const keyA = a.user + '|' + a.giftName + '|' + a.giftCount;
                            const keyB = b.user + '|' + b.giftName + '|' + b.giftCount;
                            return (giftTimestamps.get(keyB) || 0) - (giftTimestamps.get(keyA) || 0);
                        }});
                        
                        // 发送找到的礼物信息（二次优化输出：只输出用户+礼物类型+数量）
                        // 使用更严格的去重机制，只发送新捕获的礼物（定义为礼物消息）
                        const newGifts = [];
                        const now = Date.now();
                        
                        sortedGifts.forEach(gift => {{
                            const contentKey = gift.user + '|' + gift.giftName + '|' + gift.giftCount;
                            const lastTime = giftContentCache.get(contentKey);
                            
                            // 检查是否在缓存期内（60秒内相同内容不重复捕获）
                            if (lastTime && (now - lastTime) < GIFT_CACHE_TTL) {{
                                return; // 跳过已捕获的礼物
                            }}
                            
                            // 更新缓存时间戳
                            giftContentCache.set(contentKey, now);
                            newGifts.push(gift);
                        }});
                        
                        // 只输出新捕获的礼物信息（避免重复输出）
                        if (newGifts.length > 0) {{
                            // 记录排序后的礼物信息到日志（只记录新捕获的）
                            const sortedGiftsText = newGifts.map((gift, index) => {{
                                return `[${{index + 1}}] ${{gift.user}} 送 ${{gift.giftName}}${{gift.giftCount && gift.giftCount !== '1' ? ' ×' + gift.giftCount : ''}}`;
                            }}).join(' | ');
                            logVerbose('gift_sorted_list', '[排序后的礼物列表] 共' + newGifts.length + '个: ' + sortedGiftsText, {{
                                total: newGifts.length,
                                gifts: newGifts.map(gift => ({{
                                    user: gift.user,
                                    giftName: gift.giftName,
                                    giftCount: gift.giftCount,
                                    display: gift.user + ' 送 ' + gift.giftName + (gift.giftCount && gift.giftCount !== '1' ? ' ×' + gift.giftCount : '')
                                }}))
                            }});
                            
                            // 发送新捕获的礼物信息（定义为礼物消息）
                            newGifts.forEach(gift => {{
                                const displayText = gift.user + ' 送 ' + gift.giftName + (gift.giftCount && gift.giftCount !== '1' ? ' ×' + gift.giftCount : '');
                                
                                // 发送礼物信息（定义为礼物消息）
                                window.sendToPy({{
                                    type: 'gift',
                                    user: gift.user,
                                    gift_name: gift.giftName,
                                    gift_count: gift.giftCount,
                                    source: 'left_bottom_user_list',
                                    method: gift.method || 'keyword_match',
                                    display_text: displayText
                                }});
                            }});
                        }}
                        
                        // 清理过期的缓存（避免内存泄漏）
                        if (giftContentCache.size > 500) {{
                            for (let [key, timestamp] of giftContentCache.entries()) {{
                                if (now - timestamp > GIFT_CACHE_TTL * 2) {{ // 清理超过2倍缓存时间的条目
                                    giftContentCache.delete(key);
                                }}
                            }}
                        }}
                        
                        // 如果通过DOM选择器找到了礼物信息，不再使用正则表达式方式
                        return;
                    }}
                    
                    // 方法2: 基于正则表达式的匹配方式（备选）
                    // 重用之前查询的元素（如果DOM选择器方式没有找到礼物，继续使用相同的元素列表）
                    // 注意：如果DOM选择器方式已经return了，这里的代码不会执行
                    let foundCount = 0;
                    let matchedCount = 0;
                    let positionFilteredCount = 0;
                    let patternMatchedCount = 0;
                    let totalElements = allElements.length;
                    
                    // 重用之前定义的视口尺寸（避免重复计算）
                    
                    allElements.forEach(el => {{
                        const text = (el.innerText || el.textContent || '').trim();
                        if (!text || text.length < 3) return;
                        
                        // 检查是否包含"送"关键词（通用礼物格式：用户名 送礼物名 x数量）
                        if (!text.includes('送')) return;
                        
                        foundCount++;
                        
                        // 检查元素位置（左下角区域）- 先检查位置，再记录调试信息
                        const rect = el.getBoundingClientRect();
                        
                        // 临时调试：记录包含"送"的文本（减少输出频率，只记录前10次，之后每5秒记录一次）
                        // 并且只记录可能包含有效礼物信息的文本（过滤掉明显无效的文本）
                        const debugTextKey = 'left_bottom_text_debug';
                        const debugTextCountKey = 'left_bottom_text_debug_count';
                        if (!window[debugTextCountKey]) window[debugTextCountKey] = 0;
                        window[debugTextCountKey]++;
                        
                        // 过滤掉明显无效的文本（如"送出了 × 1"这种不完整的礼物信息）
                        const hasValidGiftPattern = /[^\n送]{1,30}[\s\n]*送[\s\n]*[^x×X\n]{1,50}/.test(text);
                        const shouldLogText = hasValidGiftPattern && (
                            window[debugTextCountKey] <= 10 || 
                            !window[debugTextKey] || 
                            (Date.now() - window[debugTextKey]) > 5000
                        );
                        if (shouldLogText) {{
                            window[debugTextKey] = Date.now();
                            logVerbose('gift_text_debug', '[左下角文本调试] 文本:' + text.substring(0, 100).replace(/\n/g, '\\n'), {{
                                text: text.substring(0, 200).replace(/\n/g, '\\n'),
                                textLength: text.length,
                                hasSend: text.includes('送'),
                                hasValidPattern: hasValidGiftPattern,
                                position: 'left:' + Math.floor(rect.left) + ' top:' + Math.floor(rect.top)
                            }});
                        }}
                        
                        // 判断是否在左下角区域（放宽位置判断：左侧60%，下半部分30%）
                        // 左下角的礼物信息可能在屏幕的左下角，也可能在左侧中间位置
                        // 进一步放宽：如果文本较短（<100字符）且包含"送"，也认为是可能的礼物区域
                        const isLeftSide = rect.left < viewportWidth * 0.6;  // 放宽到60%
                        const isBottomArea = rect.top > viewportHeight * 0.3;  // 放宽到30%
                        const isLeftBottom = isLeftSide && isBottomArea;
                        
                        // 如果不在左下角，也检查是否在左侧（可能是用户列表）
                        // 放宽判断：只要在左侧70%范围内，都认为是可能的礼物区域
                        // 或者文本较短（<100字符）且包含"送"，也认为是可能的礼物区域
                        const isLeftArea = rect.left < viewportWidth * 0.7;
                        const isShortGiftText = text.length < 100 && text.includes('送');
                        if (!isLeftBottom && !isLeftArea && !isShortGiftText) {{
                            positionFilteredCount++;
                            return;
                        }}
                        
                        patternMatchedCount++;
                        
                        // 生成唯一标识符
                        const itemId = text.substring(0, 80).replace(/[\s\n\r]/g, '_') + '_' + 
                                    String(Math.floor(rect.top || 0)) + '_' + String(Math.floor(rect.left || 0));
                        
                        // 检查是否已经处理过
                        if (giftContainerCache.has(itemId)) return;
                        giftContainerCache.add(itemId);
                        if (giftContainerCache.size > 500) {{
                            const firstKey = giftContainerCache.values().next().value;
                            giftContainerCache.delete(firstKey);
                        }}
                        
                        // 提取用户和礼物信息 - 支持格式："用户名 送礼物名 x数量" 或 "用户名 送礼物名"
                        let user = '';
                        let giftName = '';
                        let giftCount = '1';
                        
                        // 无效前缀列表（不应该被识别为用户名的内容）
                        const invalidPrefixes = ['自动', '直播加载中', '本场点赞', '关注', '小时榜', '人气榜', '在线观众', '全部', '贡献用户', '高等级用户', '加入', '需先登录', '才能开始聊天', '更多', '充值', 'G', '+', '加载中', '已登录', '等我刷把宗师', '万本场点赞', '万', '钻'];
                        
                        // 检查是否包含页面结构关键词（如果包含，说明是页面容器，不是单个礼物信息）
                        // 放宽过滤：只过滤明显是页面结构的文本，不要过度过滤
                        const pageStructureKeywords = ['等我刷把宗师', '本场点赞', '关注', '小时榜', '人气榜', '在线观众', '全部', '贡献用户', '高等级用户', '自动直播加载中', '万本场点赞', '需先登录', '才能开始聊天'];
                        // 只有当文本明显是页面结构时才跳过（文本长度较长且包含多个关键词）
                        // 进一步放宽：如果文本较短（<100字符），即使包含关键词也不跳过（可能是单个礼物信息）
                        const keywordCount = pageStructureKeywords.filter(keyword => text.includes(keyword)).length;
                        if (keywordCount >= 2 && text.length > 100) {{
                            return; // 跳过明显的页面结构容器（长文本且包含多个关键词）
                        }}
                        
                        // 方法1: 匹配"用户名 送礼物名 x数量"格式（支持多种格式）
                        // 简化逻辑：只要找到"送"字，提取前后的文本作为用户名和礼物名
                        // 用户名：在"送"之前，不包含"送"和换行符的连续字符（最多30个字符，允许任何字符包括特殊字符和emoji）
                        // 礼物名：在"送"之后，到"x"、"×"、"X"或换行符之前（最多50个字符）
                        // 使用更宽松的匹配，支持换行符和空格
                        // 优化：使用非贪婪匹配，确保能正确匹配包含emoji的用户名
                        // 注意：使用 [^\n送] 而不是 [\S] 来避免匹配空格，但允许emoji和特殊字符
                        const pattern1Global = /([^\n送]{1,30})[\s\n]*送[\s\n]*([^x×X\n]{1,50}?)(?:\s*[x×X]\s*(\d+)|\s+(\d+))?/g;
                        const allMatches = [];
                        let m;
                        // 重置正则表达式的 lastIndex，避免全局匹配的问题
                        pattern1Global.lastIndex = 0;
                        while ((m = pattern1Global.exec(text)) !== null) {{
                            allMatches.push(m);
                        }}
                        
                        // 如果匹配到多个礼物，需要判断是否是容器节点
                        // 检查当前元素的文本长度和结构，如果文本较短且只包含一个完整的礼物信息，仍然处理
                        const textLength = text.length;
                        const isShortText = textLength < 200; // 短文本可能是单个礼物节点
                        const giftPatternCount = (text.match(/[\s\n]*送[\s\n]*/g) || []).length; // 统计"送"的数量（与主正则一致）
                        
                        // 如果匹配到多个礼物，但文本较短且"送"的数量较少，可能是单个礼物节点（包含换行）
                        // 或者如果只匹配到一个，直接处理
                        // 放宽条件：如果文本较短（<200字符），即使包含多个礼物也处理第一个
                        if (allMatches.length > 1 && !isShortText && giftPatternCount > 2) {{
                            return; // 跳过容器节点（长文本且包含多个"送"）
                        }}
                        
                        // 如果匹配到一个或多个，使用第一个匹配结果（如果只有一个，就是它；如果有多个但当前元素是单个礼物，也使用第一个）
                        if (allMatches.length >= 1) {{
                            match1 = allMatches[0];
                            let potentialUser = match1[1].trim();
                            let potentialGiftName = match1[2].trim();
                            
                            // 临时调试：记录匹配到的内容（每5秒记录一次）
                            const debugKey = 'left_bottom_pattern_match';
                            if (!window[debugKey] || (Date.now() - window[debugKey]) > 5000) {{
                                window[debugKey] = Date.now();
                                logVerbose('gift_pattern_match', '[左下角正则匹配] 用户:' + potentialUser + ' 礼物:' + potentialGiftName + ' 文本:' + text.substring(0, 80), {{
                                    potentialUser,
                                    potentialGiftName,
                                    userLength: potentialUser.length,
                                    giftNameLength: potentialGiftName.length,
                                    text: text.substring(0, 100)
                                }});
                            }}
                            
                            // 清理用户名和礼物名：去除前后空白和换行符，以及页面结构关键词
                            potentialUser = potentialUser.replace(/^[\s\n]+|[\s\n]+$/g, '').trim();
                            potentialGiftName = potentialGiftName.replace(/^[\s\n]+|[\s\n]+$/g, '').trim();
                            
                            // 过滤掉页面结构关键词（如"自动"、"直播加载中"等）
                            if (potentialUser === '自动' || potentialUser === '直播加载中' || 
                                potentialUser.includes('直播加载中') || potentialUser.includes('自动直播') ||
                                potentialUser === '送' || potentialUser.length === 0) {{
                                return; // 跳过页面结构文本
                            }}
                            
                            // 过滤无效用户名（放宽用户名长度限制：1-30）
                            // 只要用户名和礼物名都不为空，且不是页面结构关键词，就接受
                            if (potentialUser.length >= 1 && potentialUser.length <= 30 && 
                                !invalidPrefixes.some(prefix => potentialUser.includes(prefix)) &&
                                !/^\d+$/.test(potentialUser) &&
                                !potentialUser.includes('万') &&
                                !potentialUser.includes('钻') &&
                                potentialGiftName.length > 0 &&
                                potentialGiftName !== '自动' &&
                                potentialGiftName !== '直播加载中' &&
                                potentialGiftName !== '送') {{
                                user = potentialUser;
                                giftName = potentialGiftName;
                                // 提取数量（支持x数量和纯数量两种格式）
                                if (match1[3]) {{
                                    giftCount = match1[3].toString();
                                }} else if (match1[4]) {{
                                    giftCount = match1[4].toString();
                                }} else {{
                                    giftCount = '1'; // 默认数量为1
                                }}
                            }} else {{
                                // 临时调试：记录验证失败的原因
                                const debugKey2 = 'left_bottom_validation_reason';
                                if (!window[debugKey2] || (Date.now() - window[debugKey2]) > 5000) {{
                                    window[debugKey2] = Date.now();
                                    let reason = '';
                                    if (potentialUser.length < 1 || potentialUser.length > 30) reason = '用户名长度不符合(' + potentialUser.length + ')';
                                    else if (invalidPrefixes.some(prefix => potentialUser.includes(prefix))) reason = '用户名包含无效前缀';
                                    else if (/^\d+$/.test(potentialUser)) reason = '用户名为纯数字';
                                    else if (potentialUser.includes('万') || potentialUser.includes('钻')) reason = '用户名包含万/钻';
                                    else if (potentialGiftName.length === 0) reason = '礼物名为空';
                                    logVerbose('gift_validation_reason', '[左下角验证失败] ' + reason + ' 用户:' + potentialUser + ' 礼物:' + potentialGiftName, {{
                                        reason,
                                        potentialUser,
                                        potentialGiftName,
                                        text: text.substring(0, 100)
                                    }});
                                }}
                            }}
                        }} else if (allMatches.length === 0) {{
                            // 临时调试：记录正则匹配失败的情况（每3秒记录一次，或者前10次每次都记录）
                            const debugKey3 = 'left_bottom_pattern_failed';
                            const debugCountKey3 = 'left_bottom_pattern_failed_count';
                            if (!window[debugCountKey3]) window[debugCountKey3] = 0;
                            window[debugCountKey3]++;
                            const shouldLogFailed = window[debugCountKey3] <= 10 || 
                                                   !window[debugKey3] || 
                                                   (Date.now() - window[debugKey3]) > 3000;
                            if (shouldLogFailed) {{
                                window[debugKey3] = Date.now();
                                // 尝试使用更宽松的正则表达式进行匹配测试
                                // 使用更宽松的模式：允许用户名包含任何字符（除了换行和"送"），礼物名也允许任何字符（除了x×X和换行）
                                const relaxedPattern = /([^\n送]{1,30}?)[\s\n]*送[\s\n]*([^x×X\n]{1,50}?)(?:\s*[x×X]\s*(\d+)|\s+(\d+))?/;
                                relaxedPattern.lastIndex = 0;
                                const relaxedMatch = relaxedPattern.exec(text);
                                // 如果宽松匹配成功，说明正则表达式本身没问题，可能是其他原因导致匹配失败
                                if (relaxedMatch) {{
                                    const relaxedUser = relaxedMatch[1].trim();
                                    const relaxedGift = relaxedMatch[2].trim();
                                    const relaxedCount = relaxedMatch[3] || relaxedMatch[4] || '1';
                                    logVerbose('gift_pattern_failed', '[左下角正则匹配失败但宽松匹配成功] 用户:' + relaxedUser + ' 礼物:' + relaxedGift + ' 数量:' + relaxedCount, {{
                                        text: text.substring(0, 200).replace(/\n/g, '\\n'),
                                        hasSend: text.includes('送'),
                                        textLength: text.length,
                                        relaxedMatch: relaxedUser + ' 送 ' + relaxedGift + (relaxedCount !== '1' ? ' ×' + relaxedCount : ''),
                                        relaxedUser: relaxedUser,
                                        relaxedGift: relaxedGift,
                                        relaxedCount: relaxedCount
                                    }});
                                }} else {{
                                    // 如果宽松匹配也失败，尝试最简单的模式：只匹配"送"前后的文本
                                    const simplePattern = /([^\n送]+?)[\s\n]*送[\s\n]*([^\n]+?)(?:\s*[x×X]\s*(\d+))?/;
                                    simplePattern.lastIndex = 0;
                                    const simpleMatch = simplePattern.exec(text);
                                    if (simpleMatch) {{
                                        logVerbose('gift_pattern_failed', '[左下角正则匹配失败但简单匹配成功] 用户:' + simpleMatch[1].trim() + ' 礼物:' + simpleMatch[2].trim(), {{
                                            text: text.substring(0, 200).replace(/\n/g, '\\n'),
                                            hasSend: text.includes('送'),
                                            textLength: text.length,
                                            simpleMatch: simpleMatch[1].trim() + ' 送 ' + simpleMatch[2].trim()
                                        }});
                                    }} else {{
                                        logVerbose('gift_pattern_failed', '[左下角正则匹配失败] 文本:' + text.substring(0, 100), {{
                                            text: text.substring(0, 200).replace(/\n/g, '\\n'),
                                            hasSend: text.includes('送'),
                                            textLength: text.length
                                        }});
                                    }}
                                }}
                            }}
                        }}
                        
                        // 方法2: 如果方法1失败，尝试从父元素中提取（但需要确保父元素不是容器节点）
                        if (!user || !giftName) {{
                            let parent = el.parentElement;
                            let depth = 0;
                            while (parent && depth < 5) {{
                                const parentText = (parent.innerText || parent.textContent || '').trim();
                                
                                // 检查父元素是否包含页面结构关键词
                                if (pageStructureKeywords.some(keyword => parentText.includes(keyword))) {{
                                    parent = parent.parentElement;
                                    depth++;
                                    continue; // 跳过包含页面结构的父元素
                                }}
                                
                                // 检查父元素是否包含多个礼物
                                const parentPattern = /([^\s\n]{1,30})\s+送\s+([^x×X\s\n]+?)(?:\s*[x×X]\s*(\d+)|\s+(\d+))?/g;
                                const parentMatches = [];
                                let pm;
                                while ((pm = parentPattern.exec(parentText)) !== null) {{
                                    parentMatches.push(pm);
                                }}
                                
                                // 如果父元素包含多个礼物，跳过
                                if (parentMatches.length > 1) {{
                                    parent = parent.parentElement;
                                    depth++;
                                    continue;
                                }}
                                
                                // 如果只包含一个礼物，尝试提取
                                if (parentMatches.length === 1) {{
                                    let parentMatch = parentMatches[0];
                                    let potentialUser = parentMatch[1].trim();
                                    if (potentialUser.length >= 2 && potentialUser.length <= 25 && 
                                        !invalidPrefixes.some(prefix => potentialUser.includes(prefix)) &&
                                        !/^\d+$/.test(potentialUser) &&
                                        !potentialUser.includes('万') &&
                                        !potentialUser.includes('钻')) {{
                                        user = potentialUser;
                                        giftName = parentMatch[2].trim();
                                        if (parentMatch[3]) {{
                                            giftCount = parentMatch[3].toString();
                                        }} else if (parentMatch[4]) {{
                                            giftCount = parentMatch[4].toString();
                                        }}
                                        break;
                                    }}
                                }}
                                parent = parent.parentElement;
                                depth++;
                            }}
                        }}
                        
                        // 只有当找到用户和礼物名称时才发送（避免发送无效数据）
                        if (user && giftName) {{
                            matchedCount++;
                            // 验证礼物名是否包含已知关键词（放宽验证：只要礼物名不为空且不是用户名，就发送）
                            const hasGiftKeyword = giftKeywordList.some(keyword => giftName.includes(keyword));
                            // 如果礼物名不包含关键词，但礼物名不是用户名，也允许发送（可能是新的礼物类型）
                            const isGiftNameValid = hasGiftKeyword || (giftName !== user && giftName.length > 0 && giftName.length < 50);
                            
                            if (isGiftNameValid) {{
                                // 内容去重：检查是否在10秒内捕获过相同的礼物
                                const contentKey = user + '|' + giftName + '|' + giftCount;
                                const lastTime = giftContentCache.get(contentKey);
                                if (lastTime && (Date.now() - lastTime) < GIFT_CACHE_TTL) {{
                                    return; // 10秒内相同内容不重复捕获
                                }}
                                giftContentCache.set(contentKey, Date.now());
                                
                                // 发送礼物信息（转换为gift类型，以便统一处理）
                                // 简化输出：只包含用户昵称、礼物类型和数量
                                window.sendToPy({{
                                    type: 'gift',
                                    user: user,
                                    gift_name: giftName,
                                    gift_count: giftCount,
                                    source: 'left_bottom_user_list',
                                    // 格式化输出：用户昵称 + 礼物类型 + 数量
                                    display_text: user + ' 送 ' + giftName + (giftCount && giftCount !== '1' ? ' ×' + giftCount : '')
                                }});
                                
                                // 记录左下角礼物捕获成功的日志（简化输出）
                                logVerbose('gift_captured', '[左下角礼物捕获] ' + user + ' 送 ' + giftName + (giftCount && giftCount !== '1' ? ' ×' + giftCount : ''), {{
                                    user: user,
                                    giftName: giftName,
                                    giftCount: giftCount,
                                    source: 'left_bottom_user_list',
                                    display_text: user + ' 送 ' + giftName + (giftCount && giftCount !== '1' ? ' ×' + giftCount : '')
                                }});
                            }} else {{
                                // 临时调试：记录验证失败的礼物（5秒内只记录一次）
                                const debugKey = 'left_bottom_validation_failed_' + giftName;
                                if (!window[debugKey]) {{
                                    window[debugKey] = true;
                                    logVerbose('gift_validation_failed', '[左下角礼物验证失败] 礼物名称不包含已知关键词: ' + giftName, {{
                                        giftName,
                                        user,
                                        text: text.substring(0, 100),
                                        giftKeywordList
                                    }});
                                    setTimeout(() => {{ window[debugKey] = false; }}, 5000);
                                }}
                            }}
                        }}
                    }});
                    
                    // 记录扫描统计（前20次每次都记录，之后每3秒记录一次，或者有候选时记录）
                    const debugStatsKey = 'left_bottom_scan_stats';
                    const scanCountKey = 'left_bottom_scan_count';
                    if (!window[scanCountKey]) window[scanCountKey] = 0;
                    window[scanCountKey]++;
                    
                    const now = Date.now();
                    // 前20次扫描每次都记录，之后每3秒记录一次，或者有候选时记录
                    const shouldLog = window[scanCountKey] <= 20 || 
                                     !window[debugStatsKey] || 
                                     (now - window[debugStatsKey]) > 3000 || 
                                     foundCount > 0;
                    
                    if (shouldLog) {{
                        window[debugStatsKey] = now;
                        const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
                        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
                        logVerbose('gift_scan_stats', '[左下角扫描统计] 总元素' + totalElements + '个, 找到' + foundCount + '个候选, 位置匹配' + patternMatchedCount + '个, 位置过滤' + positionFilteredCount + '个, 最终匹配' + matchedCount + '个', {{
                            totalElements,
                            foundCount,
                            patternMatchedCount,
                            positionFilteredCount,
                            matchedCount,
                            viewportWidth,
                            viewportHeight,
                            scanCount: window[scanCountKey]
                        }});
                    }}
                    
                    // 如果找到候选但没有匹配，记录详细信息用于调试
                    if (foundCount > 0 && matchedCount === 0) {{
                        logVerbose('gift_scan_debug', '[左下角扫描调试] 找到候选但未匹配，可能需要检查正则表达式或位置过滤', {{
                            foundCount,
                            patternMatchedCount,
                            positionFilteredCount,
                            matchedCount
                        }});
                    }}
                }} catch (e) {{
                    // 临时调试：记录错误
                    logVerbose('gift_scan_error', '[左下角扫描错误] ' + e.message, {{
                        error: e.message,
                        stack: e.stack
                    }});
                }}
            }}
            
            function scan() {{
                scanGifts();  // 先扫描礼物（优先级最高）
                scanLeftBottomUserList();  // 扫描左下角用户列表区域（重要来源）
                scanRealtimeInfo();  // 再扫描实时信息
                scanDanmu();  // 最后扫描弹幕（排除礼物和实时信息）
                scanViewerCount();  // 扫描在线人数
                scanLikeCount();  // 扫描本场点赞数量
            }}
            
            // 动态扫描：初始500ms，根据礼物更新间隔自动调整
            scanTimer = setInterval(scan, currentScanInterval);
            window[activeFlag] = true;
            console.log(">>> [V59] 引擎就绪（支持弹幕、礼物、在线人数）实例ID: " + instanceId);
        }})();
        """
        self.browser.page().runJavaScript(js_code)
        self.add_log(f"<span style='color:#98FB98;'>[JavaScript]</span> JavaScript代码已注入")
    
    def _on_danmu_signal(self, data):
        """接收弹幕信号（与正式版相同的处理逻辑）"""
        # 处理弹幕（通过DanmuMonitor处理，会进行过滤）
        self.danmu_monitor.process_danmu(data)
    
    def _on_danmu_received(self, data):
        """数据回调处理（弹幕、礼物、在线人数等，与正式版相同的处理逻辑）"""
        data_type = data.get('type', 'danmu')
        
        # 调试：记录所有接收到的数据（特别是礼物数据）
        if data_type == 'gift':
            import json
            _write_test_log(f"[调试-接收礼物] {json.dumps(data, ensure_ascii=False)}")
        
        if data_type == 'debug_log':
            # 详细调试日志
            log_type = data.get('log_type', '')
            message = data.get('message', '')
            log_data = data.get('data', {})
            
            # 显示礼物扫描相关的调试信息
            if log_type == 'gift_scan_start':
                total_nodes = log_data.get('totalNodes', 0)
                gift_nodes = log_data.get('giftNodes', 0)
                self.add_log(f"<span style='color:#87CEEB;'>[调试]</span> {message}")
            
            elif log_type == 'gift_scan_stats':
                # 显示左下角扫描统计（用于调试）
                message = log_data.get('message', '')
                if '左下角扫描统计' in message:
                    total_elements = log_data.get('totalElements', 0)
                    found_count = log_data.get('foundCount', 0)
                    pattern_matched = log_data.get('patternMatchedCount', 0)
                    position_filtered = log_data.get('positionFilteredCount', 0)
                    matched_count = log_data.get('matchedCount', 0)
                    viewport_width = log_data.get('viewportWidth', 0)
                    viewport_height = log_data.get('viewportHeight', 0)
                    scan_count = log_data.get('scanCount', 0)
                    self.add_log(f"<span style='color:#87CEEB;'>[调试]</span> {message} <span style='color:#888; font-size:11px;'>视口:{viewport_width}x{viewport_height} 扫描次数:{scan_count}</span>")
                    # 同时记录到文件
                    import json
                    _write_test_log(f"[左下角扫描统计] {message} 视口:{viewport_width}x{viewport_height} 扫描次数:{scan_count}")
                # 其他扫描统计不显示，减少冗余
            
            elif log_type == 'gift_scan_debug':
                # 显示左下角扫描调试信息（支持两种数据结构）
                message = log_data.get('message', '')
                # 方法1：DOM选择器扫描的数据结构
                checked = log_data.get('checked', 0)
                matched = log_data.get('matched', 0)
                gifts_found = log_data.get('giftsFound', 0)
                sample_text = log_data.get('sampleText', '')
                # 方法2：正则扫描的数据结构（兼容旧版本）
                found_count = log_data.get('foundCount', 0)
                pattern_matched = log_data.get('patternMatchedCount', 0)
                position_filtered = log_data.get('positionFilteredCount', 0)
                matched_count = log_data.get('matchedCount', 0)
                
                if checked > 0 or matched > 0 or gifts_found > 0:
                    # DOM选择器扫描结果
                    debug_msg = f"<span style='color:#FFA500;'>[DOM选择器扫描]</span> 检查:{checked} 匹配:{matched} 礼物数:{gifts_found}"
                    if sample_text:
                        debug_msg += f" <span style='color:#888; font-size:11px;'>示例文本:{sample_text[:80]}</span>"
                    self.add_log(debug_msg)
                    _write_test_log(f"[DOM选择器扫描] 检查:{checked} 匹配:{matched} 礼物数:{gifts_found} 示例文本:{sample_text[:100]}")
                elif found_count > 0 or pattern_matched > 0:
                    # 正则扫描结果（兼容旧版本）
                    self.add_log(f"<span style='color:#FFA500;'>[调试-左下角]</span> {message} 候选:{found_count} 位置匹配:{pattern_matched} 位置过滤:{position_filtered} 最终匹配:{matched_count}")
                    _write_test_log(f"[左下角扫描调试] {message} 候选:{found_count} 位置匹配:{pattern_matched} 位置过滤:{position_filtered} 最终匹配:{matched_count}")
                else:
                    # 通用显示
                    self.add_log(f"<span style='color:#FFA500;'>[调试]</span> {message}")
                    _write_test_log(f"[调试] {message}")
            
            elif log_type == 'gift_pattern_match':
                # 显示正则匹配成功的信息
                potential_user = log_data.get('potentialUser', '')
                potential_gift_name = log_data.get('potentialGiftName', '')
                text_preview = log_data.get('text', '')
                self.add_log(f"<span style='color:#90EE90;'>[正则匹配]</span> 用户:{potential_user} 礼物:{potential_gift_name} 文本:{text_preview[:80]}")
                _write_test_log(f"[正则匹配] 用户:{potential_user} 礼物:{potential_gift_name} 文本:{text_preview[:80]}")
            
            elif log_type == 'gift_validation_reason':
                # 显示验证失败的原因
                reason = log_data.get('reason', '')
                potential_user = log_data.get('potentialUser', '')
                potential_gift_name = log_data.get('potentialGiftName', '')
                text_preview = log_data.get('text', '')
                self.add_log(f"<span style='color:#FF6B6B;'>[验证失败]</span> {reason} 用户:{potential_user} 礼物:{potential_gift_name}")
                _write_test_log(f"[验证失败] {reason} 用户:{potential_user} 礼物:{potential_gift_name} 文本:{text_preview[:80]}")
            
            elif log_type == 'gift_pattern_failed':
                # 显示正则匹配失败的信息
                text_preview = log_data.get('text', '')
                has_send = log_data.get('hasSend', False)
                relaxed_match = log_data.get('relaxedMatch', '')
                simple_match = log_data.get('simpleMatch', '')
                if relaxed_match:
                    self.add_log(f"<span style='color:#90EE90;'>[正则失败但宽松匹配成功]</span> {relaxed_match}")
                    _write_test_log(f"[正则失败但宽松匹配成功] {relaxed_match}")
                elif simple_match:
                    self.add_log(f"<span style='color:#90EE90;'>[正则失败但简单匹配成功]</span> {simple_match}")
                    _write_test_log(f"[正则失败但简单匹配成功] {simple_match}")
                else:
                    self.add_log(f"<span style='color:#FFD700;'>[正则失败]</span> 包含'送':{has_send} 文本:{text_preview[:100]}")
                    _write_test_log(f"[正则失败] 包含'送':{has_send} 文本:{text_preview[:100]}")
            
            elif log_type == 'gift_text_debug':
                # 显示左下角文本调试信息
                text_preview = log_data.get('text', '')
                text_length = log_data.get('textLength', 0)
                has_send = log_data.get('hasSend', False)
                position = log_data.get('position', '')
                self.add_log(f"<span style='color:#87CEEB;'>[文本调试]</span> 长度:{text_length} 包含'送':{has_send} 位置:{position} <span style='color:#888; font-size:11px;'>文本: {text_preview[:80]}...</span>")
                _write_test_log(f"[文本调试] 长度:{text_length} 包含'送':{has_send} 位置:{position} 文本:{text_preview[:100]}")
            
            elif log_type == 'gift_candidate':
                unique_id = log_data.get('uniqueId', '')
                has_send_out = log_data.get('hasSendOut', False)
                has_send = log_data.get('hasSend', False)
                has_keyword = log_data.get('hasGiftKeyword', False)
                has_user_format = log_data.get('hasUserFormat', False)
                has_send_out_format = log_data.get('hasSendOutFormat', False)
                has_colon_format = log_data.get('hasColonFormat', False)
                has_send_format = log_data.get('hasSendFormat', False)
                has_multiple_gifts = log_data.get('hasMultipleGifts', False)
                gift_count = log_data.get('giftCount', 0)
                send_count = log_data.get('sendCount', 0)
                text_length = log_data.get('textLength', 0)
                is_gift = log_data.get('isGiftMessage', False)
                text_preview = log_data.get('textPreview', '')
                is_gift_list = log_data.get('isGiftList', False)
                is_realtime = log_data.get('isRealtimeInfo', False)
                
                # 简化日志：只在失败时显示详细信息
                if not is_gift:
                    format_details = []
                    if has_send_out_format:
                        format_details.append('送出了')
                    if has_colon_format:
                        format_details.append('冒号格式')
                    if has_send_format:
                        format_details.append('送格式')
                    format_str = '|'.join(format_details) if format_details else '无'
                    
                    self.add_log(f"<span style='color:#DDA0DD;'>[调试-候选]</span> ID:{unique_id[:20]}... 送:{has_send} 关键词:{has_keyword} 格式:{format_str} 多礼物:{has_multiple_gifts}({gift_count}/{send_count}) 长度:{text_length} 通过:{is_gift}<br><span style='color:#888; font-size:11px;'>文本: {text_preview[:60]}...</span>")
                    # 显示失败原因
                    reasons = []
                    if is_gift_list:
                        reasons.append('礼物列表')
                    if is_realtime:
                        reasons.append('实时信息')
                    if not has_user_format:
                        reasons.append('无用户格式')
                    if has_multiple_gifts:
                        reasons.append(f'多礼物({gift_count}/{send_count})')
                    if text_length >= 200:
                        reasons.append('文本过长')
                    if reasons:
                        self.add_log(f"<span style='color:#FFA500; font-size:10px;'>    └─ 失败原因: {', '.join(reasons)}</span>")
            
            elif log_type == 'gift_filtered':
                reason = log_data.get('reason', '')
                text_preview = log_data.get('textPreview', '')
                self.add_log(f"<span style='color:#FFA500;'>[调试-过滤]</span> 原因:{reason} <span style='color:#888; font-size:11px;'>文本: {text_preview[:60]}...</span>")
            
            elif log_type == 'gift_extract_failed':
                # 不再显示提取失败的日志，减少冗余
                # user = log_data.get('user', '')
                # gift_name = log_data.get('giftName', '')
                # text_preview = log_data.get('allText', '')
                # self.add_log(f"<span style='color:#FF6B6B;'>[调试-提取失败]</span> 用户:{user} 礼物名:{gift_name} <span style='color:#888; font-size:11px;'>文本: {text_preview[:80]}...</span>")
                pass
            
            elif log_type == 'gift_validation_failed':
                # 显示验证失败的信息（支持两种数据结构）
                message = log_data.get('message', '')
                user = log_data.get('user', '')
                gift_name = log_data.get('giftName', '')
                user_length = log_data.get('userLength', 0)
                gift_name_length = log_data.get('giftNameLength', 0)
                text_preview = log_data.get('text', '')
                
                if user or gift_name:
                    # DOM选择器扫描的验证失败
                    debug_msg = f"<span style='color:#FF6B6B;'>[验证失败]</span> 用户:{user} 礼物:{gift_name} 用户长度:{user_length} 礼物长度:{gift_name_length}"
                    if text_preview:
                        debug_msg += f" <span style='color:#888; font-size:11px;'>文本:{text_preview[:60]}</span>"
                    self.add_log(debug_msg)
                    _write_test_log(f"[验证失败] 用户:{user} 礼物:{gift_name} 用户长度:{user_length} 礼物长度:{gift_name_length} 文本:{text_preview[:100]}")
                else:
                    # 正则扫描的验证失败（兼容旧版本）
                    self.add_log(f"<span style='color:#FF6B6B;'>[验证失败]</span> {message}")
                    _write_test_log(f"[验证失败] {message}")
            
            elif log_type == 'gift_validation_failed_old':
                # 显示左下角验证失败的日志（用于调试）
                message = log_data.get('message', '')
                if '左下角礼物验证失败' in message:
                    gift_name = log_data.get('giftName', '')
                    user = log_data.get('user', '')
                    text = log_data.get('text', '')
                    self.add_log(f"<span style='color:#FF6B6B;'>[调试-验证失败]</span> 礼物名:{gift_name} 用户:{user} <span style='color:#888; font-size:11px;'>文本: {text[:80]}...</span>")
                # 其他验证失败不显示，减少冗余
            
            elif log_type == 'gift_pattern_failed':
                # 显示正则匹配失败的日志（用于调试）
                text = log_data.get('text', '')
                has_send = log_data.get('hasSend', False)
                length = log_data.get('length', 0)
                self.add_log(f"<span style='color:#FFA500;'>[调试-正则失败]</span> 包含送:{has_send} 长度:{length} <span style='color:#888; font-size:11px;'>文本: {text[:100]}...</span>")
            
            elif log_type == 'gift_check_failed':
                has_send_out = log_data.get('hasSendOut', False)
                has_send = log_data.get('hasSend', False)
                has_keyword = log_data.get('hasGiftKeyword', False)
                text_preview = log_data.get('textPreview', '')
                self.add_log(f"<span style='color:#FFA500;'>[调试-检查失败]</span> 送出了:{has_send_out} 送:{has_send} 关键词:{has_keyword} <span style='color:#888; font-size:11px;'>文本: {text_preview[:60]}...</span>")
            
            elif log_type == 'gift_name_missing':
                # 显示礼物名称缺失的详细调试信息
                user = log_data.get('user', '未知用户')
                all_text = log_data.get('allText', '')
                spans = log_data.get('spans', [])
                child_texts = log_data.get('childTexts', [])
                send_index = log_data.get('sendIndex', -1)
                send_text = log_data.get('sendText', '')
                gift_count = log_data.get('giftCount', '1')
                source_type = log_data.get('sourceType', '')
                between_user_and_send = log_data.get('betweenUserAndSend', '')
                between_send_and_count = log_data.get('betweenSendAndCount', '')
                after_send_text = log_data.get('afterSendText', '')
                before_count_text = log_data.get('beforeCountText', '')
                between_send_and_x = log_data.get('betweenSendAndX', '')
                
                import json
                _write_test_log(f"[礼物名称缺失] 用户:{user} 数量:{gift_count} 来源:{source_type}")
                _write_test_log(f"[礼物名称缺失] 完整文本: {all_text[:200]}")
                _write_test_log(f"[礼物名称缺失] spans数组: {json.dumps(spans[:10], ensure_ascii=False)}")
                _write_test_log(f"[礼物名称缺失] childTexts数组: {json.dumps(child_texts[:10], ensure_ascii=False)}")
                _write_test_log(f"[礼物名称缺失] sendIndex:{send_index} sendText:{send_text}")
                _write_test_log(f"[礼物名称缺失] 用户和送之间: '{between_user_and_send}'")
                _write_test_log(f"[礼物名称缺失] 送和数量之间: '{between_send_and_count}'")
                _write_test_log(f"[礼物名称缺失] 送出了之后: '{after_send_text}'")
                _write_test_log(f"[礼物名称缺失] 数量之前: '{before_count_text}'")
                _write_test_log(f"[礼物名称缺失] 送出了和×之间: '{between_send_and_x}'")
                
                # 在UI中显示简化版本
                self.add_log(f"<span style='color:#FF6B6B; font-weight:bold;'>[礼物名称缺失]</span> 用户:{user} 送出了×{gift_count} <span style='color:#888; font-size:11px;'>来源:{source_type}</span>")
                if between_send_and_x:
                    self.add_log(f"<span style='color:#FFA500; font-size:11px;'>    └─ 送出了和×之间: '{between_send_and_x}'</span>")
                if between_send_and_count:
                    self.add_log(f"<span style='color:#FFA500; font-size:11px;'>    └─ 送和数量之间: '{between_send_and_count}'</span>")
                if after_send_text:
                    self.add_log(f"<span style='color:#FFA500; font-size:11px;'>    └─ 送出了之后: '{after_send_text}'</span>")
            
            # 只显示和记录捕获到的礼物信息（粉色标记）- 只在礼物更新时输出
            elif log_type == 'gift_sorted_list':
                # 显示排序后的礼物列表（用于调试）
                total = log_data.get('total', 0)
                gifts = log_data.get('gifts', [])
                message = log_data.get('message', '')
                self.add_log(f"<span style='color:#FFD700; font-weight:bold;'>[排序后的礼物列表]</span> {message}")
                _write_test_log(f"[排序后的礼物列表] {message}")
                # 详细显示每个礼物
                if gifts:
                    for idx, gift in enumerate(gifts, 1):
                        gift_display = gift.get('display', f"{gift.get('user', '')} 送 {gift.get('giftName', '')}")
                        self.add_log(f"<span style='color:#90EE90; font-size:11px;'>  [{idx}] {gift_display}</span>")
                        _write_test_log(f"  [{idx}] {gift_display}")
            
            elif log_type == 'gift_captured':
                user = log_data.get('user', '未知用户')
                gift_name = log_data.get('giftName', '')
                gift_count = log_data.get('giftCount', '1')
                display_text = log_data.get('display_text', '')
                interval_since_last = log_data.get('intervalSinceLastGift', 0)
                avg_interval = log_data.get('avgInterval', 0)
                current_scan_interval = log_data.get('currentScanInterval', 500)
                meaningful_text = log_data.get('meaningfulText', '')
                data_index = log_data.get('dataIndex', '')
                
                # 如果有display_text，直接使用；否则自己格式化
                if display_text:
                    gift_display = display_text
                else:
                    gift_display = f"{user} 送出了 {gift_name}"
                    if gift_count != '1':
                        gift_display += f" × {gift_count}"
                
                # 显示间隔信息
                interval_info = ""
                if interval_since_last > 0:
                    interval_info = f"<span style='color:#87CEEB; font-size:10px;'>间隔: {interval_since_last}ms"
                    if avg_interval > 0:
                        interval_info += f" | 平均: {avg_interval}ms | 扫描: {current_scan_interval}ms"
                    interval_info += "</span>"
                
                log_line = f"<span style='color:#FF69B4; font-weight:bold;'>[礼物]</span> {display_text}"
                if interval_info:
                    log_line += f"<br>{interval_info}"
                if meaningful_text:
                    log_line += f"<br><span style='color:#DDA0DD; font-size:11px;'>文本: {meaningful_text}</span>"
                if data_index:
                    log_line += f"<br><span style='color:#DDA0DD; font-size:11px;'>ID: {data_index}</span>"
                
                self.add_log(log_line)
            # 其他调试日志（弹幕、在线人数等）不显示在UI中，也不写入文件
            return
        
        # 调试：记录所有非debug_log类型的数据（用于排查礼物数据丢失问题）
        if data_type != 'debug_log':
            import json
            _write_test_log(f"[调试-接收数据] type={data_type}, data={json.dumps(data, ensure_ascii=False)}")
        
        # 记录礼物、弹幕、实时信息到文件（简略输出，去重）
        import json
        import time
        
        current_time = time.time()
        
        if data_type == 'gift':
            # 验证礼物信息：必须包含用户ID和礼物类型
            gift_name = data.get('gift_name', '')
            user = data.get('user', '')
            
            # 过滤掉礼物名为None、空字符串或无效的情况
            if not gift_name or gift_name == 'None' or gift_name == 'null' or gift_name == 'undefined' or len(str(gift_name).strip()) == 0:
                # 不记录无效的礼物信息
                return
            
            # 只记录有效的礼物信息
            _write_test_log(f"[数据] {data_type}: {json.dumps(data, ensure_ascii=False)}")
        
        elif data_type == 'danmu':
            # 弹幕去重
            user = data.get('user', '')
            content = data.get('content', '')
            cache_key = f"{user}|{content}"
            
            last_time = self.danmu_cache.get(cache_key, 0)
            if current_time - last_time > self.cache_ttl:
                self.danmu_cache[cache_key] = current_time
                # 简略输出：只显示用户名和内容
                _write_test_log(f"[弹幕] {user}: {content}")
                
                # 清理过期缓存
                if len(self.danmu_cache) > 500:
                    expired_keys = [k for k, v in self.danmu_cache.items() if current_time - v > self.cache_ttl]
                    for k in expired_keys:
                        del self.danmu_cache[k]
        
        elif data_type == 'realtime_info':
            # 实时信息去重
            info_type = data.get('info_type', '')
            user = data.get('user', '')
            content = data.get('content', '')
            cache_key = f"{info_type}|{user}"
            
            last_time = self.realtime_cache.get(cache_key, 0)
            if current_time - last_time > self.cache_ttl:
                self.realtime_cache[cache_key] = current_time
                
                # 格式化输出
                if info_type == 'enter':
                    # 进入直播间：补齐"进入了直播间"
                    _write_test_log(f"[实时] {user} 进入了直播间")
                elif info_type == 'score':
                    # 为主播加分：只显示"为主播加了X分"，去掉多余信息
                    # 清理content中的多余信息（如"score"等）
                    clean_content = content.replace('score', '').replace('Score', '').strip()
                    if clean_content:
                        # 如果content包含分数，直接使用
                        if '分' in clean_content:
                            _write_test_log(f"[实时] {user} 为主播加了{clean_content}")
                        else:
                            _write_test_log(f"[实时] {user} 为主播加了{clean_content}分")
                    else:
                        _write_test_log(f"[实时] {user} 为主播加了分")
                elif info_type == 'like':
                    _write_test_log(f"[实时] {user} 为主播点赞了")
                elif info_type == 'share':
                    _write_test_log(f"[实时] {user} 分享了直播间")
                elif info_type == 'top':
                    _write_test_log(f"[实时] {user} 成为了观众TOP")
                else:
                    # 其他类型：显示类型和用户名
                    type_map = {
                        'enter': '进入',
                        'like': '点赞',
                        'share': '分享',
                        'top': 'TOP'
                    }
                    type_name = type_map.get(info_type, info_type)
                    _write_test_log(f"[实时] {user} {type_name}")
                
                # 清理过期缓存
                if len(self.realtime_cache) > 200:
                    expired_keys = [k for k, v in self.realtime_cache.items() if current_time - v > self.cache_ttl]
                    for k in expired_keys:
                        del self.realtime_cache[k]
        
        elif data_type == 'viewer_count':
            viewer_count = data.get('viewer_count', '')
            _write_test_log(f"[常驻信息] 在线人数: {viewer_count}")
        
        elif data_type == 'like_count':
            like_count = data.get('like_count', '')
            _write_test_log(f"[常驻信息] 本场点赞: {like_count}")
    
    def add_log(self, text):
        """添加日志到显示区域和文件"""
        t = datetime.now().strftime("%H:%M:%S")
        
        # 写入日志文件（去除HTML标签，只保留纯文本）
        import re
        text_plain = re.sub(r'<[^>]+>', '', text)  # 移除HTML标签
        _write_test_log(f"[{t}] {text_plain}")
        
        # 显示在UI中
        scrollbar = self.log_display.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 10
        
        current_html = self.log_display.toHtml()
        lines = current_html.split('<br>')
        
        # 找到头部结束位置
        header_end = 0
        for i, line in enumerate(lines):
            if '[提示]' in line:
                header_end = i + 1
                break
        
        header_lines = lines[:header_end]
        log_lines = lines[header_end:]
        
        new_log_line = f"<b>[{t}]</b> {text}"
        log_lines.append(new_log_line)
        
        new_html = '<br>'.join(header_lines + log_lines)
        self.log_display.setHtml(new_html)
        
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(scrollbar.value())
    
    def _clear_log(self):
        """清空日志"""
        log_file_info = f"日志文件: {self.log_file}"
        self.log_display.setHtml(
            f"<span style='color:#FFD700;'>【提示】</span> "
            f"<span style='color:#87CEEB;'>这是弹幕和礼物测试窗口，用于调试弹幕和礼物捕获功能。</span><br>"
            f"<span style='color:#87CEEB;'>所有捕获到的弹幕、礼物、在线人数等信息都会显示在下方。</span><br>"
            f"<span style='color:#98FB98;'>【日志文件】</span> <span style='color:#87CEEB;'>{log_file_info}</span><br><br>"
        )
        _write_test_log("[操作] 用户清空了日志显示")


def main():
    """主函数"""
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    QWebEngineProfile.defaultProfile().setHttpUserAgent(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    
    win = TestDanmuWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
