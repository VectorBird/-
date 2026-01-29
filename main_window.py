"""
主界面模块 - 整合所有功能模块
"""
import os
import sys
import time
from datetime import datetime

# 环境优化
os.environ["QT_GL_DEFAULT_BACKEND"] = "software"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--no-sandbox --disable-gpu --disable-software-rasterizer "
    "--ignore-gpu-blocklist --disable-background-timer-throttling "
    "--disable-logging --log-level=3"
)

from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QCheckBox,
                             QTextEdit, QSpinBox, QDoubleSpinBox)
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QGuiApplication, QTextCursor, QCloseEvent, QIcon
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtWebChannel import QWebChannel

# 导入自定义模块
from config_manager import load_cfg, save_cfg
from danmu_monitor import DanmuBridge, DanmuMonitor, global_signal
from danmu_gift_scraper import DanmuGiftScraper
from reply_handler import ReplyHandler
from warmup_handler import WarmupHandler
from message_sender import MessageSender
from command_handler import CommandHandler
from ui_managers import BaseRuleManager, WarmupManager
from global_message_queue import global_queue
from global_logger import global_logger


class LiveBrowser(QWidget):
    """主界面 - 整合所有功能模块（支持多小号模式）"""
    
    def __init__(self, cfg_ref, account_data=None, config_signal=None, log_callback=None, other_nicknames=None, close_callback=None):
        """
        初始化主界面
        
        Args:
            cfg_ref: 配置字典引用（所有小号共享的配置）
            account_data: 账户数据字典，包含name、nickname、url等（多小号模式时提供）
            config_signal: 配置更新信号对象（多小号模式时提供）
            log_callback: 日志回调函数（用于发送日志到控制面板）
            other_nicknames: 其他小号的昵称列表（用于过滤其他小号的弹幕）
            close_callback: 窗口关闭回调函数（用于通知控制面板窗口已关闭）
        """
        # 调试日志：记录窗口创建来源
        import traceback
        is_multi_account = account_data is not None
        account_name = account_data.get('name', 'N/A') if account_data else '单窗口模式'
        print(f"[窗口创建] 正在创建LiveBrowser窗口 | 模式: {'多小号' if is_multi_account else '单窗口'} | 账户: {account_name}")
        print(f"[窗口创建] 调用堆栈:")
        for line in traceback.format_stack()[-5:-1]:  # 只显示最近几层
            print(f"  {line.strip()}")
        sys.stdout.flush()
        
        try:
            # 不设置父对象，确保窗口独立（多小号模式下）
            super().__init__(None)  # 传入None确保没有父窗口
            # 设置窗口属性，确保关闭时不会影响其他窗口
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)  # 不自动删除
            self.cfg = cfg_ref
            self.account_data = account_data
            self.config_signal = config_signal
            self.log_callback = log_callback  # 日志回调函数（用于发送日志到控制面板）
            self.close_callback = close_callback  # 窗口关闭回调函数
            self.is_multi_account_mode = account_data is not None
            
            # 账户信息
            self.account_name = account_data.get('name', '') if account_data else ''
            self.account_nickname = account_data.get('nickname', '') if account_data else ''
            self.account_url = account_data.get('url', '') if account_data else ''
            
            # 其他小号的昵称列表（用于过滤弹幕，防止循环回复）
            self.other_nicknames = other_nicknames or []
            
            # 配置窗口引用
            self.reply_win = None
            self.spec_win = None
            self.warm_win = None
            
            # 弹幕时间跟踪（用于暖场判断）
            self.last_danmu_time = None  # 最后一次收到弹幕的时间，None表示还未收到弹幕
            self.stream_started = False  # 直播间是否已启动（URL已加载）
            self.reply_box_detected = False  # 回复框是否已检测到（用户是否已登录）
            
            # 初始化UI
            self._init_ui()
            
            # 初始化功能模块
            self._init_modules()
            
            # 初始化定时器
            self._init_timers()
            
            # 绑定信号
            self._connect_signals()
            
            # 初始化队列配置（如果是多小号模式）
            if self.is_multi_account_mode:
                global_queue.set_queue_mode(self.cfg.get('queue_mode', '轮询'))
                global_queue.set_time_window(self.cfg.get('queue_time_window', 5.0))
                global_queue.set_lock_timeout(self.cfg.get('queue_lock_timeout', 30.0))
                global_queue.set_strict_single_reply(self.cfg.get('strict_single_reply', True))
                global_queue.set_auto_cleanup(self.cfg.get('auto_cleanup_locks', True))
                account_priorities = self.cfg.get('account_priorities', {})
                for account_name, priority in account_priorities.items():
                    global_queue.set_account_priority(account_name, priority)
                # 注册账户到全局队列
                if self.account_name:
                    global_queue.register_account(self.account_name)
            
            # 更新视图
            self.update_view()
        except Exception as e:
            # 记录异常日志（此时self可能未完全初始化，使用print）
            import traceback
            account_info = f"账户={self.account_name}" if (hasattr(self, 'is_multi_account_mode') and self.is_multi_account_mode) else "主窗口"
            error_msg = f"[异常] 初始化LiveBrowser | 类型: {type(e).__name__} | 错误: {str(e)} | 上下文: {account_info}"
            print(error_msg)
            print(traceback.format_exc())
            sys.stdout.flush()
            raise
        
        # 如果有初始URL，自动加载
        if self.account_url:
            self.url_input.setText(self.account_url)
            # 多小号模式下，如果有初始URL，标记为已启动
            if self.is_multi_account_mode:
                self.stream_started = True
                self.stream_start_time = time.time()
            
    def closeEvent(self, event: QCloseEvent):
        """窗口关闭事件"""
        try:
            print(f"    [关闭窗口] 开始清理资源...")
            sys.stdout.flush()
            
            # 停止所有定时器
            if hasattr(self, 'auto_refresh_timer') and self.auto_refresh_timer:
                self.auto_refresh_timer.stop()
            if hasattr(self, 'danmu_timer') and self.danmu_timer:
                self.danmu_timer.stop()
            if hasattr(self, 'health_check_timer') and self.health_check_timer:
                self.health_check_timer.stop()
            if hasattr(self, 'refresh_timer') and self.refresh_timer:
                self.refresh_timer.stop()
            if hasattr(self, 'refresh_countdown_timer') and self.refresh_countdown_timer:
                self.refresh_countdown_timer.stop()
            
            # 注销账户（释放队列锁）- 在清理浏览器之前
            if self.is_multi_account_mode and self.account_name:
                try:
                    global_queue.unregister_account(self.account_name)
                except Exception as e:
                    self._log_exception("注销账户", e, context=f"账户名={self.account_name}")
            
            # 调用关闭回调（通知控制面板窗口已关闭，立即清理引用）- 在清理浏览器之前
            if self.close_callback:
                try:
                    self.close_callback()
                except Exception as e:
                    self._log_exception("执行关闭回调", e)
        
            # 清理浏览器资源（最后清理，避免影响其他操作）
            if hasattr(self, 'browser') and self.browser:
                try:
                    # 停止加载
                    self.browser.stop()
                    # 清理浏览器缓存和连接
                    try:
                        profile = self.browser.page().profile()
                        profile.clearHttpCache()
                        profile.clearAllVisitedLinks()
                    except:
                        pass
                    # 只断开父对象关系，不立即删除，让Qt自动管理
                    self.browser.setParent(None)
                    # 不调用deleteLater()，让窗口自然关闭时自动清理
                except Exception as e:
                    self._log_exception("清理浏览器资源", e)
            
            print(f"    [关闭窗口] 资源清理完成")
            sys.stdout.flush()
            
        except Exception as e:
            self._log_exception("关闭窗口清理资源", e)
        
        # 接受关闭事件，正常关闭窗口（不阻止关闭）
        event.accept()
        # 调用父类closeEvent，但确保不会影响主窗口
        super().closeEvent(event)
        
    def _init_ui(self):
        """初始化用户界面"""
        # 设置窗口标题
        title_suffix = " | 开发者: 故里何日还 | 仅供学习交流，禁止倒卖"
        if self.is_multi_account_mode:
            self.setWindowTitle(f"小号窗口: {self.account_name} ({self.account_nickname}){title_suffix}")
        else:
            self.setWindowTitle(f"抖音直播中控控场工具V3.0版本{title_suffix}")
        self.resize(1350, 950)
        
        # 设置窗口图标
        try:
            from path_utils import get_resource_path
            icon_path = get_resource_path("favicon.ico")
            if icon_path and os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except (ImportError, Exception):
            # 如果path_utils不可用或出错，使用旧逻辑（向后兼容）
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
        
        # 创建浏览器（多小号模式时使用独立的profile路径，确保cookie隔离）
        self.browser = QWebEngineView()
        
        # 获取会话目录路径（使用路径工具，支持打包环境）
        try:
            from path_utils import get_session_dir
            if self.is_multi_account_mode:
                session_path = get_session_dir(self.account_name)
            else:
                session_path = get_session_dir()
        except ImportError:
            # 如果path_utils不可用（向后兼容），使用当前工作目录
            if self.is_multi_account_mode:
                session_path = os.path.join(os.getcwd(), "douyin_sessions", self.account_name)
                os.makedirs(session_path, exist_ok=True)
            else:
                session_path = os.path.join(os.getcwd(), "douyin_session")
                os.makedirs(session_path, exist_ok=True)
        
        if self.is_multi_account_mode:
            # 为每个小号创建独立的profile，使用账户名确保唯一性
            profile_name = f"DouyinBot_{self.account_name}"
            # 创建独立的profile（指定parent为None，确保完全独立）
            self.profile = QWebEngineProfile(profile_name, None)
        else:
            profile_name = "DouyinBot"
            # 单窗口模式使用默认profile
            self.profile = QWebEngineProfile(profile_name, self)
        
        # 设置持久化存储路径（cookie、localStorage等都会存储在这里）
        self.profile.setPersistentStoragePath(session_path)
        # 设置缓存路径（也是独立的）
        cache_path = os.path.join(session_path, "cache")
        os.makedirs(cache_path, exist_ok=True)
        self.profile.setCachePath(cache_path)
        
        # 创建独立的页面实例
        page = QWebEnginePage(self.profile, self.browser)
        self.browser.setPage(page)
        
        # 创建WebChannel桥接
        self.bridge = DanmuBridge()
        self.channel = QWebChannel()
        self.channel.registerObject("pyBridge", self.bridge)
        self.browser.page().setWebChannel(self.channel)
        
        # 调试日志：确认 QWebChannel 已设置
        print(f"[初始化] QWebChannel 已设置，pyBridge 已注册")
        sys.stdout.flush()
        
        # 主布局
        layout = QVBoxLayout(self)
        
        # 导航栏
        nav = QHBoxLayout()
        
        # URL输入
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴直播间地址...")
        self.btn_go = QPushButton("🚀 启动")
        self.btn_go.setFixedWidth(60)
        self.btn_go.setStyleSheet("background:#FE2C55; color:white; font-weight:bold;")
        nav.addWidget(self.url_input)
        nav.addWidget(self.btn_go)
        
        # 多小号模式：只显示账户信息，配置由主控制面板管理
        if self.is_multi_account_mode:
            nav.addWidget(QLabel(f"账户: {self.account_name} | 昵称: {self.account_nickname}"))
            nav.addStretch()
            # 添加刷新倒计时标签
            self.refresh_countdown_label = QLabel("距离下次自动刷新: 60:00")
            self.refresh_countdown_label.setStyleSheet("color:#98FB98; font-weight:bold; padding:0 10px;")
            nav.addWidget(self.refresh_countdown_label)
            self.cb_hide = QCheckBox("🙈隐藏")
            self.cb_hide.setChecked(self.cfg['hide_web'])
            self.cb_hide.stateChanged.connect(self._update_hide_view)
            nav.addWidget(self.cb_hide)
        else:
            # 单窗口模式：显示所有配置控件
            nav.addWidget(QLabel("我昵称:"))
            self.edit_me = QLineEdit()
            self.edit_me.setText(self.cfg['my_nickname'])
            self.edit_me.setFixedWidth(100)
            nav.addWidget(self.edit_me)
            
            nav.addWidget(QLabel("回复间隔:"))
            self.sp_step = QSpinBox()
            self.sp_step.setRange(2, 30)
            self.sp_step.setValue(self.cfg['reply_interval'])
            nav.addWidget(self.sp_step)
            
            nav.addWidget(QLabel("随机抖动:"))
            self.sp_jitter = QDoubleSpinBox()
            self.sp_jitter.setRange(0, 10)
            self.sp_jitter.setValue(self.cfg['random_jitter'])
            nav.addWidget(self.sp_jitter)
            
            # 功能开关
            self.cb_reply = QCheckBox("回复")
            self.cb_reply.setChecked(self.cfg['auto_reply_enabled'])
            nav.addWidget(self.cb_reply)
            
            self.cb_spec = QCheckBox("特定")
            self.cb_spec.setChecked(self.cfg['specific_reply_enabled'])
            nav.addWidget(self.cb_spec)
            
            self.cb_warm = QCheckBox("暖场")
            self.cb_warm.setChecked(self.cfg['warmup_enabled'])
            nav.addWidget(self.cb_warm)
            
            # 配置按钮
            btn_r_cfg = QPushButton("📝 关键词")
            btn_r_cfg.clicked.connect(lambda: self.open_sub_win('reply'))
            nav.addWidget(btn_r_cfg)
            
            btn_s_cfg = QPushButton("🎯 特定")
            btn_s_cfg.clicked.connect(lambda: self.open_sub_win('spec'))
            nav.addWidget(btn_s_cfg)
            
            btn_w_cfg = QPushButton("📢 暖场")
            btn_w_cfg.clicked.connect(lambda: self.open_sub_win('warm'))
            nav.addWidget(btn_w_cfg)
            
            self.cb_hide = QCheckBox("🙈隐藏")
            self.cb_hide.setChecked(self.cfg['hide_web'])
            nav.addWidget(self.cb_hide)
        
        layout.addLayout(nav)
        
        # 日志显示
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet(
            "background:#000000; color:#00FF41; font-family:'Microsoft YaHei UI'; font-size:14px;"
        )
        
        # 多小号模式：在日志窗口添加暖场说明和刷新倒计时
        if self.is_multi_account_mode:
            self._update_log_header()
        
        layout.addWidget(self.browser, stretch=3)
        layout.addWidget(self.log_display, stretch=1)
        
    def _init_modules(self):
        """初始化功能模块"""
        # 弹幕和礼物捕获模块（DOM scraping方式）
        instance_id = self.account_name if self.is_multi_account_mode else "default"
        self.danmu_gift_scraper = DanmuGiftScraper(instance_id=instance_id)
        
        # 弹幕监控模块（使用账户昵称）
        nickname = self.account_nickname if self.is_multi_account_mode else self.cfg['my_nickname']
        self.danmu_monitor = DanmuMonitor(nickname)
        # 设置其他小号的昵称列表（用于过滤其他小号的弹幕，防止循环回复）
        if self.is_multi_account_mode and self.other_nicknames:
            self.danmu_monitor.set_other_account_nicknames(self.other_nicknames)
        self.danmu_monitor.set_callback(self._on_danmu_received)
        
        
        # 准备配置（如果是多小号模式且有账户独立配置，使用账户配置，否则使用全局配置）
        # 单窗口模式直接使用self.cfg引用（支持热更新），多小号模式使用合并后的配置
        if self.is_multi_account_mode and self.account_data:
            # 多小号模式：创建合并配置（账户特定配置优先，但warmup_rules需要合并）
            account_cfg = self.cfg.copy()
            
            # 调试日志：记录配置合并过程
            try:
                from reply_handler import _write_debug_log
                global_reply_rules_count = len(self.cfg.get('reply_rules', [])) if isinstance(self.cfg.get('reply_rules', []), list) else 0
                account_reply_rules = self.account_data.get('reply_rules', None)
                account_reply_rules_count = len(account_reply_rules) if isinstance(account_reply_rules, list) else 0
                _write_debug_log(f"[配置合并] 账户: {self.account_name}, "
                               f"全局规则数={global_reply_rules_count}, "
                               f"账户规则存在={'reply_rules' in self.account_data}, "
                               f"账户规则数={account_reply_rules_count}")
            except:
                pass
            
            # 只有当账户数据中有reply_rules键且不为空列表时，才使用账户配置
            # 如果账户数据中没有reply_rules键，或reply_rules为空列表，使用全局配置
            if 'reply_rules' in self.account_data:
                account_reply_rules = self.account_data.get('reply_rules', [])
                if isinstance(account_reply_rules, list) and len(account_reply_rules) > 0:
                    account_cfg['reply_rules'] = account_reply_rules
                    try:
                        from reply_handler import _write_debug_log
                        _write_debug_log(f"[配置合并] 使用账户特定规则，规则数={len(account_reply_rules)}")
                    except:
                        pass
                # 如果账户规则为空列表，使用全局配置（已在copy中，不需要修改）
                else:
                    try:
                        from reply_handler import _write_debug_log
                        _write_debug_log(f"[配置合并] 账户规则为空，使用全局规则")
                    except:
                        pass
            # 如果账户数据中没有reply_rules键，使用全局配置（已在copy中，不需要修改）
            
            if 'specific_rules' in self.account_data:
                account_specific_rules = self.account_data.get('specific_rules', [])
                if isinstance(account_specific_rules, list) and len(account_specific_rules) > 0:
                    account_cfg['specific_rules'] = account_specific_rules
            # 如果没有账户特定规则，使用全局规则（已在copy中）
            
            if 'warmup_msgs' in self.account_data:
                account_cfg['warmup_msgs'] = self.account_data.get('warmup_msgs', '')
            # warmup_rules：如果有账户特定规则，合并全局规则和账户规则（账户规则在前）
            if 'warmup_rules' in self.account_data:
                account_warmup_rules = self.account_data.get('warmup_rules', [])
                global_warmup_rules = self.cfg.get('warmup_rules', [])
                # 合并规则：账户规则在前，全局规则在后（这样账户规则优先级更高）
                account_cfg['warmup_rules'] = account_warmup_rules + global_warmup_rules
            # 如果没有账户特定规则，使用全局规则（已在copy中）
            
            # advanced_reply_rules：如果有账户特定规则，合并全局规则和账户规则（账户规则在前）
            if 'advanced_reply_rules' in self.account_data:
                account_advanced_rules = self.account_data.get('advanced_reply_rules', [])
                global_advanced_rules = self.cfg.get('advanced_reply_rules', [])
                # 合并规则：账户规则在前，全局规则在后（这样账户规则优先级更高）
                account_cfg['advanced_reply_rules'] = account_advanced_rules + global_advanced_rules
            # 如果没有账户特定规则，使用全局规则（已在copy中）
        else:
            # 单窗口模式：直接使用self.cfg引用（支持热更新）
            account_cfg = self.cfg
        
        # 回复处理模块（使用账户配置或全局配置）
        account_name = self.account_name if self.is_multi_account_mode else None
        self.reply_handler = ReplyHandler(account_cfg, self._log_message, account_name)
        self.reply_handler.set_enabled(
            account_cfg.get('auto_reply_enabled', False),
            account_cfg.get('specific_reply_enabled', False),
            account_cfg.get('advanced_reply_enabled', False)
        )
        
        # 暖场处理模块（使用账户配置或全局配置，单窗口模式使用cfg引用支持热更新）
        warmup_cfg = self.cfg if not self.is_multi_account_mode else account_cfg
        self.warmup_handler = WarmupHandler(warmup_cfg, self._log_message)
        self.warmup_handler.set_enabled(account_cfg.get('warmup_enabled', False))
        
        # 指令处理器（使用全局配置）
        self.command_handler = CommandHandler(self.cfg, self._log_message)
        self.command_handler.set_enabled(self.cfg.get('command_enabled', False))
        self.command_handler.set_command_user(self.cfg.get('command_user', ''))
        self.command_handler.set_silent_mode(self.cfg.get('command_silent_mode', False))
        
        # 消息发送模块（共享配置）
        account_name_for_sender = self.account_name if self.is_multi_account_mode else "default"
        self.message_sender = MessageSender(self.browser.page(), self._log_message, account_name_for_sender)
        self.message_sender.set_intervals(
            self.cfg['reply_interval'],
            self.cfg['random_jitter']
        )
        # 设置随机空格插入功能
        self.message_sender.set_random_space_insert(
            self.cfg.get('random_space_insert_enabled', False)
        )
        
    def _init_timers(self):
        """初始化定时器"""
        # 主循环定时器 - 处理消息队列和暖场
        self.main_timer = QTimer()
        self.main_timer.timeout.connect(self._on_main_loop)
        self.main_timer.start(1000)  # 1秒执行一次
        
        # JavaScript注入定时器
        self.inject_timer = QTimer()
        self.inject_timer.timeout.connect(self._inject_js)
        self.inject_timer.start(3000)  # 3秒执行一次
        
        # 多小号模式：定期检查页面健康状态和自动刷新
        if self.is_multi_account_mode:
            # 页面健康检查定时器（每5分钟检查一次）
            self.health_check_timer = QTimer()
            self.health_check_timer.timeout.connect(self._check_page_health)
            self.health_check_timer.start(5 * 60 * 1000)  # 5分钟检查一次
            
            # 自动刷新定时器（每2小时刷新一次，减少刷新频率避免掉登录）
            self.refresh_timer = QTimer()
            self.refresh_timer.timeout.connect(self._auto_refresh_browser)
            self.refresh_timer.start(2 * 3600000)  # 2小时刷新一次（原来1小时）
            self.last_refresh_time = time.time()  # 记录上次刷新时间
            
            # 刷新倒计时显示定时器（每秒更新一次，更新窗口顶部标签）
            self.refresh_countdown_timer = QTimer()
            self.refresh_countdown_timer.timeout.connect(self._update_refresh_countdown)
            self.refresh_countdown_timer.start(1000)  # 1秒执行一次
            self._update_refresh_countdown()  # 立即更新一次
            
            # 初始化健康检查相关变量
            self.last_reply_box_check = time.time()
            self.consecutive_login_failures = 0  # 连续登录失败次数
        
    def _connect_signals(self):
        """连接信号和槽"""
        # 连接全局信号
        global_signal.received.connect(self._on_danmu_signal)
        # 多小号模式下不使用global_signal.log_msg，避免日志重复输出（日志通过log_callback直接发送到控制面板）
        # 单窗口模式才连接log_msg信号
        if not self.is_multi_account_mode:
            global_signal.log_msg.connect(self.add_log)
        
        # 连接按钮
        self.btn_go.clicked.connect(self.load_url)
        
        # 多小号模式：连接配置更新信号
        if self.is_multi_account_mode and self.config_signal:
            self.config_signal.config_updated.connect(self._on_config_updated)
        
        # 单窗口模式：连接配置控件变化
        if not self.is_multi_account_mode:
            for widget in [self.cb_reply, self.cb_spec, self.cb_warm, self.cb_hide,
                           self.edit_me, self.sp_step, self.sp_jitter]:
                if isinstance(widget, QCheckBox):
                    widget.stateChanged.connect(self.update_cfg)
                elif isinstance(widget, QLineEdit):
                    widget.textChanged.connect(self.update_cfg)
                else:
                    widget.valueChanged.connect(self.update_cfg)
                
    def _on_danmu_signal(self, data):
        """接收弹幕信号"""
        # 调试日志：记录接收到的原始数据
        try:
            print(f"[弹幕信号] 类型: {data.get('type', 'unknown')}, 数据: {data}")
            sys.stdout.flush()
        except:
            pass
        
        # 更新监控器昵称
        if self.is_multi_account_mode:
            self.danmu_monitor.set_nickname(self.account_nickname)
        else:
            self.danmu_monitor.set_nickname(self.edit_me.text().strip())
        # 处理弹幕
        self.danmu_monitor.process_danmu(data)
        
    def _on_danmu_received(self, data):
        """数据回调处理（弹幕、礼物、在线人数等）"""
        data_type = data.get('type', 'danmu')
        
        # 检测回复框状态
        if data_type == 'reply_box_detected':
            detected = data.get('detected', False)
            # 如果状态发生变化，记录日志
            if self.reply_box_detected != detected:
                if detected:
                    self._log_message(f"<span style='color:#00FF00;'>[登录状态]</span> ✓ 已检测到回复框，登录状态正常")
                    self.consecutive_login_failures = 0  # 重置失败计数
                else:
                    self._log_message(f"<span style='color:#FFA500;'>[登录状态]</span> ⚠ 回复框未检测到，可能已掉登录")
            self.reply_box_detected = detected
            self.last_reply_box_check = time.time()  # 更新最后检查时间
            return
        
        if data_type == 'danmu':
            # 处理弹幕
            user = data.get('user', '')
            content = data.get('content', '')
            
            # 单独输出弹幕日志（方便调试）
            try:
                print(f"[弹幕日志] 用户: {user}, 内容: {content}")
                sys.stdout.flush()
            except:
                pass
            
            # 更新最后一次弹幕时间（用于暖场判断）
            self.last_danmu_time = time.time()
            
            # 记录捕获日志
            self._log_message(f"<span style='color:white;'>[弹幕]</span> {user}: {content}")
            
            # 先检查是否是指令（优先级最高）
            if hasattr(self, 'command_handler'):
                is_command, result_msg, actions, need_confirm = self.command_handler.process_command(user, content)
                if is_command:
                    # 记录指令执行日志
                    self._log_message(f"<span style='color:#FFD700;'>[指令]</span> {user}: {content}")
                    
                    # 如果需要确认，只发送确认消息，不执行操作
                    if need_confirm:
                        if result_msg and not self.command_handler.silent_mode:
                            self.message_sender.add_message([result_msg])
                        return
                    
                    # 执行指令操作
                    for action_type, action_data in actions:
                        if action_type == 'stop_auto_reply':
                            # 停止自动回复和暖场
                            self.cfg['auto_reply_enabled'] = False
                            self.cfg['specific_reply_enabled'] = False
                            self.cfg['advanced_reply_enabled'] = False
                            self.cfg['warmup_enabled'] = False
                            self.reply_handler.set_enabled(False, False, False)
                            if hasattr(self, 'warmup_handler'):
                                self.warmup_handler.set_enabled(False)
                            # 保存配置到文件
                            from config_manager import save_cfg
                            save_cfg(self.cfg)
                            # 通知控制面板更新UI状态
                            if self.is_multi_account_mode and self.config_signal:
                                self.config_signal.config_updated.emit(self.cfg.copy())
                            # 单窗口模式：更新UI
                            elif not self.is_multi_account_mode:
                                self.update_cfg()
                            self._log_message(f"<span style='color:#FF6B6B;'>[指令执行]</span> 已停止自动回复和暖场功能")
                        
                        elif action_type == 'start_auto_reply':
                            # 启动自动回复和暖场
                            self.cfg['auto_reply_enabled'] = True
                            self.cfg['specific_reply_enabled'] = self.cfg.get('specific_reply_enabled', False)
                            self.cfg['advanced_reply_enabled'] = self.cfg.get('advanced_reply_enabled', False)
                            self.cfg['warmup_enabled'] = self.cfg.get('warmup_enabled', False)
                            self.reply_handler.set_enabled(
                                True, 
                                self.cfg.get('specific_reply_enabled', False),
                                self.cfg.get('advanced_reply_enabled', False)
                            )
                            if hasattr(self, 'warmup_handler'):
                                self.warmup_handler.set_enabled(self.cfg.get('warmup_enabled', False))
                            # 保存配置到文件
                            from config_manager import save_cfg
                            save_cfg(self.cfg)
                            # 通知控制面板更新UI状态
                            if self.is_multi_account_mode and self.config_signal:
                                self.config_signal.config_updated.emit(self.cfg.copy())
                            # 单窗口模式：更新UI
                            elif not self.is_multi_account_mode:
                                self.update_cfg()
                            self._log_message(f"<span style='color:#00FF00;'>[指令执行]</span> 已启动自动回复和暖场功能")
                        
                        elif action_type == 'enable_specific_reply':
                            # 启用@回复
                            self.cfg['specific_reply_enabled'] = True
                            self.reply_handler.set_enabled(
                                self.cfg.get('auto_reply_enabled', False),
                                True,
                                self.cfg.get('advanced_reply_enabled', False)
                            )
                            # 保存配置到文件
                            from config_manager import save_cfg
                            save_cfg(self.cfg)
                            # 通知控制面板更新UI状态
                            if self.is_multi_account_mode and self.config_signal:
                                self.config_signal.config_updated.emit(self.cfg.copy())
                            # 单窗口模式：更新UI
                            elif not self.is_multi_account_mode:
                                self.update_cfg()
                            self._log_message(f"<span style='color:#00FF00;'>[指令执行]</span> 已启用@回复功能")
                        
                        elif action_type == 'disable_specific_reply':
                            # 禁用@回复
                            self.cfg['specific_reply_enabled'] = False
                            self.reply_handler.set_enabled(
                                self.cfg.get('auto_reply_enabled', False),
                                False,
                                self.cfg.get('advanced_reply_enabled', False)
                            )
                            # 保存配置到文件
                            from config_manager import save_cfg
                            save_cfg(self.cfg)
                            # 通知控制面板更新UI状态
                            if self.is_multi_account_mode and self.config_signal:
                                self.config_signal.config_updated.emit(self.cfg.copy())
                            # 单窗口模式：更新UI
                            elif not self.is_multi_account_mode:
                                self.update_cfg()
                            self._log_message(f"<span style='color:#FF6B6B;'>[指令执行]</span> 已禁用@回复功能")
                        
                        elif action_type == 'enable_warmup':
                            # 启用暖场
                            self.cfg['warmup_enabled'] = True
                            if hasattr(self, 'warmup_handler'):
                                self.warmup_handler.set_enabled(True)
                            # 保存配置到文件
                            from config_manager import save_cfg
                            save_cfg(self.cfg)
                            # 通知控制面板更新UI状态
                            if self.is_multi_account_mode and self.config_signal:
                                self.config_signal.config_updated.emit(self.cfg.copy())
                            # 单窗口模式：更新UI
                            elif not self.is_multi_account_mode:
                                self.update_cfg()
                            self._log_message(f"<span style='color:#00FF00;'>[指令执行]</span> 已启用暖场功能")
                        
                        elif action_type == 'disable_warmup':
                            # 禁用暖场
                            self.cfg['warmup_enabled'] = False
                            if hasattr(self, 'warmup_handler'):
                                self.warmup_handler.set_enabled(False)
                            # 保存配置到文件
                            from config_manager import save_cfg
                            save_cfg(self.cfg)
                            # 通知控制面板更新UI状态
                            if self.is_multi_account_mode and self.config_signal:
                                self.config_signal.config_updated.emit(self.cfg.copy())
                            # 单窗口模式：更新UI
                            elif not self.is_multi_account_mode:
                                self.update_cfg()
                            self._log_message(f"<span style='color:#FF6B6B;'>[指令执行]</span> 已禁用暖场功能")
                        
                        elif action_type == 'set_reply_interval':
                            # 设置回复间隔
                            interval = action_data.get('interval', 4)
                            if 1 <= interval <= 30:
                                self.cfg['reply_interval'] = interval
                                if hasattr(self, 'message_sender'):
                                    self.message_sender.set_intervals(
                                        interval,
                                        self.cfg.get('random_jitter', 2.0)
                                    )
                                self._log_message(f"<span style='color:#87CEEB;'>[指令执行]</span> 已设置回复间隔为 {interval} 秒")
                            else:
                                self._log_message(f"<span style='color:#FF6B6B;'>[指令执行]</span> 间隔时间无效（1-30秒）")
                        
                        elif action_type == 'clear_queue':
                            # 清空队列
                            if hasattr(self, 'message_sender'):
                                self.message_sender.clear_queue()
                            self._log_message(f"<span style='color:#87CEEB;'>[指令执行]</span> 已清空消息队列")
                        
                        elif action_type == 'reset_statistics':
                            # 重置统计（已确认）
                            from statistics_manager import statistics_manager
                            statistics_manager.reset_statistics()
                            self._log_message(f"<span style='color:#FF6B6B;'>[指令执行]</span> 已重置统计数据")
                        
                        elif action_type == 'reload_rules':
                            # 重新加载规则（从文件重新加载配置，确保规则立即生效）
                            from config_manager import load_cfg
                            # 重新加载配置文件
                            new_cfg = load_cfg()
                            # 更新self.cfg中的规则相关字段
                            self.cfg['reply_rules'] = new_cfg.get('reply_rules', [])
                            self.cfg['specific_rules'] = new_cfg.get('specific_rules', [])
                            self.cfg['advanced_reply_rules'] = new_cfg.get('advanced_reply_rules', [])
                            
                            # 重新创建reply_handler，确保规则立即生效
                            if self.is_multi_account_mode:
                                # 多账户模式：需要重新加载账户配置并合并
                                from account_manager import get_account
                                account_data = get_account(self.account_name)
                                if account_data:
                                    # 创建账户配置副本
                                    account_cfg = self.cfg.copy()
                                    # 合并账户特定规则（如果存在）
                                    if 'reply_rules' in account_data:
                                        account_reply_rules = account_data.get('reply_rules', [])
                                        if isinstance(account_reply_rules, list) and len(account_reply_rules) > 0:
                                            account_cfg['reply_rules'] = account_reply_rules
                                    if 'specific_rules' in account_data:
                                        account_specific_rules = account_data.get('specific_rules', [])
                                        if isinstance(account_specific_rules, list) and len(account_specific_rules) > 0:
                                            account_cfg['specific_rules'] = account_specific_rules
                                    if 'advanced_reply_rules' in account_data:
                                        account_advanced_rules = account_data.get('advanced_reply_rules', [])
                                        global_advanced_rules = self.cfg.get('advanced_reply_rules', [])
                                        account_cfg['advanced_reply_rules'] = account_advanced_rules + global_advanced_rules
                                    
                                    # 重新创建reply_handler
                                    from reply_handler import ReplyHandler
                                    self.reply_handler = ReplyHandler(account_cfg, self._log_message, self.account_name)
                                    self.reply_handler.set_enabled(
                                        account_cfg.get('auto_reply_enabled', False),
                                        account_cfg.get('specific_reply_enabled', False),
                                        account_cfg.get('advanced_reply_enabled', False)
                                    )
                            else:
                                # 单窗口模式：直接使用self.cfg
                                from reply_handler import ReplyHandler
                                self.reply_handler = ReplyHandler(self.cfg, self._log_message, None)
                                self.reply_handler.set_enabled(
                                    self.cfg.get('auto_reply_enabled', False),
                                    self.cfg.get('specific_reply_enabled', False),
                                    self.cfg.get('advanced_reply_enabled', False)
                                )
                            
                            rule_count = len(self.cfg.get('reply_rules', []))
                            spec_count = len(self.cfg.get('specific_rules', []))
                            advanced_count = len(self.cfg.get('advanced_reply_rules', []))
                            self._log_message(f"<span style='color:#87CEEB;'>[指令执行]</span> 已重新加载规则（关键词:{rule_count}，@回复:{spec_count}，高级:{advanced_count}）")
                    
                    # 如果有结果消息且不是静默模式，发送回复
                    if result_msg and not self.command_handler.silent_mode:
                        self.message_sender.add_message([result_msg])
                    
                    # 指令已处理，不再进行普通回复处理
                    return
            
            # 使用回复处理模块处理弹幕（非指令）
            messages = self.reply_handler.process_danmu(user, content)
            if messages:
                # 添加到消息队列
                self.message_sender.add_message(messages)
                
        elif data_type == 'system_message':
            # 处理系统消息（进入、点赞、TOP等）
            sub_type = data.get('sub_type', 'unknown')
            user = data.get('user', '')
            action = data.get('action', '')
            content = data.get('content', '')
            
            # 根据类型设置颜色和图标
            type_map = {
                'user_entered': ('#98FB98', '🚪', '进入'),
                'user_liked': ('#FF69B4', '👍', '点赞'),
                'user_top': ('#FFD700', '⭐', 'TOP'),
                'user_followed': ('#00FF00', '➕', '关注'),
                'user_shared': ('#87CEEB', '📤', '分享'),
            }
            color, icon, label = type_map.get(sub_type, ('#888', 'ℹ️', '系统'))
            self._log_message(f"<span style='color:{color};'>[{icon} 系统消息-{label}]</span> {user} {content}")
                
        elif data_type == 'gift':
            # 处理礼物
            user = data.get('user', '')
            gift_name = data.get('gift_name', '')
            gift_count = data.get('gift_count', '1')
            source = data.get('source', 'danmu')  # 来源：danmu 或 left_bottom_user_list
            
            # 单独输出礼物日志（方便调试）
            try:
                print(f"[礼物日志] 用户: {user}, 礼物: {gift_name}, 数量: {gift_count}, 来源: {source}")
                sys.stdout.flush()
            except:
                pass
            
            # 如果用户名为"未知"且来自左下角，输出调试信息到Python控制台
            if user == '未知' and source == 'left_bottom_user_list':
                debug_text = data.get('debug_text', '')
                debug_html = data.get('debug_html', '')
                if debug_text or debug_html:
                    print(f"[礼物捕获-调试] 用户名为'未知'，礼物: {gift_name}, 数量: {gift_count}")
                    if debug_text:
                        print(f"[礼物捕获-调试] 原始文本: {debug_text}")
                    if debug_html:
                        print(f"[礼物捕获-调试] 元素HTML: {debug_html}")
                    sys.stdout.flush()
            
            # 根据来源设置显示样式
            if source == 'left_bottom_user_list':
                # 左下角捕获的完整礼物信息（绿色高亮）
                if gift_count == '1':
                    self._log_message(f"<span style='color:#00FF00;'>[礼物-左下角]</span> <span style='color:#FFD700;'>{user}</span> 送出了 {gift_name}")
                else:
                    self._log_message(f"<span style='color:#00FF00;'>[礼物-左下角]</span> <span style='color:#FFD700;'>{user}</span> 送出了 {gift_count}个 {gift_name}")
            else:
                # 弹幕区捕获的礼物信息（黄色）
                if gift_count == '1':
                    self._log_message(f"<span style='color:#FFD700;'>[礼物]</span> {user} 送出了 {gift_name}")
                else:
                    self._log_message(f"<span style='color:#FFD700;'>[礼物]</span> {user} 送出了 {gift_count}个 {gift_name}")
            
        elif data_type == 'realtime_info':
            # 处理实时信息（进入、点赞、分享、TOP、加分等）
            info_type = data.get('info_type', 'other')
            user = data.get('user', '')
            content = data.get('content', '')
            
            # 根据类型设置颜色和图标
            type_map = {
                'enter': ('#98FB98', '🚪', '进入'),
                'like': ('#FF69B4', '👍', '点赞'),
                'share': ('#87CEEB', '📤', '分享'),
                'top': ('#FFD700', '⭐', 'TOP'),
                'score': ('#00FF00', '⭐', '加分'),
                'other': ('#888', 'ℹ️', '实时'),
            }
            color, icon, label = type_map.get(info_type, ('#888', 'ℹ️', '实时'))
            
            # 格式化显示内容
            if content:
                display_text = f"{user} {content}"
            else:
                display_text = f"{user} {label}"
            
            self._log_message(f"<span style='color:{color};'>[{icon} {label}]</span> {display_text}")
            
        elif data_type == 'viewer_count':
            # 处理在线人数（静默传输，不在小号日志中显示，只传给全局日志）
            viewer_count = data.get('viewer_count', '')
            # 通过log_callback静默传输（如果存在），不调用_log_message
            if self.log_callback:
                self.log_callback(f"<span style='color:#87CEEB;'>[在线人数]</span> {viewer_count}")
            
        elif data_type == 'enter':
            # 处理进入直播间
            user = data.get('user', '')
            self._log_message(f"<span style='color:#98FB98;'>[进入]</span> {user} 进入了直播间")
            
        else:
            # 其他类型的数据
            self._log_message(f"<span style='color:gray;'>[信息]</span> {data}")
            
    def _on_main_loop(self):
        """主循环 - 处理消息队列和暖场"""
        # 处理消息队列
        sent_message = self.message_sender.process_queue()
        
        # 如果发送了消息，记录到回复处理器（防止循环回复）
        if sent_message:
            self.reply_handler.record_sent_message(sent_message)
        
        # 检查暖场（必须捕获到首条弹幕后才开始运作，且回复框已检测到）
        warmup_msg = None
        if self.stream_started and self.last_danmu_time is not None and self.reply_box_detected:
            # 只有在直播间已启动、已收到至少一条弹幕、且回复框已检测到后，才允许触发暖场
            # 与普通回复和特定回复一致，都需要检测到回复框（用户已登录）后才生效
            warmup_msg = self.warmup_handler.should_warmup(
                has_pending_messages=self.message_sender.has_pending(),
                last_danmu_time=self.last_danmu_time
            )
        
        if warmup_msg:
            # warmup_msg可能是字符串（旧版本）或列表（新版本）
            self.message_sender.add_message(warmup_msg)
    
            
    def _log_exception(self, operation, exception, context=None):
        """
        记录异常日志（统一格式）
        
        Args:
            operation: 操作名称（如"初始化LiveBrowser"、"处理弹幕"等）
            exception: 异常对象
            context: 额外的上下文信息（可选）
        """
        import traceback
        error_type = type(exception).__name__
        error_msg = str(exception)
        traceback_str = traceback.format_exc()
        
        # 构建日志消息
        log_msg = f"<span style='color:#FF6B6B;'>[异常] {operation}</span> "
        log_msg += f"<span style='color:#FFA500;'>类型: {error_type}</span> "
        log_msg += f"<span style='color:#FFD700;'>错误: {error_msg}</span>"
        if context:
            log_msg += f" <span style='color:#87CEEB;'>上下文: {context}</span>"
        
        # 记录到日志
        self._log_message(log_msg)
        
        # 同时输出到控制台（包含完整堆栈）
        account_tag = f"[{self.account_name}]" if self.is_multi_account_mode else "[主窗口]"
        print(f"{account_tag} [异常] {operation}")
        print(f"  类型: {error_type}")
        print(f"  错误: {error_msg}")
        if context:
            print(f"  上下文: {context}")
        print(f"  堆栈:\n{traceback_str}")
        sys.stdout.flush()
    
    def _log_message(self, text):
        """记录日志消息"""
        # 多小号模式：同时发送到控制面板和本地日志显示
        if self.is_multi_account_mode:
            # 发送到控制面板（全局日志）
            if self.log_callback:
                self.log_callback(text)
            # 同时显示在小号窗口的日志中
            if hasattr(self, 'log_display') and self.log_display:
                self.add_log(text)
        else:
            # 单窗口模式：只发送到本地日志
            global_signal.log_msg.emit(text)
    
    def _update_log_header(self):
        """更新日志区域顶部提示信息（仅暖场说明）"""
        if not self.is_multi_account_mode or not hasattr(self, 'log_display'):
            return
        
        warmup_note = (
            "<span style='color:#FFD700;'>【提示】</span> "
            "<span style='color:#87CEEB;'>暖场功能只会在首次捕获到弹幕后才会启动，以防止异常情况。</span><br>"
        )
        
        # 保存当前滚动位置
        scrollbar = self.log_display.verticalScrollBar()
        scroll_position = scrollbar.value()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 10
        
        # 获取现有日志内容（跳过头部）
        current_html = self.log_display.toHtml()
        # 找到第一个日志条目的位置（包含时间戳的行）
        lines = current_html.split('<br>')
        header_lines = 0
        for i, line in enumerate(lines):
            if '[提示]' in line:
                header_lines = i + 1
            elif '<b>[' in line and ']</b>' in line:  # 找到第一个日志条目
                break
        
        # 保留头部和实际日志内容
        if header_lines > 0:
            log_content_lines = lines[header_lines:]
        else:
            log_content_lines = lines
        
        # 重新组合HTML（头部 + 日志内容）
        log_content_html = '<br>'.join(log_content_lines)
        
        # 更新显示
        self.log_display.setHtml(warmup_note + log_content_html)
        
        # 恢复滚动位置（如果之前在底部，保持到底部）
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(scroll_position)
    
    def _update_refresh_countdown(self):
        """更新刷新倒计时显示（在窗口顶部标签）"""
        if not self.is_multi_account_mode:
            return
        
        if not hasattr(self, 'refresh_countdown_label'):
            return
        
        # 计算刷新倒计时（2小时 = 7200秒）
        if hasattr(self, 'last_refresh_time'):
            elapsed = time.time() - self.last_refresh_time
            remaining = 7200 - elapsed  # 7200秒 = 2小时
            if remaining < 0:
                remaining = 0
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            seconds = int(remaining % 60)
            if hours > 0:
                countdown_text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                countdown_text = f"{minutes:02d}:{seconds:02d}"
        else:
            countdown_text = "02:00:00"
        
        # 更新标签文本
        self.refresh_countdown_label.setText(f"距离下次自动刷新: {countdown_text}")
        
    def add_log(self, text):
        """添加日志到显示区域"""
        t = datetime.now().strftime("%H:%M:%S")
        # 保存当前滚动位置
        scrollbar = self.log_display.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 10
        
        # 获取当前HTML内容
        current_html = self.log_display.toHtml()
        
        # 找到头部结束位置（仅暖场提示）
        lines = current_html.split('<br>')
        header_end = 0
        for i, line in enumerate(lines):
            if '[提示]' in line:
                header_end = i + 1
                break
        
        # 构建新内容：头部 + 新日志 + 原有日志
        header_lines = lines[:header_end]
        log_lines = lines[header_end:]
        
        # 添加新日志
        new_log_line = f"<b>[{t}]</b> {text}"
        log_lines.append(new_log_line)
        
        # 重新组合
        new_html = '<br>'.join(header_lines + log_lines)
        self.log_display.setHtml(new_html)
        
        # 恢复滚动位置
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(scrollbar.value())
        
    def open_sub_win(self, tag):
        """打开子配置窗口"""
        if tag == 'reply':
            self.reply_win = BaseRuleManager(self.cfg, "关键词回复策略", "reply_rules")
            # 当窗口关闭时（配置已保存），重新加载配置以确保热更新生效
            def on_reply_win_closed():
                self.reload_account_config()
            self.reply_win.destroyed.connect(on_reply_win_closed)
            self.reply_win.show()
        elif tag == 'spec':
            self.spec_win = BaseRuleManager(self.cfg, "特定艾特策略", "specific_rules")
            def on_spec_win_closed():
                self.reload_account_config()
            self.spec_win.destroyed.connect(on_spec_win_closed)
            self.spec_win.show()
        elif tag == 'warm':
            self.warm_win = WarmupManager(self.cfg)
            def on_warm_win_closed():
                self.reload_account_config()
            self.warm_win.destroyed.connect(on_warm_win_closed)
            self.warm_win.show()
        elif tag == 'advanced':
            from ui_managers import AdvancedReplyManager
            self.advanced_win = AdvancedReplyManager(self.cfg)
            def on_advanced_win_closed():
                self.reload_account_config()
            self.advanced_win.destroyed.connect(on_advanced_win_closed)
            self.advanced_win.show()
            
    def _on_config_updated(self, new_cfg):
        """接收配置更新（多小号模式）"""
        # 更新本地配置引用（但保留账户特定配置）
        # 注意：这里只更新全局配置，账户特定配置（reply_rules, specific_rules, warmup_msgs）由 reload_account_config 处理
        global_fields = ['auto_reply_enabled', 'specific_reply_enabled', 'advanced_reply_enabled', 'warmup_enabled', 
                        'reply_interval', 'random_jitter',
                        'queue_mode', 'queue_time_window', 'queue_lock_timeout', 'strict_single_reply',
                        'auto_cleanup_locks', 'allow_multiple_reply', 'account_priorities', 'hide_web',
                        'random_space_insert_enabled', 'command_enabled', 'command_user']
        for field in global_fields:
            if field in new_cfg:
                self.cfg[field] = new_cfg[field]
        
        # 如果全局配置中包含规则配置，也需要更新（但账户特定配置优先级更高）
        if 'reply_rules' in new_cfg and 'reply_rules' not in self.account_data:
            self.cfg['reply_rules'] = new_cfg['reply_rules']
        if 'specific_rules' in new_cfg and 'specific_rules' not in self.account_data:
            self.cfg['specific_rules'] = new_cfg['specific_rules']
        if 'warmup_msgs' in new_cfg and 'warmup_msgs' not in self.account_data:
            self.cfg['warmup_msgs'] = new_cfg['warmup_msgs']
        if 'warmup_rules' in new_cfg and 'warmup_rules' not in self.account_data:
            self.cfg['warmup_rules'] = new_cfg['warmup_rules']
        if 'advanced_reply_rules' in new_cfg and 'advanced_reply_rules' not in self.account_data:
            self.cfg['advanced_reply_rules'] = new_cfg['advanced_reply_rules']
        
        # 更新全局队列配置
        global_queue.set_queue_mode(self.cfg.get('queue_mode', '轮询'))
        global_queue.set_time_window(self.cfg.get('queue_time_window', 5.0))
        global_queue.set_lock_timeout(self.cfg.get('queue_lock_timeout', 30.0))
        global_queue.set_strict_single_reply(self.cfg.get('strict_single_reply', True))
        global_queue.set_auto_cleanup(self.cfg.get('auto_cleanup_locks', True))
        global_queue.set_allow_multiple_reply(self.cfg.get('allow_multiple_reply', False))
        
        # 更新账户优先级
        account_priorities = self.cfg.get('account_priorities', {})
        for account_name, priority in account_priorities.items():
            global_queue.set_account_priority(account_name, priority)
        
        # 更新消息发送器配置
        if hasattr(self, 'message_sender'):
            self.message_sender.set_intervals(
                self.cfg.get('reply_interval', 4),
                self.cfg.get('random_jitter', 2.0)
            )
            self.message_sender.set_random_space_insert(
                self.cfg.get('random_space_insert_enabled', False)
            )
        
        # 重新加载账户配置（这会合并全局配置和账户特定配置，并重新创建处理器）
        # 注意：这个方法会重新创建 reply_handler，所以规则配置会自动更新
        self.reload_account_config()
        
        # 更新视图
        self.update_view()
        
    def _update_hide_view(self):
        """更新隐藏视图状态（多小号模式）"""
        self.cfg['hide_web'] = self.cb_hide.isChecked()
        self.update_view()
        
    def update_cfg(self):
        """更新配置（单窗口模式）"""
        if self.is_multi_account_mode:
            return  # 多小号模式不由子窗口控制配置
            
        self.cfg['hide_web'] = self.cb_hide.isChecked()
        self.cfg['auto_reply_enabled'] = self.cb_reply.isChecked()
        self.cfg['warmup_enabled'] = self.cb_warm.isChecked()
        self.cfg['specific_reply_enabled'] = self.cb_spec.isChecked()
        self.cfg['my_nickname'] = self.edit_me.text().strip()
        self.cfg['reply_interval'] = self.sp_step.value()
        self.cfg['random_jitter'] = self.sp_jitter.value()
        
        # 更新模块配置
        self.danmu_monitor.set_nickname(self.cfg['my_nickname'])
        self.reply_handler.set_enabled(
            self.cfg['auto_reply_enabled'],
            self.cfg['specific_reply_enabled']
        )
        self.warmup_handler.set_enabled(self.cfg['warmup_enabled'])
        if hasattr(self, 'command_handler'):
            self.command_handler.set_enabled(self.cfg.get('command_enabled', False))
            self.command_handler.set_command_user(self.cfg.get('command_user', ''))
            self.command_handler.set_silent_mode(self.cfg.get('command_silent_mode', False))
        self.message_sender.set_intervals(
            self.cfg['reply_interval'],
            self.cfg['random_jitter']
        )
        
        # 保存配置并更新视图
        save_cfg(self.cfg)
        self.update_view()
        
    def update_other_account_nicknames(self, other_nicknames):
        """更新其他小号的昵称列表（由控制面板调用）"""
        self.other_nicknames = other_nicknames or []
        if self.is_multi_account_mode:
            self.danmu_monitor.set_other_account_nicknames(self.other_nicknames)
    
    def reload_account_config(self):
        """重新加载账户配置（由控制面板调用）"""
        if not self.is_multi_account_mode:
            # 单窗口模式：重新加载配置并重新创建处理器（确保配置更新生效）
            from config_manager import load_cfg
            self.cfg = load_cfg()
            
            # 保存暖场处理器的状态（避免重置计时器）
            # 注意：只有在功能启用时才保存状态
            warmup_state = None
            if hasattr(self, 'warmup_handler') and self.warmup_handler.enabled:
                warmup_state = self.warmup_handler.get_state()
            
            # 重新创建回复处理器和暖场处理器（使用更新后的配置）
            self.reply_handler = ReplyHandler(self.cfg, self._log_message, None)
            self.reply_handler.set_enabled(
                self.cfg.get('auto_reply_enabled', False),
                self.cfg.get('specific_reply_enabled', False),
                self.cfg.get('advanced_reply_enabled', False)
            )
            self.warmup_handler = WarmupHandler(self.cfg, self._log_message)
            # 先设置启用状态（这会初始化计时器）
            warmup_enabled = self.cfg.get('warmup_enabled', False)
            self.warmup_handler.set_enabled(warmup_enabled)
            # 只有在功能启用时才恢复状态（避免在禁用时恢复旧的计时数据）
            if warmup_enabled and warmup_state:
                self.warmup_handler.restore_state(warmup_state)
            # 指令处理器（使用全局配置）
            self.command_handler = CommandHandler(self.cfg, self._log_message)
            self.command_handler.set_enabled(self.cfg.get('command_enabled', False))
            self.command_handler.set_command_user(self.cfg.get('command_user', ''))
            return
        
        # 多账户模式：重新加载账户数据
        # 保存暖场处理器的状态（避免重置计时器）
        # 注意：只有在功能启用时才保存状态
        warmup_state = None
        if hasattr(self, 'warmup_handler') and self.warmup_handler.enabled:
            warmup_state = self.warmup_handler.get_state()
        
        from account_manager import get_account
        account_data = get_account(self.account_name)
        if account_data:
            # 更新账户数据引用
            self.account_data = account_data
            
            # 如果配置中有独立规则，更新回复处理器的配置
            # 这里需要合并账户配置和全局配置
            account_cfg = self.cfg.copy()
            
            # 只有当账户数据中有reply_rules键且不为空列表时，才使用账户配置
            if 'reply_rules' in account_data:
                account_reply_rules = account_data.get('reply_rules', [])
                if isinstance(account_reply_rules, list) and len(account_reply_rules) > 0:
                    account_cfg['reply_rules'] = account_reply_rules
                # 如果账户规则为空列表，使用全局配置（已在copy中，不需要修改）
            
            if 'specific_rules' in account_data:
                account_specific_rules = account_data.get('specific_rules', [])
                if isinstance(account_specific_rules, list) and len(account_specific_rules) > 0:
                    account_cfg['specific_rules'] = account_specific_rules
            # 如果没有账户特定规则，使用全局规则（已在copy中）
            
            if 'warmup_msgs' in account_data:
                account_cfg['warmup_msgs'] = account_data.get('warmup_msgs', '')
            # warmup_rules：如果有账户特定规则，合并全局规则和账户规则（账户规则在前）
            if 'warmup_rules' in account_data:
                account_warmup_rules = account_data.get('warmup_rules', [])
                global_warmup_rules = self.cfg.get('warmup_rules', [])
                # 合并规则：账户规则在前，全局规则在后（这样账户规则优先级更高）
                account_cfg['warmup_rules'] = account_warmup_rules + global_warmup_rules
            # 如果没有账户特定规则，使用全局规则（已在copy中）
            
            # advanced_reply_rules：如果有账户特定规则，合并全局规则和账户规则（账户规则在前）
            if 'advanced_reply_rules' in account_data:
                account_advanced_rules = account_data.get('advanced_reply_rules', [])
                global_advanced_rules = self.cfg.get('advanced_reply_rules', [])
                # 合并规则：账户规则在前，全局规则在后（这样账户规则优先级更高）
                account_cfg['advanced_reply_rules'] = account_advanced_rules + global_advanced_rules
            # 如果没有账户特定规则，使用全局规则（已在copy中）
            
            # 重新创建回复处理器和暖场处理器（使用更新后的配置）
            from reply_handler import ReplyHandler
            from warmup_handler import WarmupHandler
            self.reply_handler = ReplyHandler(account_cfg, self._log_message, self.account_name)
            self.reply_handler.set_enabled(
                account_cfg.get('auto_reply_enabled', False),
                account_cfg.get('specific_reply_enabled', False),
                account_cfg.get('advanced_reply_enabled', False)
            )
            self.warmup_handler = WarmupHandler(account_cfg, self._log_message)
            # 先设置启用状态（这会初始化计时器）
            warmup_enabled = account_cfg.get('warmup_enabled', False)
            self.warmup_handler.set_enabled(warmup_enabled)
            # 只有在功能启用时才恢复状态（避免在禁用时恢复旧的计时数据）
            if warmup_enabled and warmup_state:
                self.warmup_handler.restore_state(warmup_state)
            # 指令处理器（使用全局配置）
            if not hasattr(self, 'command_handler'):
                from command_handler import CommandHandler
                self.command_handler = CommandHandler(self.cfg, self._log_message)
            self.command_handler.set_enabled(self.cfg.get('command_enabled', False))
            self.command_handler.set_command_user(self.cfg.get('command_user', ''))
            self.command_handler.set_silent_mode(self.cfg.get('command_silent_mode', False))
    
    def update_account_info(self, nickname, url):
        """更新账户信息（由控制面板调用）"""
        self.account_nickname = nickname
        self.account_url = url
        self.danmu_monitor.set_nickname(nickname)
        if url:
            self.url_input.setText(url)
        if self.is_multi_account_mode:
            title_suffix = " | 开发者: 故里何日还 | 仅供学习交流，禁止倒卖"
            self.setWindowTitle(f"小号窗口: {self.account_name} ({self.account_nickname}){title_suffix}")
        
    def update_view(self):
        """更新视图"""
        if self.cfg['hide_web']:
            self.browser.hide()
            self.setFixedHeight(450)
        else:
            self.browser.show()
            self.setMinimumHeight(600)
            self.resize(1350, 950)
            
    def load_url(self):
        """加载URL"""
        url = self.url_input.text().strip()
        if url:
            self.browser.load(QUrl(url))
            self.stream_started = True  # 标记直播间已启动
            if not hasattr(self, 'stream_start_time'):
                self.stream_start_time = time.time()
            # 更新最后刷新时间（多小号模式）
            if self.is_multi_account_mode:
                if hasattr(self, 'refresh_timer'):
                    self.last_refresh_time = time.time()
                    self._update_refresh_countdown()  # 更新窗口顶部倒计时显示
                    # 重置健康检查相关变量
                    self.last_reply_box_check = time.time()
                    self.consecutive_login_failures = 0
    
    def _check_page_health(self):
        """检查页面健康状态（多小号模式，每5分钟检查一次）"""
        if not self.is_multi_account_mode:
            return
        
        # 检查是否已经启动
        if not self.stream_started:
            return
        
        try:
            # 检查登录状态（如果回复框未检测到，可能已掉登录）
            current_time = time.time()
            # 如果超过30秒没有检测到回复框，且之前检测到过，可能已掉登录
            if (self.reply_box_detected == False and 
                hasattr(self, 'last_reply_box_check') and 
                current_time - self.last_reply_box_check > 30):
                
                self.consecutive_login_failures += 1
                
                # 如果连续3次检查都未登录，尝试恢复
                if self.consecutive_login_failures >= 3:
                    self._log_message(f"<span style='color:#FF6B6B;'>[页面健康检查]</span> 检测到可能已掉登录，尝试恢复...")
                    # 使用重新加载URL而不是reload，更温和
                    url = self.url_input.text().strip()
                    if url:
                        self.browser.load(QUrl(url))
                        self.consecutive_login_failures = 0  # 重置计数器
                        self._log_message(f"<span style='color:#FFD700;'>[页面恢复]</span> 已重新加载页面，请检查登录状态")
                else:
                    self._log_message(f"<span style='color:#FFA500;'>[页面健康检查]</span> 警告：回复框未检测到，可能已掉登录（{self.consecutive_login_failures}/3）")
            else:
                # 如果检测到回复框，重置失败计数
                if self.reply_box_detected:
                    self.consecutive_login_failures = 0
                    self.last_reply_box_check = current_time
                    
        except Exception as e:
            # 健康检查失败时记录日志，但不影响程序运行
            self._log_exception("页面健康检查", e, context="不影响程序运行")
    
    def _auto_refresh_browser(self):
        """自动刷新浏览器页面（多小号模式，每2小时执行一次）"""
        if not self.is_multi_account_mode:
            return
        
        # 检查是否有有效的URL
        url = self.url_input.text().strip()
        if not url:
            return
        
        # 检查是否已经启动（stream_started为True）
        if not self.stream_started:
            return
        
        try:
            # 在刷新前检查登录状态
            if not self.reply_box_detected:
                self._log_message(f"<span style='color:#FFA500;'>[自动刷新]</span> 检测到未登录状态，跳过刷新以避免进一步问题")
                return
            
            # 记录刷新日志
            self._log_message(f"<span style='color:#FFD700;'>[自动刷新]</span> 每2小时自动刷新浏览器页面，防止长时间运行后停止工作")
            
            # 使用重新加载URL而不是reload，更温和，减少掉登录风险
            # reload() 可能导致cookie丢失，使用load()重新加载URL更安全
            self.browser.load(QUrl(url))
            
            # 更新最后刷新时间
            self.last_refresh_time = time.time()
            
            # 更新窗口顶部倒计时显示（重置倒计时）
            self._update_refresh_countdown()
            
            # 重置登录状态检测（等待页面重新加载后重新检测）
            self.reply_box_detected = False
            self.consecutive_login_failures = 0
            
        except Exception as e:
            # 刷新失败时记录日志，但不影响程序运行
            self._log_exception("自动刷新浏览器", e, context="不影响程序运行")
            
    def _inject_js(self):
        """注入JavaScript代码（支持弹幕、礼物、在线人数等）"""
        try:
            # 检查浏览器和页面是否已准备好
            if not hasattr(self, 'browser') or not self.browser:
                return
            page = self.browser.page()
            if not page:
                return
        except Exception as e:
            # 如果检查失败，记录日志并静默返回，避免崩溃
            try:
                self._log_exception("注入JavaScript检查", e, context="静默返回，避免崩溃")
            except:
                # 如果_log_exception也失败，只打印到控制台
                print(f"[异常] 注入JavaScript检查失败: {type(e).__name__}: {e}")
                sys.stdout.flush()
            return
        
        # 使用独立的弹幕和礼物捕获模块
        if hasattr(self, 'danmu_gift_scraper'):
            self.danmu_gift_scraper.inject(page)


