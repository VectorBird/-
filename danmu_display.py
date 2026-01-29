"""
弹幕姬显示模块 - 从单文件版提取的弹幕显示功能
"""
import os
import sys
import json
import re
import csv
import datetime

from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QFrame, QLineEdit, QPushButton, QCheckBox, QComboBox,
                             QScrollArea, QSpinBox, QColorDialog, QGroupBox, QListWidget, QAbstractItemView,
                             QTextEdit)
from PyQt6.QtCore import (Qt, pyqtSignal, QObject, pyqtSlot, QUrl, QTimer,
                          QPropertyAnimation, QEasingCurve, QCoreApplication, QPoint)
from PyQt6.QtGui import QGuiApplication, QMouseEvent, QColor, QTextCursor
# 移除未使用的 WebEngine 相关导入

from config_manager import load_cfg, save_cfg
from danmu_monitor import global_signal as danmu_monitor_signal

# --- 配置文件管理 ---
DANMU_CONFIG_FILE = "danmu_cfg_v51.json"

def load_persistent_cfg():
    """加载弹幕姬配置文件"""
    default = {
        "use_gpu": True, 
        "win_w": 400, "win_h": 750, "pos_x": 100, "pos_y": 100,
        "font_size": 24,  # 弹幕字体大小
        "font_color": "#FFFFFF",  # 弹幕字体颜色
        "danmu_bg_color": "rgba(10,10,10,210)",  # 弹幕背景颜色（支持透明度，格式：rgba(r,g,b,a) 或 #RRGGBB）
        "gift_font_size": 28,  # 礼物字体大小
        "gift_font_color": "#FFD700",  # 礼物字体颜色
        "gift_bg_color": "rgba(10,10,10,180)",  # 礼物背景颜色（透明底色，与弹幕一致，格式：rgba(r,g,b,a) 或 #RRGGBB）
        "gift_duration": 10,  # 礼物停留时间（秒）
        "gift_max_count": 3,  # 礼物框最大显示数量（避免覆盖弹幕）
        "realtime_font_size": 24,  # 实时信息字体大小（与弹幕消息一致）
        "realtime_font_color": "#FFFFFF",  # 实时信息字体颜色（与弹幕消息一致）
        "realtime_bg_color": "rgba(10,10,10,180)",  # 实时信息背景颜色（透明底色，与弹幕一致，格式：rgba(r,g,b,a) 或 #RRGGBB）
        "realtime_duration": 2,  # 实时信息轮播停留时间（秒）- 快速轮播
        "hide_web": False, "is_locked": False,
        "duration_normal": 10,  # 普通弹幕停留时间（秒）
        "duration_pin": 60,  # 置顶关键词弹幕停留时间（秒）
        "pin_color": "#FF00FF",  # 置顶关键词弹幕文字颜色
        "pin_bg_color": "rgba(40,0,40,240)",  # 置顶关键词弹幕背景颜色
        "block_list": [],  # 清空默认屏蔽关键词
        "pin_list": [],  # 清空默认置顶关键词
        "block_gifts": False,  # 是否屏蔽礼物
        "block_self_danmu": False,  # 是否屏蔽小号的自我发言
        "block_users": [],  # 自定义屏蔽用户（昵称）列表
        "show_stats": True,
        "stats_selector": "[data-e2e='live-room-online-count'], .online-count",
        "stats_font_size": 18, 
        "stats_pos": "bottom",  # "top" 或 "bottom" - 在线观众显示框位置
        "show_gifts": True,
        "show_enters": False,
        "show_likes": True,
        "show_total_enter": True,
        "show_realtime_info": True,  # 是否显示实时信息
        "connection_mode": "auto",  # "auto", "websocket", "dom"
        "use_websocket": True,
        "show_debug_log": True
    }
    if os.path.exists(DANMU_CONFIG_FILE):
        try:
            with open(DANMU_CONFIG_FILE, "r", encoding='utf-8') as f:
                return {**default, **json.load(f)}
        except: pass
    return default