def main():
    """主函数（仅用于直接运行此模块时，打包环境不应执行）"""
    # 双重检查：防止在打包环境或已有QApplication时执行
    if getattr(sys, 'frozen', False):
        print("错误: main_window.main() 不应在打包环境中调用")
        return
    
    # 检查是否已有QApplication实例（防止在打包环境中重复创建）
    app = QApplication.instance()
    if app is not None:
        # 如果已有QApplication实例，说明可能是从主程序导入的，不应该创建新窗口
        print("警告: main_window.main() 不应在已有QApplication的情况下调用")
        print(f"警告: 当前QApplication对象: {app}")
        import traceback
        print("警告: 调用堆栈:")
        traceback.print_stack()
        sys.stdout.flush()
        return
    
    # 只有在非打包环境且没有QApplication时才创建
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    QWebEngineProfile.defaultProfile().setHttpUserAgent(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    
    cfg = load_cfg()
    # 创建单窗口模式的LiveBrowser（仅用于直接运行此模块时）
    # 注意：在多小号模式下，应该通过control_panel创建窗口，而不是直接调用main()
    win = LiveBrowser(cfg, account_data=None)  # account_data=None表示单窗口模式
    win.show()
    sys.exit(app.exec())


# 仅在直接运行此文件时执行（打包环境不应触发）
# 添加额外检查，确保不是从打包的EXE中调用
if __name__ == "__main__":
    # 多重检查：防止在打包环境或已有QApplication时执行
    if getattr(sys, 'frozen', False):
        print("错误: main_window.py 不应在打包环境中作为入口点执行")
        print("请使用 main.py 作为程序入口点")
        sys.exit(1)
    
    # 检查是否已有QApplication实例
    from PyQt6.QtWidgets import QApplication
    if QApplication.instance() is not None:
        print("错误: main_window.py 不应在已有QApplication的情况下执行")
        print("请使用 main.py 作为程序入口点")
        sys.exit(1)
    
    # 只有在非打包环境且没有QApplication时才允许执行
    main()