def save_persistent_cfg(data):
    """保存弹幕姬配置文件"""
    try:
        with open(DANMU_CONFIG_FILE, "w", encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except: pass

# --- 日志记录器 ---
class DanmuLogger:
    def __init__(self):
        self.log_dir = "danmu_logs"
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.filename = os.path.join(self.log_dir, f"{timestamp}_全景日志.csv")
        
        try:
            with open(self.filename, mode='w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["时间", "类型", "用户", "内容", "额外信息"])
        except Exception as e:
            print(f"日志初始化失败: {e}")

    def write_log(self, log_type, user, content, extra=""):
        try:
            now_str = datetime.datetime.now().strftime("%H:%M:%S")
            with open(self.filename, mode='a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([now_str, log_type, user, content, extra])
        except: pass

# --- 信号与桥梁 ---
class GlobalSignal(QObject):
    chat_received = pyqtSignal(dict)
    stats_received = pyqtSignal(str)
    gift_received = pyqtSignal(dict)
    enter_received = pyqtSignal(dict)
    like_received = pyqtSignal(dict)
    total_enter_received = pyqtSignal(str)
    config_update = pyqtSignal()
    pos_moved = pyqtSignal(int, int)
    raw_data_received = pyqtSignal(str, dict)

global_signal = GlobalSignal()

# DouyinWebSocketFetcher 和 DanmuBridge 类已移除
# 弹幕姬现在只使用悬浮窗口，复用自动回复的弹幕捕获逻辑
# 这些类在 danmu_monitor.py 中已有定义，不需要重复

# --- 弹幕条目组件 ---
class DanmuItem(QFrame):
    def __init__(self, user, content, width, font_size, text_color, duration_sec, is_pinned=False, item_type="chat", extra_info="", gift_image_url="", font_color=None, pin_bg_color=None, bg_color=None):
        super().__init__()
        self.setFixedWidth(width - 20)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        
        type_colors = {
            "chat": ("#42C3FB", font_color or "#FFFFFF"),  # 使用自定义颜色或默认白色
            "gift": ("#FFD700", "#FFA500"),
            "enter": ("#00FF00", "#90EE90"),
            "like": ("#FF69B4", "#FFB6C1")
        }
        user_color, content_color = type_colors.get(item_type, ("#42C3FB", font_color or "#FFFFFF"))
        
        if is_pinned:
            # 使用配置的背景颜色，如果没有则使用默认值
            if pin_bg_color is None:
                pin_bg_color = "rgba(40,0,40,240)"  # 默认值
            bg_style = f"background-color:{pin_bg_color}; border:2px solid {text_color}; border-radius:8px;"
            final_text_color = text_color
            final_font_size = font_size + 4
        else:
            # 如果提供了自定义背景颜色，使用它；否则使用默认值
            if bg_color:
                bg_style = f"background-color:{bg_color}; border:1px solid rgba(255,255,255,30); border-radius:12px;"
            else:
                bg_style = "background-color:rgba(10,10,10,210); border:1px solid rgba(255,255,255,30); border-radius:12px;"
            final_text_color = content_color
            final_font_size = font_size

        self.setStyleSheet(bg_style)
        style = f"font-family:'Microsoft YaHei UI';font-size:{final_font_size}px;font-weight:bold;line-height:1.2;"
        
        type_icons = {
            "chat": "💬",
            "gift": "🎁",
            "enter": "👤",
            "like": "❤️"
        }
        icon = type_icons.get(item_type, "💬")
        
        gift_img_html = ""
        if gift_image_url and item_type == "gift":
            img_size = max(16, min(32, font_size))
            safe_url = gift_image_url.replace('&', '&amp;').replace('"', '&quot;')
            gift_img_html = f'<img src="{safe_url}" style="width:{img_size}px; height:{img_size}px; vertical-align:middle; margin:0 4px; border-radius:2px;" />'
        
        if extra_info:
            html = f"""<div style="{style}"><span style="color:{user_color};">{icon} {user}: </span>{gift_img_html}<span style="color:{final_text_color};">{content}</span> <span style="color:#AAAAAA; font-size:{max(10, final_font_size-4)}px;">{extra_info}</span></div>"""
        else:
            html = f"""<div style="{style}"><span style="color:{user_color};">{icon} {user}: </span>{gift_img_html}<span style="color:{final_text_color};">{content}</span></div>"""
        
        self.label = QLabel(html)
        self.label.setWordWrap(True)
        self.label.setAttribute(Qt.WidgetAttribute(121), True) 
        layout.addWidget(self.label)
        QTimer.singleShot(int(duration_sec * 1000), self.deleteLater)

# --- 悬浮展示窗口 ---
class DanmuOverlay(QWidget):
    def __init__(self, cfg_ref, account_nicknames=None):
        """
        初始化弹幕展示窗口
        
        Args:
            cfg_ref: 配置字典引用
            account_nicknames: 所有小号的昵称列表，用于屏蔽自我发言
        """
        super().__init__()
        self.cfg = cfg_ref
        self._drag_pos = QPoint()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # 存储小号昵称列表（用于屏蔽自我发言）
        self.account_nicknames = set(account_nicknames) if account_nicknames else set()
        
        self.logger = DanmuLogger()
        self.last_logged_count = -1
        self.last_like_count = -1
        self.last_enter_count = 0
        self.enter_count = 0
        self.current_viewer_count = None  # 当前在线人数
        self.current_like_count = None    # 当前点赞数

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)

        # 礼物置顶容器（高亮显示，限制最大高度避免覆盖弹幕）
        self.gift_container = QWidget()
        self.gift_layout = QVBoxLayout(self.gift_container)
        self.gift_layout.setContentsMargins(0,0,0,0)
        self.gift_layout.setSpacing(4)
        # 在rearrange_layout中设置高度限制
        # 用于跟踪已显示的礼物（用户+礼物名 -> DanmuItem），用于更新数量
        self.gift_items_map = {}  # {user|gift_name: DanmuItem}
        
        # 关键词置顶容器（原有功能）
        self.pin_container = QWidget()
        self.pin_layout = QVBoxLayout(self.pin_container)
        self.pin_layout.setContentsMargins(0,0,0,0)
        self.pin_layout.setSpacing(4)
        
        # 弹幕瀑布流容器
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background:transparent; border:none;")
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.addStretch() 
        self.scroll_area.setWidget(self.scroll_widget)
        
        # 实时信息底部轮播容器（固定框，快速轮播）
        self.realtime_container = QWidget()
        self.realtime_container.setFixedHeight(60)  # 固定高度，用于轮播显示
        # 背景颜色会在 refresh_window 中根据配置更新
        self.realtime_layout = QHBoxLayout(self.realtime_container)
        self.realtime_layout.setContentsMargins(10, 8, 10, 8)
        self.realtime_layout.setSpacing(5)
        self.realtime_label = QLabel("")
        self.realtime_label.setWordWrap(True)
        self.realtime_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.realtime_label.setTextFormat(Qt.TextFormat.RichText)
        self.realtime_layout.addWidget(self.realtime_label)
        self.realtime_queue = []  # 实时信息队列
        self.realtime_timer = QTimer()  # 实时信息轮播定时器
        self.realtime_timer.timeout.connect(self._show_next_realtime)
        self.current_realtime_index = 0
        
        # 初始化实时信息容器的背景颜色（根据配置）
        realtime_bg_color = self.cfg.get('realtime_bg_color', 'rgba(10,10,10,180)')
        if realtime_bg_color:
            self.realtime_container.setStyleSheet(f"background-color: {realtime_bg_color}; border-radius: 8px;")
        
        self.stats_frame = QFrame()
        self.stats_frame.setStyleSheet("""background-color: rgba(0, 0, 0, 220); border: 1px solid rgba(255, 255, 255, 50); border-radius: 5px;""")
        stats_layout = QVBoxLayout(self.stats_frame)
        stats_layout.setContentsMargins(10, 8, 10, 8)
        # 只保留在线观众显示，移除其他统计信息
        self.lbl_count = QLabel("等待数据...")
        self.lbl_count.setTextFormat(Qt.TextFormat.RichText) 
        stats_layout.addWidget(self.lbl_count)
        # 保留其他标签但不显示（用于兼容性）
        self.lbl_like = QLabel("")
        self.lbl_like.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_like.setVisible(False)
        self.lbl_enter = QLabel("")
        self.lbl_enter.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_enter.setVisible(False)
        self.lbl_total_enter = QLabel("")
        self.lbl_total_enter.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_total_enter.setVisible(False)
        
        # 监听现有的弹幕捕获信号（复用自动回复的弹幕捕获逻辑）
        try:
            danmu_monitor_signal.received.connect(self.on_danmu_data_received)
        except Exception as e:
            print(f"弹幕姬信号连接失败: {e}")
            import traceback
            traceback.print_exc()
        global_signal.config_update.connect(self.refresh_window)
        
        self.scroll_anim = QPropertyAnimation(self.scroll_area.verticalScrollBar(), b"value")
        
        # 初始化位置保存定时器
        self._save_pos_timer = None
        
        self.rearrange_layout()
        self.refresh_window()

    def _save_position(self):
        """保存窗口位置到配置文件"""
        try:
            save_persistent_cfg(self.cfg)
        except Exception as e:
            print(f"保存弹幕姬位置失败: {e}")

    def rearrange_layout(self):
        # 移除所有组件
        for i in reversed(range(self.main_layout.count())):
            self.main_layout.itemAt(i).widget().setParent(None)
        
        # 更新礼物容器最大高度（根据配置的最大数量动态设置）
        gift_max_count = self.cfg.get('gift_max_count', 3)
        max_height = min(gift_max_count * 60, 200)  # 最多200px高度
        self.gift_container.setMaximumHeight(max_height)
        
        pos = self.cfg.get('stats_pos', 'bottom')
        if pos == 'top':
            self.main_layout.addWidget(self.stats_frame)
            self.main_layout.addWidget(self.gift_container)  # 礼物置顶
            self.main_layout.addWidget(self.pin_container)  # 关键词置顶
            self.main_layout.addWidget(self.scroll_area, 1)  # 弹幕瀑布流
            self.main_layout.addWidget(self.realtime_container)  # 实时信息底部轮播
        else:
            self.main_layout.addWidget(self.gift_container)  # 礼物置顶
            self.main_layout.addWidget(self.pin_container)  # 关键词置顶
            self.main_layout.addWidget(self.scroll_area, 1)  # 弹幕瀑布流
            self.main_layout.addWidget(self.realtime_container)  # 实时信息底部轮播
            self.main_layout.addWidget(self.stats_frame)
        
        self.stats_frame.setVisible(self.cfg.get('show_stats', True))
        self.realtime_container.setVisible(self.cfg.get('show_realtime_info', True))
        # 更新实时信息容器的背景颜色（根据配置）
        realtime_bg_color = self.cfg.get('realtime_bg_color', 'rgba(10,10,10,180)')
        if realtime_bg_color:
            self.realtime_container.setStyleSheet(f"background-color: {realtime_bg_color}; border-radius: 8px;")
        # 只显示在线观众，其他统计信息隐藏
        self.lbl_like.setVisible(False)
        self.lbl_enter.setVisible(False)
        self.lbl_total_enter.setVisible(False)
    
    def _show_next_realtime(self):
        """显示下一个实时信息（轮播）"""
        if not self.realtime_queue:
            self.realtime_label.setText("")
            self.realtime_timer.stop()
            return
        
        if self.current_realtime_index >= len(self.realtime_queue):
            self.current_realtime_index = 0
        
        if self.current_realtime_index < len(self.realtime_queue):
            info = self.realtime_queue[self.current_realtime_index]
            user = info.get('user', '')
            info_type = info.get('info_type', 'other')
            content = info.get('content', '')
            
            # 格式化显示文本
            type_map = {
                'enter': '进入了直播间',
                'like': '为主播点赞了',
                'share': '分享了直播间',
                'top': '成为了观众TOP',
                'score': f'为主播加了{content}' if content else '为主播加了分'
            }
            action_text = type_map.get(info_type, '')
            display_text = f"{user} {action_text}" if user and action_text else f"{user}" if user else ""
            
            # 应用样式
            font_size = self.cfg.get('realtime_font_size', 20)
            font_color = self.cfg.get('realtime_font_color', '#98FB98')
            bg_color = self.cfg.get('realtime_bg_color', 'rgba(10,10,10,180)')
            
            html = f"""
            <div style="background-color:{bg_color}; border-radius:8px; padding:8px; font-family:'Microsoft YaHei UI'; font-size:{font_size}px; font-weight:bold; color:{font_color};">
                {display_text}
            </div>
            """
            self.realtime_label.setText(html)
            # 更新实时信息容器的背景颜色（如果配置了）
            if bg_color:
                self.realtime_container.setStyleSheet(f"background-color: {bg_color}; border-radius: 8px;")
            self.current_realtime_index += 1
        else:
            self.current_realtime_index = 0

    def parse_raw_count(self, text):
        try:
            text = text.replace(',', '')
            is_wan = '万' in text or 'w' in text.lower()
            nums = re.findall(r"\d+\.?\d*", text)
            if not nums: return 0
            val = float(nums[0])
            if is_wan: val *= 10000
            return int(val)
        except: return 0

    def update_stats(self, count_str, like_count_str=None):
        font_size = self.cfg.get('stats_font_size', 16)
        val = self.parse_raw_count(count_str)
        
        # 保存当前在线人数
        self.current_viewer_count = count_str
        
        if val != self.last_logged_count:
            self.logger.write_log("在线人数", "[系统]", str(val), "")
            self.last_logged_count = val

        tiers = [60, 160, 260, 500, 1000, 3000, 5000, 10000]
        color = "#BBBBBB" 
        if val >= 10000: color = "#FF0000"
        elif val >= 5000: color = "#EE82EE"
        elif val >= 3000: color = "#FFA500"
        elif val >= 1000: color = "#FFFF00"
        elif val >= 500: color = "#ADFF2F"
        elif val >= 260: color = "#00FF00"
        elif val >= 160: color = "#42C3FB"
        elif val >= 60: color = "#00FFFF"

        next_goal = None
        for t in tiers:
            if val < t:
                next_goal = t
                break
        
        main_text = f"在线观众: {count_str}"
        gap_html = ""
        if next_goal:
            diff = next_goal - val
            if diff > 0:
                small_size = max(10, int(font_size * 0.8))
                gap_html = f" <span style='font-size:{small_size}px; color:#DDDDDD;'>(距{next_goal}还差{int(diff)})</span>"

        # 添加点赞数显示（如果有）
        like_html = ""
        if like_count_str:
            like_html = f" <span style='font-family:\"Microsoft YaHei UI\"; font-weight:bold; font-size:{font_size}px; color:#FFD700; margin-left:15px;'>点赞: {like_count_str}</span>"

        final_html = f"<span style='font-family:\"Microsoft YaHei UI\"; font-weight:bold; font-size:{font_size}px; color:{color};'>{main_text}</span>{gap_html}{like_html}"
        self.lbl_count.setText(final_html)

    def refresh_window(self):
        """刷新窗口显示（当配置更新时调用）"""
        self.rearrange_layout()
        # 使用get方法获取配置，提供默认值
        # 从配置文件重新加载位置，确保使用最新保存的位置
        try:
            saved_cfg = load_persistent_cfg()
            pos_x = saved_cfg.get('pos_x', self.cfg.get('pos_x', 100))
            pos_y = saved_cfg.get('pos_y', self.cfg.get('pos_y', 100))
            # 更新当前cfg中的位置，保持同步
            self.cfg['pos_x'] = pos_x
            self.cfg['pos_y'] = pos_y
        except:
            pos_x = self.cfg.get('pos_x', 100)
            pos_y = self.cfg.get('pos_y', 100)
        win_w = self.cfg.get('win_w', 400)
        win_h = self.cfg.get('win_h', 750)
        self.setGeometry(pos_x, pos_y, win_w, win_h)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, self.cfg.get('is_locked', False))
        bg = "rgba(100, 100, 100, 50)" if not self.cfg.get('is_locked', False) else "transparent"
        self.setStyleSheet(f"background-color: {bg};")
        # 只显示在线观众，其他统计信息隐藏
        self.lbl_like.setVisible(False)
        self.lbl_enter.setVisible(False)
        self.lbl_total_enter.setVisible(False)
        self.show()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and not self.cfg.get('is_locked', False):
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            
    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton and not self.cfg.get('is_locked', False):
            try:
                new_pos = event.globalPosition().toPoint() - self._drag_pos
                self.move(new_pos)
                self.cfg['pos_x'], self.cfg['pos_y'] = new_pos.x(), new_pos.y()
                global_signal.pos_moved.emit(new_pos.x(), new_pos.y())
                # 保存位置到配置文件（延迟保存，避免频繁写入）
                try:
                    if self._save_pos_timer is None:
                        self._save_pos_timer = QTimer()
                        self._save_pos_timer.setSingleShot(True)
                        self._save_pos_timer.timeout.connect(self._save_position)
                    self._save_pos_timer.stop()
                    self._save_pos_timer.start(500)  # 500ms后保存，避免拖动时频繁写入
                except Exception as e:
                    # 如果定时器操作失败，静默处理，避免异常退出
                    pass
            except Exception as e:
                # 捕获所有异常，避免拖动时程序崩溃
                print(f"拖动弹幕姬窗口时出错: {e}")
                import traceback
                traceback.print_exc()
    
    def on_danmu_data_received(self, data):
        """接收来自弹幕监控器的数据（复用自动回复的弹幕捕获逻辑）"""
        data_type = data.get('type', 'danmu')
        
        if data_type == 'danmu':
            # 处理弹幕
            content = data.get('content', '')
            user = data.get('user', '').strip()
            if not content or not user:
                return
            
            # 检查是否是礼物消息（如果启用了屏蔽礼物，检查弹幕内容是否包含礼物特征）
            if self.cfg.get('block_gifts', False):
                # 检查弹幕内容是否包含礼物特征：× 数字 或 x 数字 或 送出了
                import re
                if re.search(r'[×x]\s*\d+', content) or '送出了' in content:
                    return  # 屏蔽礼物消息
            
            # 屏蔽小号的自我发言（如果启用了此选项）
            if self.cfg.get('block_self_danmu', False) and self.account_nicknames:
                # 检查用户昵称是否在小号昵称列表中
                if user in self.account_nicknames:
                    return  # 屏蔽小号的自我发言
                # 部分匹配（防止昵称有细微差异）
                for nickname in self.account_nicknames:
                    if nickname and (user == nickname.strip() or 
                                   user.startswith(nickname.strip()) or
                                   nickname.strip() in user):
                        return  # 屏蔽小号的自我发言
            
            # 屏蔽自定义用户（昵称列表）
            block_users = self.cfg.get('block_users', [])
            if block_users:
                # 精确匹配
                if user in block_users:
                    return  # 屏蔽该用户
                # 部分匹配
                for block_user in block_users:
                    if block_user and (user == block_user.strip() or 
                                     user.startswith(block_user.strip()) or
                                     block_user.strip() in user):
                        return  # 屏蔽该用户
            
            # 屏蔽关键词
            if any(w in content for w in self.cfg.get('block_list', [])): 
                return
            
            self.logger.write_log("弹幕", user, content, "")
            
            is_pinned = any(w in content for w in self.cfg.get('pin_list', []))
            font_color = self.cfg.get('font_color', '#FFFFFF')
            if is_pinned:
                pin_color = self.cfg.get('pin_color', '#FF00FF')
                pin_bg_color = self.cfg.get('pin_bg_color', 'rgba(40,0,40,240)')
                self.pin_layout.addWidget(DanmuItem(user, content, self.width(), self.cfg.get('font_size', 24), pin_color, self.cfg.get('duration_pin', 60), True, "chat", "", "", font_color, pin_bg_color))
                if self.pin_layout.count() > 4: 
                    self.pin_layout.takeAt(0).widget().deleteLater()
            else:
                # 使用配置的弹幕背景颜色和字号
                danmu_font_size = self.cfg.get('font_size', 24)
                danmu_bg_color = self.cfg.get('danmu_bg_color', 'rgba(10,10,10,210)')
                self.scroll_layout.insertWidget(self.scroll_layout.count()-1, 
                    DanmuItem(user, content, self.width(), danmu_font_size, "#FFFFFF", 
                             self.cfg.get('duration_normal', 10), False, "chat", "", "", 
                             font_color, None, danmu_bg_color))
                if self.scroll_layout.count() > 25: 
                    self.scroll_layout.takeAt(0).widget().deleteLater()
                if self.scroll_anim:
                    QTimer.singleShot(20, lambda: (self.scroll_anim.stop(), self.scroll_anim.setDuration(300), self.scroll_anim.setStartValue(self.scroll_area.verticalScrollBar().value()), self.scroll_anim.setEndValue(self.scroll_area.verticalScrollBar().maximum()), self.scroll_anim.setEasingCurve(QEasingCurve.Type.OutQuad), self.scroll_anim.start()))
        
        elif data_type == 'gift':
            # 处理礼物（检查是否屏蔽礼物）
            # 如果启用了屏蔽礼物，直接屏蔽所有礼物消息
            if self.cfg.get('block_gifts', False):
                return  # 屏蔽礼物消息，不显示
            # 如果未启用屏蔽，正常显示礼物
            self.on_gift_received(data)
        
        elif data_type == 'realtime_info':
            # 处理实时信息（底部轮播）
            self.on_realtime_info_received(data)
        
        elif data_type == 'viewer_count':
            # 处理在线人数（格式转换）
            count_str = str(data.get('viewer_count', '0'))
            self.current_viewer_count = count_str
            # 如果已经有点赞数，一起更新；否则只更新在线人数
            like_count_str = self.current_like_count if hasattr(self, 'current_like_count') and self.current_like_count else None
            self.update_stats(count_str, like_count_str)
        
        elif data_type == 'like_count':
            # 处理点赞数（本场点赞）
            count_str = str(data.get('like_count', '0'))
            self.current_like_count = count_str
            # 如果已经有在线人数，一起更新；否则只更新点赞数
            viewer_count_str = self.current_viewer_count if hasattr(self, 'current_viewer_count') and self.current_viewer_count else None
            if viewer_count_str:
                self.update_stats(viewer_count_str, count_str)
            else:
                # 如果还没有在线人数，先记录点赞数，等待在线人数数据
                pass
        
        elif data_type == 'enter':
            # 处理进人
            self.on_enter_received(data)

    def on_gift_received(self, data):
        """处理礼物数据（高亮置顶显示）"""
        user = data.get('user', '未知用户')
        gift_name = data.get('gift_name', '礼物')
        # 兼容不同的字段名
        gift_count = data.get('count', data.get('gift_count', '1'))
        gift_image_url = data.get('gift_image_url', '')
        is_update = data.get('is_update', False)  # 是否为更新（累加数量）
        
        # 优先使用display_text（如果存在），否则自己构造
        display_text = data.get('display_text', '')
        if not display_text:
            if gift_count and str(gift_count) != '1':
                display_text = f"{user} 送 {gift_name} ×{gift_count}"
            else:
                display_text = f"{user} 送 {gift_name}"
        
        extra = f"x{gift_count}" if gift_count else ""
        self.logger.write_log("礼物", user, gift_name, f"{extra} | 图片:{gift_image_url[:50] if gift_image_url else '无'}")
        
        if self.cfg.get('show_gifts', True):
            # 检查是否已存在相同的用户+礼物组合
            gift_key = f"{user}|{gift_name}"
            existing_item = self.gift_items_map.get(gift_key)
            
            if existing_item and is_update:
                # 如果已存在且是更新，则更新数量显示
                try:
                    # 更新显示文本
                    if display_text:
                        content = display_text
                    else:
                        if gift_count and str(gift_count) != '1':
                            content = f"{user} 送 {gift_name} ×{gift_count}"
                        else:
                            content = f"{user} 送 {gift_name}"
                    
                    # 更新DanmuItem的label内容
                    gift_font_size = self.cfg.get('gift_font_size', 28)
                    gift_font_color = self.cfg.get('gift_font_color', '#FFD700')
                    style = f"font-family:'Microsoft YaHei UI';font-size:{gift_font_size}px;font-weight:bold;line-height:1.2;"
                    icon = "🎁"
                    html = f"""<div style="{style}"><span style="color:{gift_font_color};">{icon} </span><span style="color:{gift_font_color};">{content}</span></div>"""
                    existing_item.label.setText(html)
                    return  # 已更新，不需要创建新项
                except Exception as e:
                    # 如果更新失败，删除旧项并创建新项
                    if gift_key in self.gift_items_map:
                        try:
                            existing_item.deleteLater()
                        except:
                            pass
                        del self.gift_items_map[gift_key]
            
            # 使用display_text或构造内容
            if display_text:
                # display_text格式：用户 送 礼物名 ×数量（已经包含用户名，不需要再传入user）
                # 直接使用display_text作为完整内容，user参数传入空字符串避免重复显示
                content = display_text
                display_user = ""  # 不显示用户名，因为display_text已经包含
            else:
                # 如果没有display_text，使用传统格式
                content = f"送出了 {gift_name}" if gift_name and gift_name != "礼物" else "送出了礼物"
                display_user = user  # 显示用户名
            
            # 使用自定义的礼物字体大小、颜色、背景颜色和停留时间
            gift_font_size = self.cfg.get('gift_font_size', 28)
            gift_font_color = self.cfg.get('gift_font_color', '#FFD700')
            gift_bg_color = self.cfg.get('gift_bg_color', 'rgba(10,10,10,180)')
            gift_duration = self.cfg.get('gift_duration', 10)  # 礼物停留时间（秒）
            
            # 礼物信息高亮置顶显示
            gift_item = DanmuItem(display_user, content, self.width(), gift_font_size, gift_font_color, 
                                 gift_duration, True, "gift", extra, gift_image_url, 
                                 gift_font_color, gift_bg_color)
            self.gift_layout.addWidget(gift_item)
            
            # 记录到映射表
            self.gift_items_map[gift_key] = gift_item
            
            # 限制礼物置顶区域最大显示数量（避免覆盖弹幕）
            gift_max_count = self.cfg.get('gift_max_count', 3)
            if self.gift_layout.count() > gift_max_count: 
                # 移除最旧的礼物项
                old_item = self.gift_layout.takeAt(0).widget()
                # 从映射表中删除
                for key, item in list(self.gift_items_map.items()):
                    if item == old_item:
                        del self.gift_items_map[key]
                        break
                old_item.deleteLater()
    
    def on_realtime_info_received(self, data):
        """处理实时信息（底部轮播）"""
        info_type = data.get('info_type', 'other')
        user = data.get('user', '')
        content = data.get('content', '')
        
        if not user:
            return
        
        # 添加到实时信息队列
        self.realtime_queue.append({
            'info_type': info_type,
            'user': user,
            'content': content
        })
        
        # 限制队列长度（最多保留10条）
        if len(self.realtime_queue) > 10:
            self.realtime_queue.pop(0)
        
        # 如果定时器未运行，启动轮播
        if not self.realtime_timer.isActive():
            self.current_realtime_index = 0
            self._show_next_realtime()
            duration = self.cfg.get('realtime_duration', 5) * 1000  # 转换为毫秒
            self.realtime_timer.start(duration)

    def on_enter_received(self, data):
        user = data.get('user', '未知用户')
        self.enter_count += 1
        self.logger.write_log("进人", user, "进入直播间", "")
        
        if self.cfg.get('show_enters', False):
            content = "进入直播间"
            self.scroll_layout.insertWidget(self.scroll_layout.count()-1, 
                DanmuItem(user, content, self.width(), self.cfg['font_size'], "#90EE90", 
                         max(3, self.cfg['duration_normal'] // 2), False, "enter"))
            if self.scroll_layout.count() > 25: 
                self.scroll_layout.takeAt(0).widget().deleteLater()
        
        self.lbl_enter.setText(f"<span style='color:#00FF00; font-size:12px;'>实时进人: {self.enter_count}</span>")
    
    def update_total_enter(self, count_str):
        """更新累计进人数量显示"""
        font_size = max(12, self.cfg.get('stats_font_size', 16) - 4)
        self.lbl_total_enter.setText(f"<span style='color:#00CED1; font-size:{font_size}px;'>📊 累计进人: {count_str}</span>")

    def on_like_received(self, data):
        count_str = data.get('count', '0')
        val = self.parse_raw_count(count_str)
        
        if val != self.last_like_count:
            self.logger.write_log("点赞", "[系统]", str(val), "")
            self.last_like_count = val
        
        font_size = max(12, self.cfg.get('stats_font_size', 16) - 4)
        self.lbl_like.setText(f"<span style='color:#FF69B4; font-size:{font_size}px;'>❤️ 点赞: {count_str}</span>")

# DanmuLiveBrowser 类已移除，不再需要独立的浏览器控制窗口
# 弹幕姬现在只使用悬浮窗口，复用自动回复的弹幕捕获逻辑

