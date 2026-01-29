"""
主控制面板 - 统一管理所有小号的配置和开关
"""
import os
import sys
import traceback

# 环境优化（需要在导入Qt之前）
os.environ["QT_GL_DEFAULT_BACKEND"] = "software"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--no-sandbox --disable-gpu --disable-software-rasterizer "
    "--ignore-gpu-blocklist --disable-background-timer-throttling "
    "--disable-logging --log-level=3"
)

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QCheckBox, QListWidget,
                             QListWidgetItem, QMessageBox, QDialog, QDialogButtonBox,
                             QTabWidget, QGroupBox, QSpinBox, QDoubleSpinBox, QTextEdit, 
                             QApplication, QComboBox, QFileDialog, QSplitter, QRadioButton, QButtonGroup,
                             QScrollArea, QAbstractItemView, QFrame, QInputDialog, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QGuiApplication, QTextCursor, QIcon, QPixmap, QColor
from PyQt6.QtWebEngineCore import QWebEngineProfile

from config_manager import load_cfg, save_cfg
from account_manager import (load_accounts, save_accounts, add_account, 
                            remove_account, update_account, get_all_accounts, get_account)
from ui_managers import BaseRuleManager, WarmupManager
from global_message_queue import global_queue
from statistics_manager import statistics_manager
from server_client import submit_keywords, check_ban_status
import json
import threading
import time
# 不再使用 global_logger，改用直接回调的方式传递日志
# 延迟导入LiveBrowser，避免循环导入
# 注意：为了PyInstaller打包时能正确识别依赖，这里添加一个条件导入提示
# 实际导入在 _start_account 函数中进行
if False:  # 永远不会执行，但PyInstaller会分析这个导入
    from main_window import LiveBrowser


class ConfigUpdateSignal(QObject):
    """配置更新信号"""
    config_updated = pyqtSignal(dict)  # 配置更新信号


def get_icon_path():
    """获取图标文件路径（支持打包环境）"""
    try:
        from path_utils import get_resource_path
        icon_path = get_resource_path("favicon.ico")
        if icon_path:
            return icon_path
    except ImportError:
        # 如果path_utils不可用（向后兼容），使用旧逻辑
        try:
            # PyInstaller打包后的临时目录
            if getattr(sys, 'frozen', False):
                base_dir = sys._MEIPASS
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(base_dir, "favicon.ico")
            if os.path.exists(icon_path):
                return icon_path
        except:
            pass
        # 尝试当前工作目录
        try:
            icon_path = os.path.join(os.getcwd(), "favicon.ico")
            if os.path.exists(icon_path):
                return icon_path
        except:
            pass
    return None


class AccountDialog(QDialog):
    """添加/编辑小号对话框"""
    
    def __init__(self, parent=None, account_data=None):
        super().__init__(parent)
        self.account_data = account_data
        self.setWindowTitle("添加小号" if account_data is None else "编辑小号")
        self.setMinimumSize(500, 350)
        self.resize(500, 350)
        
        # 设置窗口图标
        icon_path = get_icon_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))
        
        layout = QVBoxLayout(self)
        
        # 小号名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("小号名称:"))
        self.name_input = QLineEdit()
        if account_data:
            self.name_input.setText(account_data.get('name', ''))
            self.name_input.setEnabled(False)  # 编辑时不允许修改名称
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)
        
        # 昵称
        nickname_layout = QHBoxLayout()
        nickname_layout.addWidget(QLabel("小号在直播间的昵称(请严格填选,否则会导致循环回复):"))
        self.nickname_input = QLineEdit()
        if account_data:
            self.nickname_input.setText(account_data.get('nickname', ''))
        nickname_layout.addWidget(self.nickname_input)
        layout.addLayout(nickname_layout)
        
        # 直播间地址选择区域
        url_group = QGroupBox("直播间地址")
        url_group_layout = QVBoxLayout()
        
        # 第一行：地址输入和选择
        url_input_layout = QHBoxLayout()
        url_input_layout.addWidget(QLabel("地址:"))
        self.url_input = QLineEdit()
        if account_data:
            self.url_input.setText(account_data.get('url', ''))
        self.url_input.setPlaceholderText("粘贴直播间地址或从下方选择")
        url_input_layout.addWidget(self.url_input)
        url_group_layout.addLayout(url_input_layout)
        
        # 第二行：历史记录选择
        url_select_layout = QHBoxLayout()
        url_select_layout.addWidget(QLabel("历史记录:"))
        self.url_combo = QComboBox()
        self.url_combo.setEditable(False)
        self.url_combo.currentTextChanged.connect(self._on_url_selected)
        url_select_layout.addWidget(self.url_combo)
        
        # 添加按钮
        btn_add_room = QPushButton("➕ 添加")
        btn_add_room.setToolTip("将当前地址添加到历史记录")
        btn_add_room.clicked.connect(self._add_live_room)
        url_select_layout.addWidget(btn_add_room)
        
        # 管理按钮
        btn_manage_rooms = QPushButton("📋 管理")
        btn_manage_rooms.setToolTip("管理历史记录")
        btn_manage_rooms.clicked.connect(self._manage_live_rooms)
        url_select_layout.addWidget(btn_manage_rooms)
        
        url_group_layout.addLayout(url_select_layout)
        
        # 加载历史记录
        self._load_live_rooms()
        
        url_group.setLayout(url_group_layout)
        layout.addWidget(url_group)
        
        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _load_live_rooms(self):
        """加载直播间历史记录到下拉框"""
        try:
            from live_room_manager import get_all_live_rooms
            rooms = get_all_live_rooms()
            self.url_combo.clear()
            self.url_combo.addItem("-- 选择历史记录 --", "")
            for room in rooms:
                display_text = f"{room.get('name', '未命名')} - {room.get('url', '')[:50]}"
                self.url_combo.addItem(display_text, room.get('url', ''))
        except Exception as e:
            import traceback
            error_msg = f"[异常] 加载直播间历史记录失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
            print(error_msg)
            print(traceback.format_exc())
            sys.stdout.flush()
    
    def _on_url_selected(self, text):
        """当选择历史记录时，自动填充地址"""
        if self.url_combo.currentData():
            self.url_input.setText(self.url_combo.currentData())
    
    def _add_live_room(self):
        """添加当前地址到历史记录"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请先输入直播间地址！")
            return
        
        # 弹出对话框输入直播间名称
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self, 
            "添加直播间记录", 
            "请输入直播间名称:",
            text=url.split('/')[-1] if '/' in url else "直播间"
        )
        
        if ok and name:
            try:
                from live_room_manager import add_live_room
                add_live_room(name.strip(), url)
                self._load_live_rooms()  # 重新加载
                QMessageBox.information(self, "成功", "直播间已添加到历史记录！")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"添加失败: {e}")
    
    def _manage_live_rooms(self):
        """管理直播间历史记录"""
        try:
            from live_room_manager import get_all_live_rooms, remove_live_room
            rooms = get_all_live_rooms()
            
            if not rooms:
                QMessageBox.information(self, "提示", "暂无历史记录！")
                return
            
            # 创建管理对话框
            manage_dialog = QDialog(self)
            manage_dialog.setWindowTitle("管理直播间历史记录")
            manage_dialog.setMinimumSize(600, 400)
            manage_layout = QVBoxLayout(manage_dialog)
            
            # 说明
            info_label = QLabel("双击列表项可删除该记录")
            info_label.setStyleSheet("color: #666; font-size: 11px; padding: 5px;")
            manage_layout.addWidget(info_label)
            
            # 列表
            room_list = QListWidget()
            for room in rooms:
                item_text = f"{room.get('name', '未命名')}\n{room.get('url', '')}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, room.get('url', ''))
                room_list.addItem(item)
            
            # 双击删除
            def on_item_double_clicked(item):
                url = item.data(Qt.ItemDataRole.UserRole)
                reply = QMessageBox.question(
                    self,
                    "确认删除",
                    f"确定要删除该直播间记录吗？\n{item.text()}",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    remove_live_room(url)
                    room_list.takeItem(room_list.row(item))
                    self._load_live_rooms()  # 重新加载下拉框
            
            room_list.itemDoubleClicked.connect(on_item_double_clicked)
            manage_layout.addWidget(room_list)
            
            # 按钮
            btn_close = QPushButton("关闭")
            btn_close.clicked.connect(manage_dialog.accept)
            manage_layout.addWidget(btn_close)
            
            manage_dialog.exec()
        except Exception as e:
            import traceback
            error_msg = f"[异常] 管理直播间历史记录失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
            print(error_msg)
            print(traceback.format_exc())
            sys.stdout.flush()
            QMessageBox.warning(self, "错误", f"管理失败: {e}")
        
    def get_data(self):
        """获取输入的账户数据"""
        return {
            'name': self.name_input.text().strip(),
            'nickname': self.nickname_input.text().strip(),
            'url': self.url_input.text().strip()
        }


class AIReplyConfigDialog(QDialog):
    """AI回复配置对话框"""
    
    def __init__(self, parent=None, cfg=None):
        super().__init__(parent)
        self.cfg = cfg or {}
        self.setWindowTitle("🤖 AI智能回复配置")
        self.setMinimumSize(700, 600)
        self.resize(750, 700)
        
        # 设置窗口图标
        icon_path = get_icon_path()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # 使用滚动区域包装内容
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(12)
        
        # AI回复开关和授权状态
        enable_layout = QHBoxLayout()
        self.cb_ai_reply = QCheckBox("启用AI智能回复")
        # AI功能默认禁用，只有CDK授权后才能启用
        self.cb_ai_reply.setChecked(self.cfg.get('ai_reply_enabled', False))
        self.cb_ai_reply.setStyleSheet("font-weight: bold; font-size: 13px; color: #4CAF50;")
        self.cb_ai_reply.setToolTip("启用AI智能回复功能，当其他规则都不匹配时，使用AI生成回复\n注意：此功能需要CDK授权才能使用")
        
        # 检查AI功能授权状态
        try:
            from server_client import check_feature_auth
            auth_status = check_feature_auth()
            ai_authorized = auth_status.get('ai_reply', False)
        except Exception:
            ai_authorized = False
        
        # 授权状态标签
        self.auth_label = QLabel()
        if ai_authorized:
            self.auth_label.setText("✓ 已授权")
            self.auth_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.cb_ai_reply.setEnabled(True)
        else:
            self.auth_label.setText("✗ 未授权（需要CDK激活）")
            self.auth_label.setStyleSheet("color: #f44336; font-weight: bold;")
            self.cb_ai_reply.setEnabled(False)
            self.cb_ai_reply.setChecked(False)
            self.cb_ai_reply.setToolTip("AI功能需要CDK授权才能使用，请在CDK管理页面激活AI功能")
        
        enable_layout.addWidget(self.cb_ai_reply)
        enable_layout.addStretch()
        enable_layout.addWidget(self.auth_label)
        content_layout.addLayout(enable_layout)
        
        # API Key配置
        api_key_group = QGroupBox("API配置")
        api_key_layout = QVBoxLayout()
        api_key_layout.setSpacing(8)
        
        api_key_row = QHBoxLayout()
        api_key_row.addWidget(QLabel("API Key:"))
        self.edit_ai_api_key = QLineEdit()
        # 不显示默认API Key，防止泄露
        saved_api_key = self.cfg.get('ai_reply_api_key', '')
        # 如果配置中有保存的API Key，在placeholder中显示提示（不显示完整密钥）
        if saved_api_key and len(saved_api_key) > 8:
            # 显示格式：sk-4...6762（仅用于提示用户已保存，实际输入框为空）
            display_hint = f"{saved_api_key[:4]}...{saved_api_key[-4:]}"
            self.edit_ai_api_key.setPlaceholderText(f"已保存API Key（{display_hint}），留空则保留原值，输入新值则更新")
        else:
            self.edit_ai_api_key.setPlaceholderText("输入DeepSeek API Key（安全起见，不会默认显示）")
        # 不设置默认文本，保持为空，防止API Key泄露
        self.edit_ai_api_key.setText('')
        self.edit_ai_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        api_key_row.addWidget(self.edit_ai_api_key)
        
        btn_toggle_api_key = QPushButton("👁️")
        btn_toggle_api_key.setMaximumWidth(40)
        btn_toggle_api_key.setToolTip("显示/隐藏API Key")
        btn_toggle_api_key.clicked.connect(lambda: self.edit_ai_api_key.setEchoMode(
            QLineEdit.EchoMode.Normal if self.edit_ai_api_key.echoMode() == QLineEdit.EchoMode.Password 
            else QLineEdit.EchoMode.Password
        ))
        api_key_row.addWidget(btn_toggle_api_key)
        api_key_layout.addLayout(api_key_row)
        
        api_key_group.setLayout(api_key_layout)
        content_layout.addWidget(api_key_group)
        
        # 预设角色和对话历史
        role_group = QGroupBox("AI角色设置")
        role_layout = QVBoxLayout()
        role_layout.setSpacing(8)
        
        role_row = QHBoxLayout()
        role_row.addWidget(QLabel("预设角色:"))
        self.ai_role_combo = QComboBox()
        self.ai_role_combo.addItem("自定义提示词", "custom")
        self.ai_role_combo.addItem("服装类直播AI", "clothing")
        saved_role = self.cfg.get('ai_reply_role', 'custom')
        index = self.ai_role_combo.findData(saved_role)
        if index >= 0:
            self.ai_role_combo.setCurrentIndex(index)
        self.ai_role_combo.currentTextChanged.connect(self._on_role_changed)
        role_row.addWidget(self.ai_role_combo)
        role_row.addStretch()
        
        role_row.addWidget(QLabel("对话历史:"))
        self.sp_ai_max_history = QSpinBox()
        self.sp_ai_max_history.setRange(1, 20)
        self.sp_ai_max_history.setValue(self.cfg.get('ai_reply_max_history', 5))
        self.sp_ai_max_history.setSuffix(" 轮")
        self.sp_ai_max_history.setToolTip("AI会记住最近N轮对话，用于上下文理解")
        role_row.addWidget(self.sp_ai_max_history)
        role_layout.addLayout(role_row)
        
        # 服装类AI详细信息
        self.clothing_info_group = QGroupBox("服装类AI详细信息")
        clothing_info_layout = QVBoxLayout()
        clothing_info_layout.setSpacing(8)
        
        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("品类:"))
        self.edit_clothing_category = QLineEdit()
        self.edit_clothing_category.setText(self.cfg.get('ai_reply_clothing_category', ''))
        self.edit_clothing_category.setPlaceholderText("例如：女装、男装、童装、运动装等")
        category_layout.addWidget(self.edit_clothing_category)
        clothing_info_layout.addLayout(category_layout)
        
        host_info_layout = QHBoxLayout()
        host_info_layout.addWidget(QLabel("主播身高(cm):"))
        self.sp_clothing_height = QSpinBox()
        self.sp_clothing_height.setRange(100, 250)
        self.sp_clothing_height.setValue(self.cfg.get('ai_reply_clothing_height', 165))
        self.sp_clothing_height.setSuffix(" cm")
        host_info_layout.addWidget(self.sp_clothing_height)
        
        host_info_layout.addWidget(QLabel("主播体重(kg):"))
        self.sp_clothing_weight = QSpinBox()
        self.sp_clothing_weight.setRange(30, 200)
        self.sp_clothing_weight.setValue(self.cfg.get('ai_reply_clothing_weight', 55))
        self.sp_clothing_weight.setSuffix(" kg")
        host_info_layout.addWidget(self.sp_clothing_weight)
        clothing_info_layout.addLayout(host_info_layout)
        
        self.clothing_info_group.setLayout(clothing_info_layout)
        self.clothing_info_group.setVisible(saved_role == "clothing")
        role_layout.addWidget(self.clothing_info_group)
        
        # 自定义提示词
        self.custom_prompt_group = QGroupBox("自定义提示词")
        custom_prompt_layout = QVBoxLayout()
        self.edit_ai_system_prompt = QTextEdit()
        default_prompt = self.cfg.get('ai_reply_system_prompt', '')
        if not default_prompt:
            default_prompt = (
                "你是一个抖音直播间的智能助手，负责回复观众的弹幕。"
                "回复要简洁、友好、有趣，通常不超过20字。"
                "如果观众问问题，要给出有用的回答；如果是闲聊，要热情互动。"
                "不要重复相同的内容，要根据上下文灵活回复。"
            )
        self.edit_ai_system_prompt.setPlainText(default_prompt)
        self.edit_ai_system_prompt.setPlaceholderText("输入AI的系统提示词，定义AI的角色和行为...")
        self.edit_ai_system_prompt.setMaximumHeight(100)
        custom_prompt_layout.addWidget(self.edit_ai_system_prompt)
        self.custom_prompt_group.setLayout(custom_prompt_layout)
        self.custom_prompt_group.setVisible(saved_role == "custom")
        role_layout.addWidget(self.custom_prompt_group)
        
        role_group.setLayout(role_layout)
        content_layout.addWidget(role_group)
        
        # 弹幕过滤设置
        filter_group = QGroupBox("🔍 弹幕过滤设置（节省Token）")
        filter_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #FF9800;
                background-color: rgba(255, 152, 0, 0.05);
            }
        """)
        filter_layout = QVBoxLayout()
        filter_layout.setSpacing(8)
        
        min_length_layout = QHBoxLayout()
        min_length_layout.addWidget(QLabel("最小长度:"))
        self.sp_ai_filter_min_length = QSpinBox()
        self.sp_ai_filter_min_length.setRange(1, 20)
        self.sp_ai_filter_min_length.setValue(self.cfg.get('ai_reply_filter_min_length', 2))
        self.sp_ai_filter_min_length.setSuffix(" 字符")
        self.sp_ai_filter_min_length.setToolTip("弹幕至少需要多少个字符才会进行AI回复")
        min_length_layout.addWidget(self.sp_ai_filter_min_length)
        min_length_layout.addStretch()
        filter_layout.addLayout(min_length_layout)
        
        filter_options_layout = QHBoxLayout()
        filter_left_layout = QVBoxLayout()
        filter_right_layout = QVBoxLayout()
        
        self.cb_filter_emoji = QCheckBox("过滤纯表情符号")
        self.cb_filter_emoji.setChecked(self.cfg.get('ai_reply_filter_emoji_only', True))
        self.cb_filter_emoji.setToolTip("过滤掉只包含表情符号的弹幕")
        filter_left_layout.addWidget(self.cb_filter_emoji)
        
        self.cb_filter_numbers = QCheckBox("过滤纯数字")
        self.cb_filter_numbers.setChecked(self.cfg.get('ai_reply_filter_numbers_only', True))
        self.cb_filter_numbers.setToolTip("过滤掉只包含数字的弹幕（如'666'、'123'）")
        filter_left_layout.addWidget(self.cb_filter_numbers)
        
        self.cb_filter_punctuation = QCheckBox("过滤纯标点符号")
        self.cb_filter_punctuation.setChecked(self.cfg.get('ai_reply_filter_punctuation_only', True))
        self.cb_filter_punctuation.setToolTip("过滤掉只包含标点符号的弹幕")
        filter_right_layout.addWidget(self.cb_filter_punctuation)
        
        self.cb_filter_repeated = QCheckBox("过滤重复字符")
        self.cb_filter_repeated.setChecked(self.cfg.get('ai_reply_filter_repeated_chars', True))
        self.cb_filter_repeated.setToolTip("过滤掉重复字符过多的弹幕（如'哈哈哈'、'666666'）")
        filter_right_layout.addWidget(self.cb_filter_repeated)
        
        filter_options_layout.addLayout(filter_left_layout)
        filter_options_layout.addLayout(filter_right_layout)
        filter_layout.addLayout(filter_options_layout)
        
        keyword_layout = QVBoxLayout()
        keyword_header_layout = QHBoxLayout()
        self.cb_require_keywords = QCheckBox("仅回复包含关键词的弹幕")
        self.cb_require_keywords.setChecked(self.cfg.get('ai_reply_require_keywords', False))
        self.cb_require_keywords.setToolTip("启用后，只有包含下方关键词的弹幕才会进行AI回复（白名单模式）")
        keyword_header_layout.addWidget(self.cb_require_keywords)
        keyword_header_layout.addStretch()
        keyword_layout.addLayout(keyword_header_layout)
        
        keyword_input_layout = QHBoxLayout()
        keyword_input_layout.addWidget(QLabel("关键词:"))
        self.edit_ai_filter_keywords = QLineEdit()
        saved_keywords = self.cfg.get('ai_reply_filter_keywords', [])
        if isinstance(saved_keywords, list):
            keywords_text = '|'.join(saved_keywords)
        else:
            keywords_text = str(saved_keywords) if saved_keywords else ''
        self.edit_ai_filter_keywords.setText(keywords_text)
        self.edit_ai_filter_keywords.setPlaceholderText("多个关键词用 | 分隔，例如：尺码|颜色|材质")
        self.edit_ai_filter_keywords.setToolTip("设置关键词后，只有包含这些关键词的弹幕才会进行AI回复")
        keyword_input_layout.addWidget(self.edit_ai_filter_keywords)
        keyword_layout.addLayout(keyword_input_layout)
        filter_layout.addLayout(keyword_layout)
        
        filter_group.setLayout(filter_layout)
        content_layout.addWidget(filter_group)
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _on_role_changed(self, text):
        """角色切换处理"""
        role = self.ai_role_combo.currentData()
        if role == "clothing":
            self.clothing_info_group.setVisible(True)
            self.custom_prompt_group.setVisible(False)
        else:
            self.clothing_info_group.setVisible(False)
            self.custom_prompt_group.setVisible(True)
    
    def get_config(self):
        """获取配置"""
        keywords_text = self.edit_ai_filter_keywords.text().strip()
        if keywords_text:
            keywords_list = [k.strip() for k in keywords_text.split('|') if k.strip()]
        else:
            keywords_list = []
        
        # 获取API Key：如果用户输入了新的，使用新的；否则保留之前保存的
        new_api_key = self.edit_ai_api_key.text().strip()
        if new_api_key:
            # 用户输入了新的API Key，使用新的
            api_key = new_api_key
        else:
            # 用户没有输入新的API Key，保留之前保存的（如果有）
            api_key = self.cfg.get('ai_reply_api_key', '')
        
        return {
            'ai_reply_enabled': self.cb_ai_reply.isChecked(),
            'ai_reply_api_key': api_key,
            'ai_reply_role': self.ai_role_combo.currentData(),
            'ai_reply_system_prompt': self.edit_ai_system_prompt.toPlainText().strip(),
            'ai_reply_max_history': self.sp_ai_max_history.value(),
            'ai_reply_clothing_category': self.edit_clothing_category.text().strip(),
            'ai_reply_clothing_height': self.sp_clothing_height.value(),
            'ai_reply_clothing_weight': self.sp_clothing_weight.value(),
            'ai_reply_filter_min_length': self.sp_ai_filter_min_length.value(),
            'ai_reply_filter_emoji_only': self.cb_filter_emoji.isChecked(),
            'ai_reply_filter_numbers_only': self.cb_filter_numbers.isChecked(),
            'ai_reply_filter_punctuation_only': self.cb_filter_punctuation.isChecked(),
            'ai_reply_filter_repeated_chars': self.cb_filter_repeated.isChecked(),
            'ai_reply_filter_keywords': keywords_list,
            'ai_reply_require_keywords': self.cb_require_keywords.isChecked(),
        }


class ControlPanel(QWidget):
    """主控制面板"""
    
    def __init__(self):
        super().__init__()
        try:
            print("    [初始化] 加载配置...", end=" ")
            sys.stdout.flush()
            self.cfg = load_cfg()
            print("✓")
            sys.stdout.flush()
            
            print("    [初始化] 创建账户窗口字典...", end=" ")
            sys.stdout.flush()
            self.account_windows = {}  # 存储每个账户的窗口实例
            self.danmu_overlay = None  # 弹幕悬浮窗口
            print("✓")
            sys.stdout.flush()
            
            # 初始化统计数据结构
            self.viewer_count = "0"  # 当前在线人数
            self.gift_total_count = 0  # 礼物总数
            print("    [初始化] 初始化统计数据...", end=" ")
            sys.stdout.flush()
            print("✓")
            sys.stdout.flush()
            
            print("    [初始化] 创建配置信号...", end=" ")
            sys.stdout.flush()
            self.config_signal = ConfigUpdateSignal()
            print("✓")
            sys.stdout.flush()
            
            print("    [初始化] 设置窗口属性...", end=" ")
            sys.stdout.flush()
            self.setWindowTitle("抖音直播中控控场工具V3.0版本 - 主控制面板 | 开发者: 故里何日还 | 仅供学习交流，禁止倒卖")
            # 增加默认窗口大小，确保所有内容都能完整显示
            self.resize(1400, 900)
            # 设置合理的窗口尺寸限制，防止拖动时尺寸异常变化
            self.setMinimumSize(1200, 750)  # 增加最小尺寸，确保内容完整显示
            # 移除最大尺寸限制，允许用户自由调整窗口大小
            # self.setMaximumSize(1920, 1080)  # 注释掉，允许窗口更大
            # 设置窗口图标
            icon_path = get_icon_path()
            if icon_path:
                self.setWindowIcon(QIcon(icon_path))
            print("✓")
            sys.stdout.flush()
            
            print("    [初始化] 初始化UI...", end=" ")
            sys.stdout.flush()
            self._init_ui()
            print("✓")
            sys.stdout.flush()
            
            # 连接配置更新信号，用于接收来自main_window的配置更新
            self.config_signal.config_updated.connect(self._on_config_updated_from_window)
            
            # 初始化功能授权状态（默认全部未授权，只有自动回复可用）
            print("    [初始化] 检查功能授权...", end=" ")
            sys.stdout.flush()
            self.feature_auth = {
                "specific_reply": False,
                "advanced_reply": False,
                "warmup": False,
                "command": False
            }
            # 延迟检查授权，确保UI已完全初始化
            QTimer.singleShot(1000, self._check_feature_auth)  # 1秒后检查授权
            
            # 启动功能授权检查定时器（每5分钟检查一次）
            self.feature_auth_timer = QTimer()
            self.feature_auth_timer.timeout.connect(self._check_feature_auth)
            self.feature_auth_timer.start(5 * 60 * 1000)  # 5分钟
            
            print("✓")
            sys.stdout.flush()
            
            # 启动封禁状态检查定时器（每15分钟检查一次）
            print("    [初始化] 启动封禁状态检查定时器...", end=" ")
            sys.stdout.flush()
            self.ban_check_timer = QTimer()
            self.ban_check_timer.timeout.connect(self._check_ban_status)
            self.ban_check_timer.start(15 * 60 * 1000)  # 15分钟 = 900000毫秒
            # 立即执行一次检查
            QTimer.singleShot(5000, self._check_ban_status)  # 5秒后执行第一次检查
            print("✓")
            sys.stdout.flush()
            
            print("    [初始化] 加载账户列表...", end=" ")
            sys.stdout.flush()
            self._load_accounts()
            print("✓")
            sys.stdout.flush()
            
            # 确保窗口大小足够显示所有内容
            # 延迟调整窗口大小，确保UI已完全初始化
            QTimer.singleShot(100, self._ensure_window_fits_content)
            
            print("    [初始化] 初始化队列配置...", end=" ")
            sys.stdout.flush()
            self._init_queue_config()
            print("✓")
            sys.stdout.flush()
            
            print("    [初始化] 完成！")
            sys.stdout.flush()
            
            # 延迟连接日志信号，在窗口显示后连接（避免阻塞初始化）
            # 使用QTimer延迟执行，确保窗口已经完全初始化
            QTimer.singleShot(200, self._connect_logger_signal)
            
            # 如果配置中启用了弹幕姬，自动启动
            if self.cfg.get('danmu_display_enabled', False):
                QTimer.singleShot(500, self._start_danmu_display)
            
            # 初始化音频管理器
            print("    [初始化] 初始化音频管理器...", end=" ")
            sys.stdout.flush()
            try:
                from audio_player import AudioManager, TTSManager
                # 初始化音频管理器
                self.audio_manager = AudioManager(self.cfg, parent=self)
                self.audio_manager.set_enabled(self.cfg.get('audio_enabled', False))
                
                # 初始化TTS管理器（独立管理TTS规则）
                self.tts_manager = TTSManager(self.cfg, parent=self)
                self.tts_manager.set_enabled(self.cfg.get('tts_enabled', False))
                # 设置队列超时时间
                if self.tts_manager.tts_engine:
                    queue_timeout = self.cfg.get('tts_queue_timeout', 10.0)
                    self.tts_manager.set_queue_timeout(queue_timeout)
                # 设置播报所有弹幕选项
                self.tts_manager.set_speak_all_danmu(self.cfg.get('tts_speak_all_danmu', False))
                
                # 连接弹幕信号到音频管理器和TTS管理器
                from danmu_monitor import global_signal
                global_signal.received.connect(self._on_danmu_for_audio)
                global_signal.received.connect(self._on_danmu_for_tts)
                
                # 启动定时检查线程（仅用于音频定时播放）
                self.audio_check_timer = QTimer()
                self.audio_check_timer.timeout.connect(self._check_audio_timers)
                self.audio_check_timer.start(1000)  # 每秒检查一次
                
                # 管理器初始化后，刷新规则列表（确保UI显示最新规则）
                QTimer.singleShot(100, self._refresh_audio_rules)
                QTimer.singleShot(100, self._refresh_tts_rules)
                QTimer.singleShot(100, self._refresh_tts_block_keywords)
                
                print("✓")
            except Exception as e:
                print(f"✗ ({e})")
                traceback.print_exc()
                self.audio_manager = None
                self.tts_manager = None
            sys.stdout.flush()
            
        except Exception as e:
            print(f"\n❌ 初始化控制面板时出错: {e}")
            traceback.print_exc()
            raise
        
    def _init_ui(self):
        """初始化用户界面"""
        print("      [UI] 创建布局...", end=" ")
        sys.stdout.flush()
        layout = QVBoxLayout(self)
        print("✓")
        sys.stdout.flush()
        
        # 标题
        print("      [UI] 创建标题...", end=" ")
        sys.stdout.flush()
        title_layout = QHBoxLayout()
        title = QLabel("🎯 主控制面板 - 统一管理所有小号")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        title_layout.addWidget(title)
        title_layout.addStretch()
        layout.addLayout(title_layout)
        print("✓")
        sys.stdout.flush()
        
        # 主标签页
        print("      [UI] 创建标签页容器...", end=" ")
        sys.stdout.flush()
        tabs = QTabWidget()
        print("✓")
        sys.stdout.flush()
        
        # 账户管理标签页
        print("      [UI] 创建账户管理标签页...", end=" ")
        sys.stdout.flush()
        account_tab = self._create_account_tab()
        tabs.addTab(account_tab, "📋 小号管理")
        print("✓")
        sys.stdout.flush()
        
        # 统一配置标签页
        print("      [UI] 创建统一配置标签页...", end=" ")
        sys.stdout.flush()
        config_tab = self._create_config_tab()
        tabs.addTab(config_tab, "⚙️ 统一配置")
        print("✓")
        sys.stdout.flush()
        
        # 全局日志标签页
        print("      [UI] 创建全局日志标签页...", end=" ")
        sys.stdout.flush()
        log_tab = self._create_log_tab()
        tabs.addTab(log_tab, "📊 运行日志")
        print("✓")
        sys.stdout.flush()
        
        # 统计报表标签页
        print("      [UI] 创建统计报表标签页...", end=" ")
        sys.stdout.flush()
        stats_tab = self._create_statistics_tab()
        tabs.addTab(stats_tab, "📈 统计报表")
        print("✓")
        sys.stdout.flush()
        
        # 音频播放标签页
        print("      [UI] 创建音频播放标签页...", end=" ")
        sys.stdout.flush()
        audio_tab = self._create_audio_tab()
        tabs.addTab(audio_tab, "🔊 音频播放")
        print("✓")
        sys.stdout.flush()
        
        # TTS文字转语音标签页
        print("      [UI] 创建TTS文字转语音标签页...", end=" ")
        sys.stdout.flush()
        tts_tab = self._create_tts_tab()
        tabs.addTab(tts_tab, "🗣️ TTS播报")
        print("✓")
        sys.stdout.flush()
        
        # 关于标签页
        print("      [UI] 创建关于标签页...", end=" ")
        sys.stdout.flush()
        about_tab = self._create_about_tab()
        tabs.addTab(about_tab, "ℹ️ 关于")
        print("✓")
        sys.stdout.flush()
        
        print("      [UI] 添加标签页到布局...", end=" ")
        sys.stdout.flush()
        layout.addWidget(tabs)
        print("✓")
        sys.stdout.flush()
        
    def _create_account_tab(self):
        """创建账户管理标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 账户列表标题
        header = QHBoxLayout()
        header.addWidget(QLabel("小号列表:"))
        header.addStretch()
        
        btn_add = QPushButton("➕ 添加小号")
        btn_add.clicked.connect(self._add_account)
        header.addWidget(btn_add)
        
        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.clicked.connect(self._load_accounts)
        header.addWidget(btn_refresh)
        
        layout.addLayout(header)
        
        # 账户列表
        self.account_list = QListWidget()
        self.account_list.itemDoubleClicked.connect(self._edit_account)
        layout.addWidget(self.account_list)
        
        # 账户操作按钮
        btn_layout = QHBoxLayout()
        
        btn_edit = QPushButton("✏️ 编辑")
        btn_edit.clicked.connect(self._edit_account)
        btn_layout.addWidget(btn_edit)
        
        btn_delete = QPushButton("🗑️ 删除")
        btn_delete.clicked.connect(self._delete_account)
        btn_layout.addWidget(btn_delete)
        
        btn_start = QPushButton("▶️ 启动")
        btn_start.clicked.connect(self._start_account)
        btn_layout.addWidget(btn_start)
        
        btn_stop = QPushButton("⏹️ 停止")
        btn_stop.clicked.connect(self._stop_account)
        btn_layout.addWidget(btn_stop)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        return widget
        
    def _create_config_tab(self):
        """创建统一配置标签页"""
        # 使用滚动区域包装整个内容，防止窗口强制拉伸
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 主内容widget
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)  # 减少边距，让布局更紧凑
        layout.setSpacing(6)  # 进一步减少间距，让布局更紧凑
        
        # 基础设置和防冲突设置合并组
        basic_queue_group = QGroupBox("基础设置与防冲突")
        basic_queue_layout = QHBoxLayout()  # 主布局：左右分栏
        basic_queue_layout.setSpacing(15)
        
        # 左侧：基础设置和防冲突配置
        left_config_layout = QVBoxLayout()
        left_config_layout.setSpacing(8)
        
        # 基础设置行（回复间隔和随机抖动）
        basic_settings_layout = QHBoxLayout()
        basic_settings_layout.addWidget(QLabel("回复间隔(秒):"))
        self.sp_interval = QSpinBox()
        self.sp_interval.setRange(2, 30)
        reply_interval = int(self.cfg.get('reply_interval', 4))
        self.sp_interval.setValue(reply_interval)
        self.sp_interval.valueChanged.connect(self._update_global_config)
        basic_settings_layout.addWidget(self.sp_interval)
        
        basic_settings_layout.addWidget(QLabel("随机抖动(秒):"))
        self.sp_jitter = QDoubleSpinBox()
        self.sp_jitter.setRange(0, 10)
        self.sp_jitter.setValue(self.cfg.get('random_jitter', 2.0))
        self.sp_jitter.valueChanged.connect(self._update_global_config)
        basic_settings_layout.addWidget(self.sp_jitter)
        basic_settings_layout.addStretch()
        left_config_layout.addLayout(basic_settings_layout)
        
        # 分隔线
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.HLine)
        separator1.setFrameShadow(QFrame.Shadow.Sunken)
        separator1.setStyleSheet("color: #555; margin: 5px 0;")
        left_config_layout.addWidget(separator1)
        
        # 防冲突设置
        queue_left_layout = QVBoxLayout()
        queue_left_layout.setSpacing(8)  # 减少间距
        
        # 多小号回复模式选择（二选一单选按钮，横向排列以节省空间）
        reply_mode_layout = QHBoxLayout()
        reply_mode_layout.setSpacing(10)
        reply_mode_label = QLabel("回复模式:")
        reply_mode_label.setStyleSheet("font-size: 11px;")
        reply_mode_layout.addWidget(reply_mode_label)
        
        # 创建单选按钮组
        self.reply_mode_group = QButtonGroup(self)
        
        # 单回复模式单选按钮
        self.rb_single_reply = QRadioButton("单回复")
        self.rb_single_reply.setStyleSheet("font-size: 11px; padding: 3px 6px;")
        self.rb_single_reply.setToolTip("同一条弹幕只由一个小号回复，根据分配模式决定由哪个小号回复")
        reply_mode_layout.addWidget(self.rb_single_reply)
        
        # 并行回复模式单选按钮
        self.rb_multiple_reply = QRadioButton("并行回复")
        self.rb_multiple_reply.setStyleSheet("font-size: 11px; padding: 3px 6px;")
        self.rb_multiple_reply.setToolTip("所有小号都可以回复同一条弹幕，实现高频率回复")
        reply_mode_layout.addWidget(self.rb_multiple_reply)
        
        reply_mode_layout.addStretch()
        
        # 将单选按钮添加到按钮组（确保互斥）
        self.reply_mode_group.addButton(self.rb_single_reply, 0)  # 0 = 单回复模式
        self.reply_mode_group.addButton(self.rb_multiple_reply, 1)  # 1 = 并行回复模式
        
        # 根据配置设置默认选中状态
        allow_multiple = self.cfg.get('allow_multiple_reply', False)
        if allow_multiple:
            self.rb_multiple_reply.setChecked(True)
        else:
            self.rb_single_reply.setChecked(True)
        
        # 连接信号
        self.rb_single_reply.toggled.connect(self._update_global_config)
        self.rb_multiple_reply.toggled.connect(self._update_global_config)
        
        queue_left_layout.addLayout(reply_mode_layout)
        
        # 分配模式（仅在单回复模式下有效，改为单选按钮横向排布）
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(10)
        mode_label = QLabel("分配模式:")
        mode_label.setStyleSheet("font-size: 11px;")
        mode_layout.addWidget(mode_label)
        
        # 创建单选按钮组
        self.queue_mode_group = QButtonGroup(self)
        
        mode_radio_layout = QHBoxLayout()
        mode_radio_layout.setSpacing(8)  # 单选按钮之间的间距
        
        # 模式映射（配置值到UI显示）
        mode_map = {"轮询": "轮流", "优先级": "优先", "随机": "随机", "第一个可用": "先到先得"}
        cfg_mode = self.cfg.get('queue_mode', '轮询')
        current_mode_ui = mode_map.get(cfg_mode, "轮流")
        
        # 创建四个单选按钮
        mode_options = ["轮流", "优先", "随机", "先到先得"]
        self.queue_mode_radios = {}
        for idx, mode_text in enumerate(mode_options):
            radio = QRadioButton(mode_text)
            radio.setStyleSheet("font-size: 11px; padding: 3px 6px;")
            if mode_text == current_mode_ui:
                radio.setChecked(True)
            radio.toggled.connect(self._update_global_config)
            self.queue_mode_group.addButton(radio, idx)
            self.queue_mode_radios[mode_text] = radio
            mode_radio_layout.addWidget(radio)
        
        mode_radio_layout.addStretch()
        mode_layout.addLayout(mode_radio_layout)
        
        # 根据回复模式启用/禁用分配模式
        for radio in self.queue_mode_radios.values():
            radio.setEnabled(not allow_multiple)
        
        queue_left_layout.addLayout(mode_layout)
        
        # 当回复模式改变时，更新分配模式的启用状态
        def on_reply_mode_changed():
            is_single_mode = self.rb_single_reply.isChecked()
            for radio in self.queue_mode_radios.values():
                radio.setEnabled(is_single_mode)
            self._update_global_config()
        self.rb_single_reply.toggled.connect(on_reply_mode_changed)
        self.rb_multiple_reply.toggled.connect(on_reply_mode_changed)
        
        # 时间窗口和锁超时（优化布局和字体）
        queue_params_layout = QHBoxLayout()
        queue_params_layout.setSpacing(10)
        
        # 识别时间窗口
        time_window_label = QLabel("时间窗口(秒):")
        time_window_label.setStyleSheet("font-size: 11px;")
        queue_params_layout.addWidget(time_window_label)
        self.sp_queue_window = QDoubleSpinBox()
        self.sp_queue_window.setRange(1.0, 60.0)
        self.sp_queue_window.setSingleStep(0.5)
        self.sp_queue_window.setValue(self.cfg.get('queue_time_window', 5.0))
        self.sp_queue_window.setStyleSheet("font-size: 11px; padding: 2px;")
        self.sp_queue_window.setToolTip("相同弹幕在此时间窗口内被视为同一条消息")
        self.sp_queue_window.valueChanged.connect(self._update_global_config)
        queue_params_layout.addWidget(self.sp_queue_window)
        
        # 锁定超时
        timeout_label = QLabel("锁定超时(秒):")
        timeout_label.setStyleSheet("font-size: 11px;")
        queue_params_layout.addWidget(timeout_label)
        self.sp_queue_timeout = QDoubleSpinBox()
        self.sp_queue_timeout.setRange(5.0, 300.0)
        self.sp_queue_timeout.setSingleStep(5.0)
        self.sp_queue_timeout.setValue(self.cfg.get('queue_lock_timeout', 30.0))
        self.sp_queue_timeout.setStyleSheet("font-size: 11px; padding: 2px;")
        self.sp_queue_timeout.setToolTip("锁自动释放的超时时间，防止死锁")
        self.sp_queue_timeout.valueChanged.connect(self._update_global_config)
        queue_params_layout.addWidget(self.sp_queue_timeout)
        
        # 高级选项（同一行）
        self.cb_auto_cleanup = QCheckBox("自动清理过期锁")
        self.cb_auto_cleanup.setStyleSheet("font-size: 11px; padding: 2px;")
        self.cb_auto_cleanup.setChecked(self.cfg.get('auto_cleanup_locks', True))
        self.cb_auto_cleanup.setToolTip("自动清理过期的锁，防止内存泄漏")
        self.cb_auto_cleanup.stateChanged.connect(self._update_global_config)
        queue_params_layout.addWidget(self.cb_auto_cleanup)
        
        queue_params_layout.addStretch()
        queue_left_layout.addLayout(queue_params_layout)
        
        # 将防冲突设置添加到左侧配置布局
        left_config_layout.addLayout(queue_left_layout)
        
        # 左侧配置区域容器
        left_config_widget = QWidget()
        left_config_widget.setLayout(left_config_layout)
        basic_queue_layout.addWidget(left_config_widget, 2)  # 左侧占2份，给右侧更多空间
        
        # 右侧：功能说明（利用空白区域，使用滚动区域确保完整显示）
        queue_right_widget = QWidget()
        queue_right_layout = QVBoxLayout(queue_right_widget)
        queue_right_layout.setSpacing(12)
        queue_right_layout.setContentsMargins(10, 5, 10, 5)
        
        # 添加模式说明文本
        mode_desc_label = QLabel("💡 <b>分配模式说明</b>")
        mode_desc_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #333; margin-bottom: 5px;")
        queue_right_layout.addWidget(mode_desc_label)
        
        mode_desc_content = QLabel(
            "• <b>轮流</b>：按小号顺序轮流回复，负载均衡\n"
            "• <b>优先</b>：按账户优先级分配，优先级高的优先回复\n"
            "• <b>随机</b>：随机选择账户回复\n"
            "• <b>先到先得</b>：最快响应的账户回复"
        )
        mode_desc_content.setStyleSheet("font-size: 11px; color: #555; padding: 12px; line-height: 1.8; background-color: rgba(0,0,0,0.03); border-radius: 5px; border-left: 3px solid #4CAF50;")
        mode_desc_content.setWordWrap(True)
        queue_right_layout.addWidget(mode_desc_content)
        
        # 队列说明（优化字体和间距，确保可见）
        queue_desc_title = QLabel("📖 <b>功能说明</b>")
        queue_desc_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #333; margin-top: 10px; margin-bottom: 5px;")
        queue_right_layout.addWidget(queue_desc_title)
        
        queue_desc = QLabel(
            "• <b>单回复模式</b>：同一条弹幕只会被一个小号回复，避免重复。根据分配模式决定由哪个小号回复\n\n"
            "• <b>并行回复模式</b>：所有小号都可以回复同一条弹幕，实现高频率回复\n\n"
            "• <b>识别时间窗口</b>：相同弹幕在此时间窗口内被视为同一条消息\n\n"
            "• <b>锁定超时</b>：锁会在超时后自动释放，防止死锁"
        )
        queue_desc.setWordWrap(True)
        queue_desc.setStyleSheet("color: #555; font-size: 11px; padding: 12px; line-height: 1.8; background-color: rgba(0,0,0,0.02); border-radius: 5px; border-left: 3px solid #2196F3;")
        queue_right_layout.addWidget(queue_desc)
        
        queue_right_layout.addStretch()  # 添加弹性空间
        
        # 将右侧内容放入滚动区域（确保内容完整显示）
        queue_right_scroll = QScrollArea()
        queue_right_scroll.setWidget(queue_right_widget)
        queue_right_scroll.setWidgetResizable(True)
        queue_right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        # 设置合理的宽度范围，防止过度拉伸
        queue_right_scroll.setMinimumWidth(220)  # 最小宽度
        queue_right_scroll.setMaximumWidth(400)  # 最大宽度，防止占用过多空间
        queue_right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        queue_right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        basic_queue_layout.addWidget(queue_right_scroll, 1)  # 右侧说明区域占1份
        
        basic_queue_group.setLayout(basic_queue_layout)
        layout.addWidget(basic_queue_group)
        
        # 功能开关组（左右分栏布局）
        switch_group = QGroupBox("功能开关")
        switch_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #666;
                border-radius: 5px;
                margin-top: 8px;
                padding-top: 12px;
            }
        """)
        switch_main_layout = QHBoxLayout()  # 主布局：左右分栏
        switch_main_layout.setSpacing(12)  # 减少间距
        
        # 左侧：功能开关
        switch_left_layout = QVBoxLayout()
        switch_left_layout.setSpacing(6)  # 减少间距
        
        # 第一行：自动回复和@回复
        switch_row1 = QHBoxLayout()
        switch_row1.setSpacing(8)  # 减少间距
        self.cb_reply = QCheckBox("自动回复")
        self.cb_reply.setChecked(self.cfg.get('auto_reply_enabled', False))
        self.cb_reply.stateChanged.connect(self._update_global_config)
        switch_row1.addWidget(self.cb_reply)
        
        self.cb_specific = QCheckBox("@回复")
        self.cb_specific.setChecked(False)  # 默认关闭，需要授权
        self.cb_specific.setEnabled(False)  # 默认禁用，等待授权检查
        self.cb_specific.setStyleSheet("color: #888;")  # 灰色
        self.cb_specific.setToolTip("需要服务端授权才能使用")
        self.cb_specific.stateChanged.connect(self._update_global_config)
        switch_row1.addWidget(self.cb_specific)
        
        # 高级回复模式开关（带提示）
        self.cb_advanced = QCheckBox("高级回复模式 (正则表达式)")
        self.cb_advanced.setChecked(False)  # 默认关闭，需要授权
        self.cb_advanced.setEnabled(False)  # 默认禁用，等待授权检查
        self.cb_advanced.setStyleSheet("color: #888;")  # 灰色
        self.cb_advanced.setToolTip("⚠️ 需要服务端授权才能使用\n"
                                   "使用正则表达式匹配同义弹幕，需要了解正则表达式语法\n"
                                   "• 示例：(怎么|如何|怎样).*(买|下单)\n"
                                   "• 建议：先在规则配置中测试正则表达式后再启用")
        self.cb_advanced.stateChanged.connect(self._update_global_config)
        switch_row1.addWidget(self.cb_advanced)
        switch_row1.addStretch()
        switch_left_layout.addLayout(switch_row1)
        
        # 第二行：自动暖场和隐藏浏览器
        switch_row2 = QHBoxLayout()
        switch_row2.setSpacing(8)  # 减少间距
        self.cb_warmup = QCheckBox("自动暖场")
        self.cb_warmup.setChecked(False)  # 默认关闭，需要授权
        self.cb_warmup.setEnabled(False)  # 默认禁用，等待授权检查
        self.cb_warmup.setStyleSheet("color: #888;")  # 灰色
        self.cb_warmup.setToolTip("需要服务端授权才能使用")
        self.cb_warmup.stateChanged.connect(self._update_global_config)
        switch_row2.addWidget(self.cb_warmup)
        
        self.cb_hide = QCheckBox("隐藏浏览器")
        self.cb_hide.setChecked(self.cfg.get('hide_web', False))
        self.cb_hide.stateChanged.connect(self._update_global_config)
        switch_row2.addWidget(self.cb_hide)
        switch_row2.addStretch()
        switch_left_layout.addLayout(switch_row2)
        
        # 第三行：随机空格插入和弹幕姬
        switch_row3 = QHBoxLayout()
        switch_row3.setSpacing(8)  # 减少间距
        self.cb_random_space = QCheckBox("随机空格插入（防风控）")
        self.cb_random_space.setChecked(self.cfg.get('random_space_insert_enabled', False))
        self.cb_random_space.setToolTip("在发送消息时随机插入空格，防止抖音官方风控导致消息发不出去")
        self.cb_random_space.stateChanged.connect(self._update_global_config)
        switch_row3.addWidget(self.cb_random_space)
        
        self.cb_danmu_display = QCheckBox("弹幕姬显示（悬浮弹幕窗口）")
        self.cb_danmu_display.setChecked(self.cfg.get('danmu_display_enabled', False))
        self.cb_danmu_display.setToolTip("启用后，会显示一个悬浮的弹幕显示窗口，可以实时显示直播间弹幕、礼物、在线人数等信息")
        self.cb_danmu_display.stateChanged.connect(self._toggle_danmu_display)
        switch_row3.addWidget(self.cb_danmu_display)
        
        btn_danmu_config = QPushButton("⚙️ 配置")
        btn_danmu_config.setToolTip("配置弹幕悬浮窗口的大小、字体、置顶关键词等")
        btn_danmu_config.clicked.connect(self._open_danmu_config)
        switch_row3.addWidget(btn_danmu_config)
        switch_row3.addStretch()
        switch_left_layout.addLayout(switch_row3)
        
        switch_left_layout.addStretch()
        switch_main_layout.addLayout(switch_left_layout, 1)  # 左侧占1/2
        
        # 右侧：指令控制（添加分隔线）
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("color: #555;")
        switch_main_layout.addWidget(separator)
        
        switch_right_layout = QVBoxLayout()
        
        # 指令功能标题
        command_title = QLabel("📢 指令控制:直播中可以使用弹幕指令进行简单操作")
        command_title.setStyleSheet("font-weight: bold; font-size: 12px; padding: 5px 0;")
        switch_right_layout.addWidget(command_title)
        
        # 启用指令功能
        self.cb_command = QCheckBox("启用指令功能")
        self.cb_command.setChecked(False)  # 默认关闭，需要授权
        self.cb_command.setEnabled(False)  # 默认禁用，等待授权检查
        self.cb_command.setStyleSheet("color: #888;")  # 灰色
        self.cb_command.setToolTip("需要服务端授权才能使用\n允许指定用户通过弹幕发送指令控制小号")
        self.cb_command.stateChanged.connect(self._update_global_config)
        switch_right_layout.addWidget(self.cb_command)
        
        # 静默模式
        self.cb_command_silent = QCheckBox("静默模式（不回复）")
        self.cb_command_silent.setChecked(self.cfg.get('command_silent_mode', False))
        self.cb_command_silent.setToolTip("启用后，指令执行成功时不发送回复消息，只记录日志")
        self.cb_command_silent.stateChanged.connect(self._update_global_config)
        switch_right_layout.addWidget(self.cb_command_silent)
        
        # 指令用户输入
        command_user_layout = QHBoxLayout()
        command_user_layout.addWidget(QLabel("指令用户:"))
        self.edit_command_user = QLineEdit()
        self.edit_command_user.setText(self.cfg.get('command_user', ''))
        self.edit_command_user.setPlaceholderText("输入用户昵称（多个用|分隔）")
        self.edit_command_user.setToolTip("只有这些用户发送的指令才会被执行，多个用户用|分隔")
        self.edit_command_user.textChanged.connect(self._update_global_config)
        command_user_layout.addWidget(self.edit_command_user)
        switch_right_layout.addLayout(command_user_layout)
        
        # 指令说明（简化版）
        command_info = QLabel("💡 弹幕指令说明：点击下方按钮查看完整指令列表")
        command_info.setStyleSheet("font-size: 9px; color: #888; padding: 3px 0;")
        command_info.setWordWrap(True)
        switch_right_layout.addWidget(command_info)
        
        # 指令说明按钮
        btn_command_help = QPushButton("📖 查看指令说明")
        btn_command_help.setStyleSheet("padding: 5px; font-size: 10px;")
        btn_command_help.clicked.connect(self._show_command_help)
        switch_right_layout.addWidget(btn_command_help)
        
        switch_right_layout.addStretch()
        switch_main_layout.addLayout(switch_right_layout, 1)  # 右侧占1/2
        
        switch_group.setLayout(switch_main_layout)
        layout.addWidget(switch_group)
        
        layout.addSpacing(8)  # 减少间距
        
        # 规则配置组（移到更靠上的位置，方便访问）
        rule_group = QGroupBox("📋 规则配置")
        rule_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #666;
                border-radius: 5px;
                margin-top: 8px;
                padding-top: 12px;
            }
        """)
        rule_layout = QVBoxLayout()
        rule_layout.setSpacing(8)
        
        # 小号选择（用于配置小号的独立规则）
        account_select_layout = QHBoxLayout()
        account_select_layout.addWidget(QLabel("为小号配置独立规则（可选）:"))
        self.account_rule_combo = QComboBox()
        self.account_rule_combo.addItem("全局配置（所有小号共用）", None)
        accounts = get_all_accounts()
        for acc in accounts:
            account_name = acc.get('name', '')
            nickname = acc.get('nickname', '')
            display_text = f"{account_name} ({nickname})"
            self.account_rule_combo.addItem(display_text, account_name)
        account_select_layout.addWidget(self.account_rule_combo)
        account_select_layout.addStretch()
        rule_layout.addLayout(account_select_layout)
        
        # 规则配置按钮（使用更紧凑的布局，让按钮更显眼）
        rule_btn_layout = QHBoxLayout()
        rule_btn_layout.setSpacing(8)
        
        btn_keyword = QPushButton("📝 回复规则")
        btn_keyword.setStyleSheet("""
            QPushButton {
                padding: 8px 15px;
                font-size: 11px;
                font-weight: bold;
                background-color: #2196F3;
                color: white;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        btn_keyword.clicked.connect(lambda: self._open_rule_manager_with_account('reply'))
        rule_btn_layout.addWidget(btn_keyword)
        
        btn_specific = QPushButton("🎯 @回复规则")
        btn_specific.setStyleSheet("""
            QPushButton {
                padding: 8px 15px;
                font-size: 11px;
                font-weight: bold;
                background-color: #FF9800;
                color: white;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        btn_specific.clicked.connect(lambda: self._open_rule_manager_with_account('spec'))
        rule_btn_layout.addWidget(btn_specific)
        
        btn_warmup = QPushButton("📢 暖场消息")
        btn_warmup.setStyleSheet("""
            QPushButton {
                padding: 8px 15px;
                font-size: 11px;
                font-weight: bold;
                background-color: #4CAF50;
                color: white;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        btn_warmup.clicked.connect(lambda: self._open_rule_manager_with_account('warm'))
        rule_btn_layout.addWidget(btn_warmup)
        
        btn_advanced = QPushButton("🔧 高级回复模式")
        btn_advanced.setStyleSheet("""
            QPushButton {
                padding: 8px 15px;
                font-size: 11px;
                font-weight: bold;
                background-color: #9c27b0;
                color: white;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #7b1fa2;
            }
        """)
        btn_advanced.clicked.connect(lambda: self._open_rule_manager_with_account('advanced'))
        rule_btn_layout.addWidget(btn_advanced)
        
        rule_btn_layout.addStretch()
        rule_layout.addLayout(rule_btn_layout)
        rule_group.setLayout(rule_layout)
        layout.addWidget(rule_group)
        
        layout.addSpacing(8)  # 减少间距
        
        # AI智能回复配置按钮（打开独立配置窗口）
        ai_reply_btn_layout = QHBoxLayout()
        ai_reply_btn_layout.addStretch()
        btn_ai_config = QPushButton("🤖 AI智能回复配置")
        btn_ai_config.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 20px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        btn_ai_config.setToolTip("打开AI智能回复配置窗口，设置API Key、角色、过滤规则等")
        btn_ai_config.clicked.connect(self._open_ai_reply_config)
        ai_reply_btn_layout.addWidget(btn_ai_config)
        ai_reply_btn_layout.addStretch()
        layout.addLayout(ai_reply_btn_layout)
        
        layout.addSpacing(8)  # 减少间距
        
        # 功能授权提示
        auth_hint = QLabel('💡 提示：需要更多功能（@回复、高级回复模式、暖场、指令控制）请在"关于"界面联系作者获取授权')
        auth_hint.setStyleSheet("color: #FFD700; font-size: 11px; padding: 8px; background-color: rgba(255, 215, 0, 0.1); border-radius: 5px; margin-top: 5px;")
        auth_hint.setWordWrap(True)
        layout.addWidget(auth_hint)
        
        # 移除最后的stretch，让内容自然排列
        # layout.addStretch()  # 注释掉，防止内容被拉伸
        
        # 将内容widget放入滚动区域
        scroll_area.setWidget(widget)
        
        # 返回滚动区域作为标签页内容
        return scroll_area
        
    def _create_log_tab(self):
        """创建全局日志标签页"""
        print("        [日志标签] 创建widget...", end=" ")
        sys.stdout.flush()
        widget = QWidget()
        layout = QVBoxLayout(widget)
        print("✓")
        sys.stdout.flush()
        
        # 工具栏
        print("        [日志标签] 创建工具栏...", end=" ")
        sys.stdout.flush()
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("全局日志 - 查看所有小号的运行状态"))
        toolbar.addStretch()
        
        btn_clear = QPushButton("清空日志")
        btn_clear.clicked.connect(self._clear_log)
        toolbar.addWidget(btn_clear)
        
        btn_clear_stats = QPushButton("清空统计")
        btn_clear_stats.clicked.connect(self._clear_stats)
        toolbar.addWidget(btn_clear_stats)
        
        layout.addLayout(toolbar)
        print("✓")
        sys.stdout.flush()
        
        # 统计显示区域（置顶）
        print("        [日志标签] 创建统计显示区域...", end=" ")
        sys.stdout.flush()
        self.stats_display = QTextEdit()
        self.stats_display.setReadOnly(True)
        self.stats_display.setMaximumHeight(150)
        self.stats_display.setMinimumHeight(100)
        self.stats_display.setStyleSheet(
            "background:#1a1a1a; color:#87CEEB; font-family:'Microsoft YaHei UI'; font-size:11px; border: 1px solid #444;"
        )
        layout.addWidget(self.stats_display)
        self._update_statistics_display()  # 初始化显示
        print("✓")
        sys.stdout.flush()
        
        # 日志显示区域
        print("        [日志标签] 创建日志显示区域...", end=" ")
        sys.stdout.flush()
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet(
            "background:#000000; color:#00FF41; font-family:'Microsoft YaHei UI'; font-size:12px;"
        )
        layout.addWidget(self.log_display)
        print("✓")
        sys.stdout.flush()
        
        # 连接全局日志信号（延迟连接，在窗口显示后连接）
        # 暂时不在这里连接，而是在窗口显示后连接，避免阻塞
        self._logger_connected = False
        
        print("        [日志标签] 完成")
        sys.stdout.flush()
        return widget
    
    def _create_statistics_tab(self):
        """创建统计报表标签页"""
        print("        [统计标签] 创建widget...", end=" ")
        sys.stdout.flush()
        widget = QWidget()
        layout = QVBoxLayout(widget)
        print("✓")
        sys.stdout.flush()
        
        # 工具栏
        print("        [统计标签] 创建工具栏...", end=" ")
        sys.stdout.flush()
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("📈 统计报表 - 查看详细统计数据"))
        toolbar.addStretch()
        
        # 暂停自动刷新复选框
        self.stats_auto_refresh_enabled = True
        self.cb_auto_refresh = QCheckBox("自动刷新")
        self.cb_auto_refresh.setChecked(True)
        self.cb_auto_refresh.setToolTip("启用后每5秒自动刷新统计数据")
        self.cb_auto_refresh.toggled.connect(self._toggle_auto_refresh)
        toolbar.addWidget(self.cb_auto_refresh)
        
        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.clicked.connect(self._refresh_statistics)
        toolbar.addWidget(btn_refresh)
        
        btn_export_csv = QPushButton("📥 导出CSV")
        btn_export_csv.clicked.connect(self._export_statistics_csv)
        toolbar.addWidget(btn_export_csv)
        
        btn_reset = QPushButton("🗑️ 重置统计")
        btn_reset.clicked.connect(self._reset_statistics)
        toolbar.addWidget(btn_reset)
        
        layout.addLayout(toolbar)
        print("✓")
        sys.stdout.flush()
        
        # 创建分割器（左侧统计文本，右侧图表）
        print("        [统计标签] 创建分割器...", end=" ")
        sys.stdout.flush()
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：统计文本显示
        self.stats_text_display = QTextEdit()
        self.stats_text_display.setReadOnly(True)
        self.stats_text_display.setStyleSheet(
            "background:#1a1a1a; color:#E0E0E0; font-family:'Microsoft YaHei UI'; font-size:11px;"
        )
        splitter.addWidget(self.stats_text_display)
        
        # 右侧：图表显示
        self.stats_chart_view = QWebEngineView()
        splitter.addWidget(self.stats_chart_view)
        
        # 设置分割比例（60%文本，40%图表）
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([600, 400])
        
        layout.addWidget(splitter)
        print("✓")
        sys.stdout.flush()
        
        # 先初始化用于跟踪滚动位置的属性（必须在调用_refresh_statistics之前）
        self.stats_scroll_position = 0
        self.stats_is_user_scrolling = False
        
        # 监听滚动事件，检测用户是否在滚动
        self.stats_scroll_timer = QTimer()
        self.stats_scroll_timer.setSingleShot(True)
        self.stats_scroll_timer.timeout.connect(lambda: setattr(self, 'stats_is_user_scrolling', False))
        
        # 连接滚动条信号
        scrollbar = self.stats_text_display.verticalScrollBar()
        scrollbar.valueChanged.connect(self._on_stats_scroll)
        
        # 创建定时器，每5秒刷新一次统计
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self._refresh_statistics)
        self.stats_timer.start(5000)  # 5秒刷新一次
        
        # 初始化统计显示（必须在属性初始化之后）
        self._refresh_statistics()
        
        print("        [统计标签] 完成")
        sys.stdout.flush()
        return widget
    
    def _create_audio_tab(self):
        """创建音频播放标签页"""
        print("        [音频标签] 创建widget...", end=" ")
        sys.stdout.flush()
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # 标题
        title = QLabel("🔊 音频播放管理")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFD700; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # 功能开关
        audio_enabled_group = QGroupBox("功能开关")
        audio_enabled_layout = QHBoxLayout()
        self.cb_audio_enabled = QCheckBox("启用音频播放功能")
        self.cb_audio_enabled.setChecked(self.cfg.get('audio_enabled', False))
        self.cb_audio_enabled.stateChanged.connect(self._toggle_audio_enabled)
        audio_enabled_layout.addWidget(self.cb_audio_enabled)
        audio_enabled_layout.addStretch()
        audio_enabled_group.setLayout(audio_enabled_layout)
        layout.addWidget(audio_enabled_group)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：关键词触发配置
        keyword_widget = QWidget()
        keyword_layout = QVBoxLayout(keyword_widget)
        keyword_layout.setContentsMargins(10, 10, 10, 10)
        
        keyword_title = QLabel("关键词触发音频")
        keyword_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #87CEEB; margin-bottom: 5px;")
        keyword_layout.addWidget(keyword_title)
        
        keyword_desc = QLabel("当弹幕包含指定关键词时，自动播放对应音频")
        keyword_desc.setStyleSheet("color: #888; font-size: 11px; margin-bottom: 10px;")
        keyword_desc.setWordWrap(True)
        keyword_layout.addWidget(keyword_desc)
        
        # 关键词规则列表（使用表格显示）
        keyword_list_group = QGroupBox("关键词规则列表")
        keyword_list_layout = QVBoxLayout()
        
        # 使用表格显示规则（更清晰）
        self.keyword_table = QTableWidget()
        self.keyword_table.setColumnCount(5)
        self.keyword_table.setHorizontalHeaderLabels(["关键词", "匹配模式", "播放模式", "音频文件", "操作"])
        self.keyword_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.keyword_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.keyword_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.keyword_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.keyword_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.keyword_table.setMaximumHeight(250)
        self.keyword_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.keyword_table.setStyleSheet("border: 1px solid #666; gridline-color: #555;")
        keyword_list_layout.addWidget(self.keyword_table)
        
        # 添加/删除/测试按钮
        keyword_btn_layout = QHBoxLayout()
        btn_add_keyword = QPushButton("➕ 添加规则")
        btn_add_keyword.clicked.connect(self._add_keyword_rule)
        btn_remove_keyword = QPushButton("➖ 删除规则")
        btn_remove_keyword.clicked.connect(self._remove_keyword_rule)
        btn_test_keyword = QPushButton("🔊 测试选中")
        btn_test_keyword.clicked.connect(self._test_keyword_audio)
        keyword_btn_layout.addWidget(btn_add_keyword)
        keyword_btn_layout.addWidget(btn_remove_keyword)
        keyword_btn_layout.addWidget(btn_test_keyword)
        keyword_btn_layout.addStretch()
        keyword_list_layout.addLayout(keyword_btn_layout)
        
        keyword_list_group.setLayout(keyword_list_layout)
        keyword_layout.addWidget(keyword_list_group)
        
        keyword_layout.addStretch()
        splitter.addWidget(keyword_widget)
        
        # 右侧：定时播放配置
        timer_widget = QWidget()
        timer_layout = QVBoxLayout(timer_widget)
        timer_layout.setContentsMargins(10, 10, 10, 10)
        
        timer_title = QLabel("定时播放音频")
        timer_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #87CEEB; margin-bottom: 5px;")
        timer_layout.addWidget(timer_title)
        
        timer_desc = QLabel("按照设定的时间间隔，自动播放指定音频")
        timer_desc.setStyleSheet("color: #888; font-size: 11px; margin-bottom: 10px;")
        timer_desc.setWordWrap(True)
        timer_layout.addWidget(timer_desc)
        
        # 定时规则列表（使用表格显示）
        timer_list_group = QGroupBox("定时规则列表")
        timer_list_layout = QVBoxLayout()
        
        # 使用表格显示规则
        self.timer_table = QTableWidget()
        self.timer_table.setColumnCount(3)
        self.timer_table.setHorizontalHeaderLabels(["播放间隔", "音频文件", "操作"])
        self.timer_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.timer_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.timer_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.timer_table.setMaximumHeight(250)
        self.timer_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.timer_table.setStyleSheet("border: 1px solid #666; gridline-color: #555;")
        timer_list_layout.addWidget(self.timer_table)
        
        # 添加/删除/测试按钮
        timer_btn_layout = QHBoxLayout()
        btn_add_timer = QPushButton("➕ 添加规则")
        btn_add_timer.clicked.connect(self._add_timer_rule)
        btn_remove_timer = QPushButton("➖ 删除规则")
        btn_remove_timer.clicked.connect(self._remove_timer_rule)
        btn_test_timer = QPushButton("🔊 测试选中")
        btn_test_timer.clicked.connect(self._test_timer_audio)
        timer_btn_layout.addWidget(btn_add_timer)
        timer_btn_layout.addWidget(btn_remove_timer)
        timer_btn_layout.addWidget(btn_test_timer)
        timer_btn_layout.addStretch()
        timer_list_layout.addLayout(timer_btn_layout)
        
        timer_list_group.setLayout(timer_list_layout)
        timer_layout.addWidget(timer_list_group)
        
        timer_layout.addStretch()
        splitter.addWidget(timer_widget)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)
        
        # 刷新规则列表（如果音频管理器已初始化）
        if hasattr(self, 'audio_manager') and self.audio_manager:
            self._refresh_audio_rules()
        
        print("✓")
        sys.stdout.flush()
        return widget
    
    def _create_tts_tab(self):
        """创建TTS文字转语音标签页"""
        print("        [TTS标签] 创建widget...", end=" ")
        sys.stdout.flush()
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # 标题
        title = QLabel("🗣️ TTS文字转语音管理")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFD700; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # 功能开关
        tts_enabled_group = QGroupBox("功能开关")
        tts_enabled_layout = QVBoxLayout()
        
        # 启用开关
        tts_enabled_row = QHBoxLayout()
        self.cb_tts_enabled = QCheckBox("启用TTS文字转语音功能")
        self.cb_tts_enabled.setChecked(self.cfg.get('tts_enabled', False))
        self.cb_tts_enabled.stateChanged.connect(self._toggle_tts_enabled)
        tts_enabled_row.addWidget(self.cb_tts_enabled)
        tts_enabled_row.addStretch()
        tts_enabled_layout.addLayout(tts_enabled_row)
        
        # 播报所有弹幕开关
        tts_speak_all_row = QHBoxLayout()
        self.cb_tts_speak_all = QCheckBox("播报所有弹幕（不限于关键词匹配）")
        self.cb_tts_speak_all.setChecked(self.cfg.get('tts_speak_all_danmu', False))
        self.cb_tts_speak_all.stateChanged.connect(self._toggle_tts_speak_all)
        self.cb_tts_speak_all.setEnabled(self.cfg.get('tts_enabled', False))  # 只有启用TTS时才能开启
        tts_speak_all_row.addWidget(self.cb_tts_speak_all)
        tts_speak_all_row.addStretch()
        tts_enabled_layout.addLayout(tts_speak_all_row)
        
        # 队列超时时间设置
        queue_timeout_row = QHBoxLayout()
        queue_timeout_row.addWidget(QLabel("队列等待超时时间（秒）:"))
        self.spin_tts_queue_timeout = QDoubleSpinBox()
        self.spin_tts_queue_timeout.setMinimum(1.0)
        self.spin_tts_queue_timeout.setMaximum(300.0)
        self.spin_tts_queue_timeout.setSingleStep(1.0)
        self.spin_tts_queue_timeout.setValue(self.cfg.get('tts_queue_timeout', 10.0))
        self.spin_tts_queue_timeout.setSuffix(" 秒")
        self.spin_tts_queue_timeout.valueChanged.connect(self._on_tts_queue_timeout_changed)
        queue_timeout_row.addWidget(self.spin_tts_queue_timeout)
        queue_timeout_row.addStretch()
        
        timeout_desc = QLabel("💡 提示：当队列中有大量待播报的语音时，超过此时间的旧语音会被自动删除，只保留最新的。")
        timeout_desc.setStyleSheet("color: #888; font-size: 10px; padding: 5px 0;")
        timeout_desc.setWordWrap(True)
        tts_enabled_layout.addLayout(queue_timeout_row)
        tts_enabled_layout.addWidget(timeout_desc)
        
        tts_enabled_group.setLayout(tts_enabled_layout)
        layout.addWidget(tts_enabled_group)
        
        # TTS规则列表
        tts_list_group = QGroupBox("TTS规则列表")
        tts_list_layout = QVBoxLayout()
        
        # 使用表格显示规则
        self.tts_table = QTableWidget()
        self.tts_table.setColumnCount(4)
        self.tts_table.setHorizontalHeaderLabels(["关键词", "匹配模式", "播报内容", "操作"])
        self.tts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tts_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tts_table.setMaximumHeight(400)
        self.tts_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tts_table.setStyleSheet("border: 1px solid #666; gridline-color: #555;")
        tts_list_layout.addWidget(self.tts_table)
        
        # 添加/删除/测试按钮
        tts_btn_layout = QHBoxLayout()
        btn_add_tts = QPushButton("➕ 添加规则")
        btn_add_tts.clicked.connect(self._add_tts_rule)
        btn_remove_tts = QPushButton("➖ 删除规则")
        btn_remove_tts.clicked.connect(self._remove_tts_rule)
        btn_test_tts = QPushButton("🔊 测试选中")
        btn_test_tts.clicked.connect(self._test_tts_rule)
        tts_btn_layout.addWidget(btn_add_tts)
        tts_btn_layout.addWidget(btn_remove_tts)
        tts_btn_layout.addWidget(btn_test_tts)
        tts_btn_layout.addStretch()
        tts_list_layout.addLayout(tts_btn_layout)
        
        tts_list_group.setLayout(tts_list_layout)
        layout.addWidget(tts_list_group)
        
        # TTS屏蔽关键词列表
        tts_block_group = QGroupBox("屏蔽关键词列表")
        tts_block_layout = QVBoxLayout()
        
        # 使用列表显示屏蔽关键词
        self.tts_block_list = QListWidget()
        self.tts_block_list.setMaximumHeight(150)
        self.tts_block_list.setStyleSheet("border: 1px solid #666;")
        tts_block_layout.addWidget(self.tts_block_list)
        
        # 添加/删除按钮
        tts_block_btn_layout = QHBoxLayout()
        btn_add_block = QPushButton("➕ 添加关键词")
        btn_add_block.clicked.connect(self._add_tts_block_keyword)
        btn_remove_block = QPushButton("➖ 删除关键词")
        btn_remove_block.clicked.connect(self._remove_tts_block_keyword)
        tts_block_btn_layout.addWidget(btn_add_block)
        tts_block_btn_layout.addWidget(btn_remove_block)
        tts_block_btn_layout.addStretch()
        tts_block_layout.addLayout(tts_block_btn_layout)
        
        tts_block_group.setLayout(tts_block_layout)
        layout.addWidget(tts_block_group)
        
        # 说明文字
        desc_label = QLabel("💡 说明：当弹幕包含关键词时，会使用TTS文字转语音播报弹幕内容。\n"
                          "如果设置了自定义播报内容，则播报自定义内容；否则播报完整弹幕内容。\n"
                          "注意：如果用户昵称或弹幕内容包含屏蔽关键词，该弹幕将不予播报。")
        desc_label.setStyleSheet("color: #888; font-size: 11px; padding: 10px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # 刷新规则列表（如果TTS管理器已初始化）
        if hasattr(self, 'tts_manager') and self.tts_manager:
            self._refresh_tts_rules()
            self._refresh_tts_block_keywords()
        
        print("✓")
        sys.stdout.flush()
        return widget
    
    def _create_about_tab(self):
        """创建关于标签页"""
        print("        [关于标签] 创建widget...", end=" ")
        sys.stdout.flush()
        # 使用滚动区域包装内容，确保所有内容都能显示
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        print("✓")
        sys.stdout.flush()
        
        # 标题
        print("        [关于标签] 创建标题...", end=" ")
        sys.stdout.flush()
        title = QLabel("📢 关于本工具")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFD700; margin-bottom: 5px;")
        layout.addWidget(title)
        print("✓")
        sys.stdout.flush()
        
        # 微信二维码（置顶，紧凑布局）
        print("        [关于标签] 创建二维码...", end=" ")
        sys.stdout.flush()
        qr_group = QGroupBox("联系方式")
        qr_layout = QVBoxLayout()
        qr_layout.setSpacing(8)
        qr_layout.setContentsMargins(10, 10, 10, 10)
        
        # 二维码和邮箱布局（水平排列，更紧凑）
        qr_info_layout = QHBoxLayout()
        qr_info_layout.setSpacing(15)
        
        # 左侧：微信二维码
        wechat_layout = QVBoxLayout()
        wechat_layout.setSpacing(5)
        wechat_label = QLabel("微信二维码：")
        wechat_label.setStyleSheet("font-size: 11px; font-weight: bold;")
        wechat_layout.addWidget(wechat_label)
        
        # 尝试加载微信二维码图片
        qr_label = QLabel()
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_label.setStyleSheet("border: 2px solid #444; background: white; padding: 5px;")
        
        # 尝试多个可能的二维码图片路径
        qr_paths = []
        qr_files = ["wechat_qr.png", "wechat_qr.jpg", "微信二维码.png", "微信二维码.jpg"]
        
        # 使用路径工具查找资源文件
        try:
            from path_utils import get_resource_path
            for qr_file in qr_files:
                qr_path = get_resource_path(qr_file)
                if qr_path:
                    qr_paths.append(qr_path)
        except ImportError:
            # 如果path_utils不可用（向后兼容），使用旧逻辑
            qr_paths = [
                os.path.join(os.getcwd(), "wechat_qr.png"),
                os.path.join(os.getcwd(), "wechat_qr.jpg"),
                os.path.join(os.getcwd(), "微信二维码.png"),
                os.path.join(os.getcwd(), "微信二维码.jpg"),
            ]
            # 如果是打包环境，也尝试从临时目录加载
            if getattr(sys, 'frozen', False):
                base_dir = sys._MEIPASS
                qr_paths.extend([
                    os.path.join(base_dir, "wechat_qr.png"),
                    os.path.join(base_dir, "wechat_qr.jpg"),
                    os.path.join(base_dir, "微信二维码.png"),
                    os.path.join(base_dir, "微信二维码.jpg"),
                ])
        
        qr_loaded = False
        for qr_path in qr_paths:
            if os.path.exists(qr_path):
                try:
                    pixmap = QPixmap(qr_path)
                    # 缩放图片到合适大小（180x180，更紧凑）
                    if pixmap.width() > 180 or pixmap.height() > 180:
                        pixmap = pixmap.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    qr_label.setPixmap(pixmap)
                    qr_loaded = True
                    break
                except Exception as e:
                    print(f"        [关于标签] 加载二维码失败: {e}")
                    continue
        
        if not qr_loaded:
            # 如果图片不存在，显示提示文字
            qr_label.setText("二维码图片未找到\n请将图片文件放置在程序目录下\n文件名为：wechat_qr.png 或 微信二维码.png")
            qr_label.setStyleSheet("border: 2px solid #444; background: #f0f0f0; padding: 15px; color: #666; min-width: 150px; min-height: 150px;")
            qr_label.setWordWrap(True)
        
        wechat_layout.addWidget(qr_label)
        qr_info_layout.addLayout(wechat_layout)
        
        # 右侧：邮箱和开发者信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)
        
        contact_desc = QLabel("如有建议、BUG反馈、需要更新版本或需要功能授权（@回复、高级回复模式、暖场、指令控制），请联系：")
        contact_desc.setWordWrap(True)
        contact_desc.setStyleSheet("font-size: 10px; color: #CCC; margin-bottom: 8px;")
        info_layout.addWidget(contact_desc)
        
        developer_label = QLabel("开发者：故里何日还")
        developer_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #FFD700;")
        info_layout.addWidget(developer_label)
        
        email_layout = QHBoxLayout()
        email_layout.setSpacing(5)
        email_label = QLabel("邮箱：ncomscook@qq.com")
        email_label.setStyleSheet("font-size: 11px; color: #87CEEB;")
        email_layout.addWidget(email_label)
        
        # 添加复制邮箱按钮（更小的按钮）
        copy_email_btn = QPushButton("📋")
        copy_email_btn.setToolTip("复制邮箱地址")
        copy_email_btn.setStyleSheet("padding: 2px 8px; font-size: 10px;")
        copy_email_btn.clicked.connect(lambda: self._copy_to_clipboard("ncomscook@qq.com"))
        email_layout.addWidget(copy_email_btn)
        email_layout.addStretch()
        info_layout.addLayout(email_layout)
        
        info_layout.addStretch()
        qr_info_layout.addLayout(info_layout)
        
        qr_layout.addLayout(qr_info_layout)
        qr_group.setLayout(qr_layout)
        layout.addWidget(qr_group)
        print("✓")
        sys.stdout.flush()
        
        # CDK激活区域（简洁版）
        print("        [关于标签] 创建CDK激活区域...", end=" ")
        sys.stdout.flush()
        cdk_group = QGroupBox("🔑 CDK激活")
        cdk_layout = QVBoxLayout()
        cdk_layout.setSpacing(8)
        cdk_layout.setContentsMargins(10, 10, 10, 10)
        
        # CDK输入区域（一行显示）
        cdk_input_layout = QHBoxLayout()
        cdk_input_layout.setSpacing(8)
        
        self.cdk_input = QLineEdit()
        self.cdk_input.setPlaceholderText("请输入CDK激活码...")
        self.cdk_input.setStyleSheet("padding: 6px; font-size: 11px; flex: 1;")
        cdk_input_layout.addWidget(self.cdk_input, stretch=1)
        
        activate_btn = QPushButton("激活")
        activate_btn.setStyleSheet("padding: 6px 20px; font-size: 11px; background: #28a745; color: white; border: none; border-radius: 3px;")
        activate_btn.clicked.connect(self._activate_cdk)
        cdk_input_layout.addWidget(activate_btn)
        cdk_layout.addLayout(cdk_input_layout)
        
        # 当前激活状态显示（简洁版）
        self.cdk_status_label = QLabel()
        self.cdk_status_label.setWordWrap(True)
        self.cdk_status_label.setStyleSheet("font-size: 10px; padding: 6px; background: #1a1a1a; border: 1px solid #444; border-radius: 3px; min-height: 20px;")
        self._update_cdk_status_display()
        cdk_layout.addWidget(self.cdk_status_label)
        
        cdk_group.setLayout(cdk_layout)
        layout.addWidget(cdk_group)
        print("✓")
        sys.stdout.flush()
        
        # 工具说明（精简版）
        print("        [关于标签] 创建工具说明...", end=" ")
        sys.stdout.flush()
        purpose_group = QGroupBox("工具说明")
        purpose_layout = QVBoxLayout()
        purpose_layout.setContentsMargins(10, 10, 10, 10)
        purpose_text = QLabel(
            "解决抖音直播只能使用大号进行中控控场的问题。支持多小号智能控场、弹幕自动回复、暖场消息、统计分析等功能。"
        )
        purpose_text.setWordWrap(True)
        purpose_text.setStyleSheet("font-size: 11px; line-height: 1.5; padding: 5px;")
        purpose_layout.addWidget(purpose_text)
        purpose_group.setLayout(purpose_layout)
        layout.addWidget(purpose_group)
        print("✓")
        sys.stdout.flush()
        
        # 开发原因（精简版，更接地气）
        print("        [关于标签] 创建开发原因...", end=" ")
        sys.stdout.flush()
        reason_group = QGroupBox("开发原因")
        reason_layout = QVBoxLayout()
        reason_layout.setContentsMargins(10, 10, 10, 10)
        reason_text = QLabel(
            "网上类似工具问题：收费高、没售后、功能夸大、各种套路。被坑几次后，干脆自己写一个，有问题还能自己修，用得放心。"
        )
        reason_text.setWordWrap(True)
        reason_text.setStyleSheet("font-size: 11px; line-height: 1.5; padding: 5px; color: #FFA500;")
        reason_layout.addWidget(reason_text)
        reason_group.setLayout(reason_layout)
        layout.addWidget(reason_group)
        print("✓")
        sys.stdout.flush()
        
        # 调试工具区域
        print("        [关于标签] 创建调试工具区域...", end=" ")
        sys.stdout.flush()
        debug_group = QGroupBox("🔧 调试工具")
        debug_layout = QVBoxLayout()
        debug_layout.setContentsMargins(10, 10, 10, 10)
        debug_layout.setSpacing(8)
        
        debug_desc = QLabel("弹幕捕获测试窗口：用于调试和优化弹幕捕获功能，可以实时查看捕获到的弹幕、礼物、在线人数等数据，以及详细的调试信息。")
        debug_desc.setWordWrap(True)
        debug_desc.setStyleSheet("font-size: 11px; color: #CCC; margin-bottom: 8px;")
        debug_layout.addWidget(debug_desc)
        
        btn_open_test = QPushButton("🔍 打开弹幕捕获测试窗口")
        btn_open_test.setStyleSheet("padding: 8px 20px; font-size: 12px; background: #007bff; color: white; border: none; border-radius: 4px;")
        btn_open_test.setToolTip("打开独立的弹幕捕获测试窗口，用于调试弹幕捕获功能")
        btn_open_test.clicked.connect(self._open_danmu_test_window)
        debug_layout.addWidget(btn_open_test)
        
        debug_group.setLayout(debug_layout)
        layout.addWidget(debug_group)
        print("✓")
        sys.stdout.flush()
        
        # 声明信息（精简版）
        print("        [关于标签] 创建声明信息...", end=" ")
        sys.stdout.flush()
        disclaimer_label = QLabel(
            "⚠️ 声明：本工具仅供学习交流使用，禁止倒卖。使用本工具时请遵守相关法律法规。"
        )
        disclaimer_label.setWordWrap(True)
        disclaimer_label.setStyleSheet("font-size: 10px; color: #FF6B6B; padding: 8px; background: #1a1a1a; border: 1px solid #444; border-radius: 3px;")
        disclaimer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(disclaimer_label)
        print("✓")
        sys.stdout.flush()
        
        layout.addStretch()
        
        # 将widget放入滚动区域
        scroll_area.setWidget(widget)
        
        print("        [关于标签] 完成")
        sys.stdout.flush()
        return scroll_area
    
    def _ensure_window_fits_content(self):
        """确保窗口大小足够显示所有内容"""
        try:
            # 获取当前窗口大小
            current_width = self.width()
            current_height = self.height()
            
            # 如果窗口太小，调整到合适的大小
            if current_width < 1200:
                self.resize(1400, current_height)
            if current_height < 750:
                self.resize(self.width(), 900)
            
            # 确保窗口至少是最小尺寸
            if self.width() < 1200:
                self.setMinimumWidth(1200)
            if self.height() < 750:
                self.setMinimumHeight(750)
        except Exception as e:
            # 静默失败，不影响主流程
            pass
    
    def _copy_to_clipboard(self, text):
        """复制文本到剪贴板"""
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
        QMessageBox.information(self, "提示", f"已复制到剪贴板：{text}")
        
    def _activate_cdk(self):
        """激活CDK（必须联网验证）"""
        cdk = self.cdk_input.text().strip()
        if not cdk:
            QMessageBox.warning(self, "提示", "请输入CDK激活码！")
            return
        
        # 显示验证中提示
        QMessageBox.information(self, "提示", "正在连接服务器验证CDK，请稍候...")
        
        try:
            from server_client import verify_cdk_online, report_cdk_activation
            from cdk_manager import format_cdk_expire_time
            from device_info import get_device_info
            
            machine_code = get_device_info().get("machine_code")
            
            # 在线验证CDK（必须联网）
            is_valid, message, cdk_data = verify_cdk_online(cdk)
            
            if not is_valid:
                QMessageBox.warning(self, "CDK验证失败", f"{message}\n\n请确保已连接到服务器。")
                return
            
            # CDK验证成功，立即上报激活信息到服务器（同步，确保状态同步）
            success, report_msg = report_cdk_activation(
                cdk=cdk,
                features=cdk_data.get("features", []),
                expire_time=cdk_data.get("expire_time", 0),
                activate_time=int(time.time())
            )
            
            if not success:
                QMessageBox.warning(
                    self, 
                    "激活失败", 
                    f"CDK验证成功，但上报激活信息失败：{report_msg}\n\n请重试或联系管理员。"
                )
                return
            
            # 保存激活信息到本地配置（用于显示）
            activation_info = {
                "cdk": cdk,
                "features": cdk_data.get("features", []),
                "expire_time": cdk_data.get("expire_time", 0),
                "activate_time": int(time.time()),
                "machine_code": machine_code
            }
            
            self.cfg['cdk_activation'] = activation_info
            save_cfg(self.cfg)
            
            print(f"    [CDK激活] CDK激活成功并已同步到服务器")
            
            # 如果CDK包含AI功能，保存CDK代码到配置中（用于token消耗上报）
            features = cdk_data.get("features", [])
            if "ai_reply" in features:
                self.cfg['ai_reply_cdk'] = cdk
                save_cfg(self.cfg)
                print(f"    [CDK激活] AI功能已激活，CDK已保存")
            
            # 更新UI显示
            self._update_cdk_status_display()
            
            # 重新检查授权（合并CDK授权和服务器授权）
            self._check_feature_auth_with_cdk()
            
            # 显示成功消息
            features_str = "、".join(cdk_data.get("features", []))
            expire_str = format_cdk_expire_time(cdk_data.get("expire_time", 0))
            QMessageBox.information(
                self, 
                "激活成功", 
                f"CDK激活成功！\n\n"
                f"激活功能：{features_str}\n"
                f"有效期：{expire_str}\n\n"
                f"功能已启用，可以开始使用。"
            )
            
            # 清空输入框
            self.cdk_input.clear()
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            error_msg = f"[异常] CDK激活失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
            print(error_msg)
            print(f"详细堆栈:\n{error_detail}")
            sys.stdout.flush()
            QMessageBox.critical(self, "激活失败", f"CDK激活失败：{str(e)}")
    
    def _update_cdk_status_display(self):
        """更新CDK状态显示"""
        try:
            activation_info = self.cfg.get('cdk_activation')
            
            if not activation_info:
                self.cdk_status_label.setText(
                    "当前状态：未激活\n"
                    "可用功能：仅基础功能（自动回复）"
                )
                self.cdk_status_label.setStyleSheet(
                    "font-size: 10px; padding: 8px; background: #1a1a1a; "
                    "border: 1px solid #444; border-radius: 5px; color: #888;"
                )
                return
            
            # 显示本地保存的激活信息（但实际授权状态从服务器获取）
            cdk = activation_info.get('cdk', '')
            if not cdk:
                self.cdk_status_label.setText("状态：激活信息无效")
                return
            
            from cdk_manager import format_cdk_expire_time
            features = activation_info.get('features', [])
            expire_time = activation_info.get('expire_time', 0)
            expire_str = format_cdk_expire_time(expire_time)
            
            # 功能名称映射
            feature_names = {
                'specific_reply': '@回复',
                'advanced_reply': '高级回复',
                'warmup': '暖场',
                'command': '指令'
            }
            features_display = "、".join([feature_names.get(f, f) for f in features]) if features else "无"
            
            # 简洁显示：状态 + 功能 + 有效期（一行或两行）
            status_text = f"✓ 已激活 | 功能：{features_display} | {expire_str}"
            if len(status_text) > 60:  # 如果太长，换行显示
                status_text = f"✓ 已激活\n功能：{features_display} | {expire_str}"
            
            self.cdk_status_label.setText(status_text)
            self.cdk_status_label.setStyleSheet(
                "font-size: 10px; padding: 6px; background: rgba(0, 255, 0, 0.1); "
                "border: 1px solid #28a745; border-radius: 3px; color: #28a745;"
            )
            
        except Exception as e:
            import traceback
            print(f"    [CDK状态显示] 错误: {e}")
            traceback.print_exc()
            self.cdk_status_label.setText(f"状态显示错误：{str(e)}")
    
    def _check_feature_auth_with_cdk(self):
        """检查功能授权状态（合并CDK授权和服务器授权）"""
        def check():
            try:
                # 必须从服务器获取授权（服务器会合并服务器授权和CDK授权）
                server_auth = None
                try:
                    from server_client import check_feature_auth
                    server_auth = check_feature_auth()
                    print(f"    [授权检查] 服务器授权: {server_auth}")
                except Exception as e:
                    print(f"    [授权检查] 服务器连接失败: {e}")
                    # 必须联网，连接失败返回全部未授权
                
                # 授权完全由服务器控制
                if server_auth:
                    final_auth = server_auth
                else:
                    # 服务器连接失败，返回全部未授权（必须联网才能使用）
                    final_auth = {
                        "specific_reply": False,
                        "advanced_reply": False,
                        "warmup": False,
                        "command": False
                    }
                
                print(f"    [授权检查] 最终授权结果: {final_auth}")
                sys.stdout.flush()
                
                # 在主线程中更新UI
                from functools import partial
                QTimer.singleShot(0, partial(self._update_feature_auth_ui, final_auth))
                
            except Exception as e:
                # 授权检查失败，返回全部未授权（必须联网）
                import traceback
                error_detail = traceback.format_exc()
                print(f"    [授权检查] 失败: {e}")
                print(f"    [授权检查] 详细错误: {error_detail}")
                sys.stdout.flush()
                
                # 必须联网才能使用，返回全部未授权
                no_auth = {
                    "specific_reply": False,
                    "advanced_reply": False,
                    "warmup": False,
                    "command": False
                }
                from functools import partial
                QTimer.singleShot(0, partial(self._update_feature_auth_ui, no_auth))
        
        # 在后台线程中执行检查
        thread = threading.Thread(target=check, daemon=True)
        thread.start()
    
    def _get_cdk_auth(self):
        """获取CDK授权状态（现在完全由服务器控制，不再使用本地验证）"""
        # CDK授权状态现在完全由服务器通过check_features接口返回
        # 这里返回空授权，实际授权状态由服务器实时验证
        return {
            "specific_reply": False,
            "advanced_reply": False,
            "warmup": False,
            "command": False
        }
        
    def _toggle_auto_refresh(self, enabled):
        """切换自动刷新"""
        self.stats_auto_refresh_enabled = enabled
        if enabled:
            if not self.stats_timer.isActive():
                self.stats_timer.start(5000)
        else:
            if self.stats_timer.isActive():
                self.stats_timer.stop()
    
    def _on_stats_scroll(self, value):
        """统计报表滚动事件处理"""
        # 记录滚动位置
        self.stats_scroll_position = value
        
        # 标记用户正在滚动
        self.stats_is_user_scrolling = True
        
        # 重置计时器（如果用户在滚动，延迟标记为"不在滚动"）
        self.stats_scroll_timer.stop()
        self.stats_scroll_timer.start(1000)  # 1秒后认为用户停止滚动
    
    def _refresh_statistics(self):
        """刷新统计显示"""
        # 检查属性是否存在（可能在初始化过程中被调用）
        if hasattr(self, 'stats_is_user_scrolling'):
            # 如果用户正在滚动，跳过本次刷新（避免打断用户查看）
            if self.stats_is_user_scrolling:
                return
        
        # 检查自动刷新设置（可能在初始化过程中被调用）
        if hasattr(self, 'stats_auto_refresh_enabled'):
            # 如果自动刷新被禁用，跳过
            if not self.stats_auto_refresh_enabled:
                return
        
        try:
            # 保存当前滚动位置
            scrollbar = self.stats_text_display.verticalScrollBar()
            saved_scroll_position = scrollbar.value()
            is_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10  # 接近底部（10像素容差）
            # 获取所有已配置的关键词（用于过滤未匹配关键词统计）
            configured_keywords = set()
            # 从全局配置获取
            global_reply_rules = self.cfg.get('reply_rules', [])
            global_specific_rules = self.cfg.get('specific_rules', [])
            for rule in global_reply_rules + global_specific_rules:
                kw = rule.get('kw', '').strip()
                if kw:
                    configured_keywords.add(kw)
            
            # 从所有账户配置获取
            from account_manager import get_all_accounts
            accounts = get_all_accounts()
            for acc in accounts:
                account_reply_rules = acc.get('reply_rules', [])
                account_specific_rules = acc.get('specific_rules', [])
                for rule in account_reply_rules + account_specific_rules:
                    kw = rule.get('kw', '').strip()
                    if kw:
                        configured_keywords.add(kw)
            
            stats = statistics_manager.get_all_statistics(configured_keywords)
            
            # 更新文本显示
            html = "<div style='padding: 15px;'>"
            html += "<h2 style='color:#FFD700; margin-top:0;'>📊 统计报表</h2>"
            
            # 运行时间
            runtime_hours = int(stats['runtime'] // 3600)
            runtime_mins = int((stats['runtime'] % 3600) // 60)
            runtime_secs = int(stats['runtime'] % 60)
            html += f"<div style='margin-bottom: 15px;'><b style='color:#87CEEB;'>运行时间:</b> <span style='color:#FFD700;'>{runtime_hours}小时 {runtime_mins}分钟 {runtime_secs}秒</span></div>"
            
            # 回复统计
            html += "<h3 style='color:#00FF00; margin-top: 20px;'>💬 回复统计</h3>"
            reply_stats = stats['reply']
            html += f"<div style='margin-bottom: 10px;'><b>总回复数:</b> <span style='color:#FFD700;'>{reply_stats['total_replies']}</span></div>"
            
            html += "<table style='width:100%; border-collapse: collapse; margin-bottom: 15px;'>"
            html += "<tr style='background:#333;'><th style='padding:8px; text-align:left; border:1px solid #555;'>小号</th><th style='padding:8px; text-align:left; border:1px solid #555;'>回复次数</th><th style='padding:8px; text-align:left; border:1px solid #555;'>平均响应时间(秒)</th></tr>"
            for account_name, count in sorted(reply_stats['reply_counts'].items(), key=lambda x: x[1], reverse=True):
                avg_time = reply_stats['avg_response_times'].get(account_name, 0)
                html += f"<tr><td style='padding:6px; border:1px solid #555;'>{account_name}</td><td style='padding:6px; border:1px solid #555; color:#FFD700;'>{count}</td><td style='padding:6px; border:1px solid #555; color:#87CEEB;'>{avg_time:.3f}</td></tr>"
            html += "</table>"
            
            # 关键词命中Top10
            html += "<h4 style='color:#FFD700; margin-top: 15px;'>🔥 关键词命中Top10</h4>"
            for account_name, keywords in reply_stats['keyword_top'].items():
                if keywords:
                    html += f"<div style='margin-bottom: 10px;'><b>{account_name}:</b></div>"
                    html += "<ul style='margin-top: 5px; margin-bottom: 10px;'>"
                    for keyword, count in keywords[:10]:
                        html += f"<li style='margin-bottom: 3px;'><span style='color:#FFD700;'>{keyword}</span>: <span style='color:#87CEEB;'>{count}</span> 次</li>"
                    html += "</ul>"
            
            # 弹幕统计
            html += "<h3 style='color:#00FF00; margin-top: 20px;'>📝 弹幕统计</h3>"
            danmu_stats = stats['danmu']
            html += f"<div style='margin-bottom: 10px;'><b>弹幕总数:</b> <span style='color:#FFD700;'>{danmu_stats['total_count']}</span></div>"
            html += f"<div style='margin-bottom: 10px;'><b>活跃用户数:</b> <span style='color:#FFD700;'>{danmu_stats['unique_users']}</span></div>"
            
            # 活跃用户Top10
            if danmu_stats['active_users']:
                html += "<h4 style='color:#FFD700; margin-top: 15px;'>👥 活跃用户Top10</h4>"
                html += "<ul style='margin-top: 5px;'>"
                for user, count in list(danmu_stats['active_users'].items())[:10]:
                    html += f"<li style='margin-bottom: 3px;'><span style='color:#FFD700;'>{user}</span>: <span style='color:#87CEEB;'>{count}</span> 条</li>"
                html += "</ul>"
            
            # 高频未匹配关键词（重要功能！）
            if danmu_stats.get('unmatched_keywords'):
                html += "<h3 style='color:#FF6B6B; margin-top: 20px;'>⚠️ 高频未匹配关键词</h3>"
                html += f"<div style='margin-bottom: 10px; color:#FFA500;'><b>未匹配弹幕数:</b> <span style='color:#FFD700;'>{danmu_stats.get('unmatched_count', 0)}</span> 条</div>"
                html += "<div style='margin-bottom: 10px; color:#FFA500;'><b>说明:</b> 以下关键词在弹幕中高频出现，但未配置回复规则，建议添加规则以提高回复率</div>"
                html += "<table style='width:100%; border-collapse: collapse; margin-bottom: 15px;'>"
                html += "<tr style='background:#333;'><th style='padding:8px; text-align:left; border:1px solid #555;'>排名</th><th style='padding:8px; text-align:left; border:1px solid #555;'>关键词</th><th style='padding:8px; text-align:left; border:1px solid #555;'>出现次数</th><th style='padding:8px; text-align:left; border:1px solid #555;'>建议操作</th></tr>"
                for idx, (keyword, count) in enumerate(list(danmu_stats['unmatched_keywords'].items())[:20], 1):
                    # 根据出现次数给出建议
                    if count >= 10:
                        suggestion = "🔴 强烈建议添加"
                        suggestion_color = "#FF6B6B"
                    elif count >= 5:
                        suggestion = "🟡 建议添加"
                        suggestion_color = "#FFA500"
                    else:
                        suggestion = "🟢 可考虑添加"
                        suggestion_color = "#87CEEB"
                    
                    html += f"<tr><td style='padding:6px; border:1px solid #555;'>{idx}</td><td style='padding:6px; border:1px solid #555; color:#FFD700; font-weight:bold;'>{keyword}</td><td style='padding:6px; border:1px solid #555; color:#87CEEB;'>{count}</td><td style='padding:6px; border:1px solid #555; color:{suggestion_color};'>{suggestion}</td></tr>"
                html += "</table>"
            
            # 性能指标
            html += "<h3 style='color:#00FF00; margin-top: 20px;'>⚡ 性能指标</h3>"
            perf_stats = stats['performance']
            html += f"<div style='margin-bottom: 10px;'><b>锁竞争总数:</b> <span style='color:#FFD700;'>{perf_stats['lock_contention_total']}</span></div>"
            html += f"<div style='margin-bottom: 10px;'><b>锁竞争（最近1小时）:</b> <span style='color:#FFD700;'>{perf_stats['lock_contention_recent']}</span></div>"
            
            if perf_stats['queue_stats']:
                html += "<h4 style='color:#FFD700; margin-top: 15px;'>📦 队列状态</h4>"
                html += "<table style='width:100%; border-collapse: collapse;'>"
                html += "<tr style='background:#333;'><th style='padding:8px; text-align:left; border:1px solid #555;'>小号</th><th style='padding:8px; text-align:left; border:1px solid #555;'>当前队列</th><th style='padding:8px; text-align:left; border:1px solid #555;'>最大队列</th><th style='padding:8px; text-align:left; border:1px solid #555;'>平均队列</th></tr>"
                for account_name, queue_stat in perf_stats['queue_stats'].items():
                    html += f"<tr><td style='padding:6px; border:1px solid #555;'>{account_name}</td><td style='padding:6px; border:1px solid #555; color:#FFD700;'>{queue_stat['current']}</td><td style='padding:6px; border:1px solid #555; color:#FF6B6B;'>{queue_stat['max']}</td><td style='padding:6px; border:1px solid #555; color:#87CEEB;'>{queue_stat['avg']:.2f}</td></tr>"
                html += "</table>"
            
            html += "</div>"
            self.stats_text_display.setHtml(html)
            
            # 恢复滚动位置
            # 如果用户之前在底部，刷新后保持在底部
            # 否则恢复到之前的滚动位置
            QTimer.singleShot(10, lambda: self._restore_scroll_position(saved_scroll_position, is_at_bottom))
            
            # 更新图表
            self._update_statistics_chart(stats)
            
        except Exception as e:
            import traceback
            error_msg = f"[异常] 刷新统计信息失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
            print(error_msg)
            print(traceback.format_exc())
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
    
    def _restore_scroll_position(self, saved_position, is_at_bottom):
        """恢复滚动位置"""
        try:
            scrollbar = self.stats_text_display.verticalScrollBar()
            if is_at_bottom:
                # 如果之前在底部，刷新后保持在底部
                scrollbar.setValue(scrollbar.maximum())
            else:
                # 否则恢复到之前的滚动位置
                scrollbar.setValue(saved_position)
        except Exception as e:
            # 忽略恢复滚动位置时的错误
            pass
    
    def _update_statistics_chart(self, stats):
        """更新统计图表"""
        try:
            # 使用简单的HTML/CSS/JavaScript创建图表
            # 提取数据
            reply_counts = stats['reply']['reply_counts']
            account_names = list(reply_counts.keys())
            reply_values = list(reply_counts.values())
            
            # 创建HTML图表（使用Chart.js的CDN或简单的CSS柱状图）
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
                <style>
                    body { 
                        background: #1a1a1a; 
                        color: #E0E0E0; 
                        font-family: 'Microsoft YaHei UI';
                        margin: 0;
                        padding: 15px;
                    }
                    .chart-container {
                        margin-bottom: 30px;
                    }
                    h3 {
                        color: #FFD700;
                        margin-top: 0;
                    }
                </style>
            </head>
            <body>
                <h3>📊 回复量统计</h3>
                <div class="chart-container">
                    <canvas id="replyChart"></canvas>
                </div>
                <h3>📝 弹幕统计</h3>
                <div class="chart-container">
                    <canvas id="danmuChart"></canvas>
                </div>
                <script>
            """
            
            # 回复量柱状图
            html += f"""
                    const ctx1 = document.getElementById('replyChart').getContext('2d');
                    const replyChart = new Chart(ctx1, {{
                        type: 'bar',
                        data: {{
                            labels: {json.dumps(account_names, ensure_ascii=False)},
                            datasets: [{{
                                label: '回复次数',
                                data: {json.dumps(reply_values)},
                                backgroundColor: 'rgba(255, 215, 0, 0.6)',
                                borderColor: 'rgba(255, 215, 0, 1)',
                                borderWidth: 1
                            }}]
                        }},
                        options: {{
                            responsive: true,
                            maintainAspectRatio: true,
                            plugins: {{
                                legend: {{
                                    labels: {{ color: '#E0E0E0' }}
                                }}
                            }},
                            scales: {{
                                y: {{
                                    beginAtZero: true,
                                    ticks: {{ color: '#E0E0E0' }},
                                    grid: {{ color: '#333' }}
                                }},
                                x: {{
                                    ticks: {{ color: '#E0E0E0' }},
                                    grid: {{ color: '#333' }}
                                }}
                            }}
                        }}
                    }});
            """
            
            # 弹幕总数（简单的文本显示，因为只有一个值）
            danmu_total = stats['danmu']['total_count']
            html += f"""
                    const ctx2 = document.getElementById('danmuChart').getContext('2d');
                    const danmuChart = new Chart(ctx2, {{
                        type: 'doughnut',
                        data: {{
                            labels: ['弹幕总数'],
                            datasets: [{{
                                data: [{danmu_total}],
                                backgroundColor: ['rgba(135, 206, 235, 0.6)'],
                                borderColor: ['rgba(135, 206, 235, 1)'],
                                borderWidth: 1
                            }}]
                        }},
                        options: {{
                            responsive: true,
                            maintainAspectRatio: true,
                            plugins: {{
                                legend: {{
                                    labels: {{ color: '#E0E0E0' }}
                                }},
                                title: {{
                                    display: true,
                                    text: '弹幕总数: {danmu_total}',
                                    color: '#FFD700',
                                    font: {{ size: 16 }}
                                }}
                            }}
                        }}
                    }});
            """
            
            html += """
                </script>
            </body>
            </html>
            """
            
            self.stats_chart_view.setHtml(html)
            
        except Exception as e:
            # 如果图表加载失败，显示简单的HTML文本
            simple_html = f"""
            <html>
            <head><meta charset="UTF-8"></head>
            <body style="background:#1a1a1a; color:#E0E0E0; padding:20px; font-family:'Microsoft YaHei UI';">
                <h3>📊 图表加载中...</h3>
                <p>如果图表无法显示，请检查网络连接（需要加载Chart.js库）</p>
                <p>错误: {str(e)}</p>
            </body>
            </html>
            """
            self.stats_chart_view.setHtml(simple_html)
    
    def _export_statistics_csv(self):
        """导出统计为CSV文件"""
        try:
            # 获取保存路径
            from datetime import datetime
            default_filename = f"统计报表_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            file_path, _ = QFileDialog.getSaveFileName(
                self, 
                "导出统计报表", 
                default_filename,
                "CSV文件 (*.csv);;所有文件 (*)"
            )
            
            if not file_path:
                return
            
            # 获取CSV数据
            csv_rows = statistics_manager.export_to_csv_rows()
            
            # 写入文件
            import csv
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:  # utf-8-sig for Excel compatibility
                writer = csv.writer(f)
                writer.writerows(csv_rows)
            
            QMessageBox.information(self, "成功", f"统计报表已导出到:\n{file_path}")
            print(f"    [导出统计] 已导出到: {file_path}")
            sys.stdout.flush()
            
        except Exception as e:
            import traceback
            error_msg = f"[异常] 导出统计报表失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
            print(error_msg)
            print(traceback.format_exc())
            sys.stdout.flush()
            QMessageBox.critical(self, "错误", f"导出统计报表失败: {str(e)}")
            traceback.print_exc()
            sys.stdout.flush()
    
    def _reset_statistics(self):
        """重置统计数据"""
        reply = QMessageBox.question(
            self, "确认重置", 
            "确定要重置所有统计数据吗？\n此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            statistics_manager.reset_statistics()
            self._refresh_statistics()
            QMessageBox.information(self, "成功", "统计数据已重置")
            print("    [重置统计] 统计数据已重置")
            sys.stdout.flush()
        
    def _connect_logger_signal(self):
        """连接全局日志信号（已不再使用，改用直接回调方式）"""
        # 不再需要，日志通过回调函数直接发送
        self._logger_connected = True
        
    def _clear_log(self):
        """清空日志"""
        self.log_display.clear()
        
    def _clear_stats(self):
        """清空统计"""
        self.viewer_count = "0"
        self.gift_total_count = 0
        self._update_statistics_display()
        
    def _update_statistics_display(self):
        """更新统计显示（置顶区域）"""
        if not hasattr(self, 'stats_display'):
            return
            
        html = "<div style='padding: 5px;'>"
        
        # 在线人数
        html += f"<div style='margin-bottom: 8px;'><b style='color:#87CEEB;'>📊 在线人数:</b> <span style='color:#FFD700;'>{self.viewer_count}</span></div>"
        
        # 礼物总数统计
        html += f"<div><b style='color:#FFD700;'>🎁 礼物总数:</b> <span style='color:#FFD700;'>{self.gift_total_count}</span></div>"
        
        html += "</div>"
        
        self.stats_display.setHtml(html)
        
    def _update_gift_statistics(self, user, gift_name, gift_count_str="1"):
        """更新礼物统计（只统计总数）"""
        try:
            gift_count = int(gift_count_str)
        except:
            gift_count = 1
            
        self.gift_total_count += gift_count
        self._update_statistics_display()
        
    def _update_viewer_count(self, count):
        """更新在线人数"""
        self.viewer_count = count
        self._update_statistics_display()
        
    def _init_queue_config(self):
        """初始化队列配置"""
        # 更新全局队列配置
        global_queue.set_queue_mode(self.cfg.get('queue_mode', '轮询'))
        global_queue.set_time_window(self.cfg.get('queue_time_window', 5.0))
        global_queue.set_lock_timeout(self.cfg.get('queue_lock_timeout', 30.0))
        # 单回复模式下，strict_single_reply 始终为 True
        global_queue.set_strict_single_reply(True)  # 单回复模式始终启用严格模式
        global_queue.set_auto_cleanup(self.cfg.get('auto_cleanup_locks', True))
        global_queue.set_max_lock_history(self.cfg.get('max_lock_history', 1000))
        global_queue.set_allow_multiple_reply(self.cfg.get('allow_multiple_reply', False))
        
        # 更新账户优先级
        account_priorities = self.cfg.get('account_priorities', {})
        for account_name, priority in account_priorities.items():
            global_queue.set_account_priority(account_name, priority)
            
    def _load_accounts(self):
        """加载账户列表到界面"""
        self.account_list.clear()
        accounts = get_all_accounts()
        for account in accounts:
            name = account.get('name', '')
            nickname = account.get('nickname', '')
            enabled = account.get('enabled', True)
            status = "✅" if enabled else "❌"
            item_text = f"{status} {name} (昵称: {nickname})"
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, name)  # 存储账户名称
            self.account_list.addItem(item)
        
        # 同时更新规则配置下拉框
        self._update_account_rule_combo()
            
    def _add_account(self):
        """添加小号"""
        dialog = AccountDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data['name'] or not data['nickname']:
                QMessageBox.warning(self, "错误", "小号名称和昵称不能为空！")
                return
                
            if add_account(data['name'], data['nickname'], data['url']):
                self._load_accounts()
                # _load_accounts 内部会调用 _update_account_rule_combo
                QMessageBox.information(self, "成功", "小号添加成功！")
                # global_logger.log("系统", f"添加小号: {data['name']}")
                print(f"    [添加小号] 小号 '{data['name']}' 已添加")
                sys.stdout.flush()
            else:
                QMessageBox.warning(self, "错误", "小号名称已存在！")
                
    def _edit_account(self):
        """编辑小号"""
        current_item = self.account_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "提示", "请先选择要编辑的小号！")
            return
            
        account_name = current_item.data(Qt.ItemDataRole.UserRole)
        accounts = get_all_accounts()
        account_data = None
        for acc in accounts:
            if acc.get('name') == account_name:
                account_data = acc
                break
                
        if not account_data:
            return
            
        dialog = AccountDialog(self, account_data)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            update_account(account_name, nickname=data['nickname'], url=data['url'])
            self._load_accounts()
            
            # 如果该账户的窗口已打开，更新窗口
            if account_name in self.account_windows:
                window = self.account_windows[account_name]
                window.update_account_info(data['nickname'], data['url'])
                
    def _delete_account(self):
        """删除账户"""
        current_item = self.account_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "提示", "请先选择要删除的小号！")
            return
            
        account_name = current_item.data(Qt.ItemDataRole.UserRole)
        
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确定要删除小号 '{account_name}' 吗？\n这将关闭该小号的窗口。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 关闭该账户的窗口
            if account_name in self.account_windows:
                self.account_windows[account_name].close()
                del self.account_windows[account_name]
                
            remove_account(account_name)
            self._load_accounts()
            # _load_accounts 内部会调用 _update_account_rule_combo
            # global_logger.log("系统", f"删除小号: {account_name}")
            print(f"    [删除小号] 小号 '{account_name}' 已删除")
            sys.stdout.flush()
            
    def _start_account(self):
        """启动账户窗口"""
        current_item = self.account_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "提示", "请先选择要启动的小号！")
            return
            
        account_name = current_item.data(Qt.ItemDataRole.UserRole)
        
        # 清理无效的窗口引用（已被销毁的窗口对象）
        # 同时检查窗口是否真的还存在且可见
        to_remove = []
        for acc_name, win in list(self.account_windows.items()):
            try:
                # 尝试多种方法检查窗口对象是否有效
                # 方法1: 检查对象是否仍然有效（访问属性）
                _ = win.objectName()
                # 方法2: 如果对象有效，检查是否真的还在显示（窗口可能被关闭但对象还存在）
                # 注意：即使窗口关闭，对象可能还存在，所以我们需要更严格的检查
                # 实际上，如果窗口被关闭，isVisible() 会返回 False
                # 但如果窗口对象被销毁，访问任何属性都会抛出 RuntimeError
            except (RuntimeError, AttributeError):
                # 窗口对象已被销毁，标记为删除
                to_remove.append(acc_name)
            except Exception:
                # 其他异常也标记为删除（安全起见）
                to_remove.append(acc_name)
        
        for acc_name in to_remove:
            if acc_name in self.account_windows:
                del self.account_windows[acc_name]
        
        # 检查窗口是否已打开（再次验证窗口对象是否有效且可见）
        if account_name in self.account_windows:
            try:
                window = self.account_windows[account_name]
                # 验证窗口对象是否有效
                _ = window.objectName()
                # 检查窗口是否仍然可见（窗口关闭后 isVisible() 会返回 False，但对象可能还存在）
                # 如果窗口已经关闭但对象还存在，我们也应该允许重新打开
                if window.isVisible():
                    # 窗口有效且可见
                    QMessageBox.information(self, "提示", f"小号 '{account_name}' 的窗口已经打开！")
                    window.raise_()
                    window.activateWindow()
                    return
                else:
                    # 窗口对象存在但不可见（可能被关闭了），从字典中移除，允许重新打开
                    del self.account_windows[account_name]
            except (RuntimeError, AttributeError):
                # 窗口对象已被销毁，从字典中移除
                if account_name in self.account_windows:
                    del self.account_windows[account_name]
            
        # 获取账户信息
        accounts = get_all_accounts()
        account_data = None
        for acc in accounts:
            if acc.get('name') == account_name:
                account_data = acc
                break
                
        if not account_data:
            QMessageBox.warning(self, "错误", "小号不存在！")
            return
            
        # 创建账户窗口（延迟导入避免循环导入）
        try:
            print(f"    [启动小号] 正在创建窗口: {account_name}")
            sys.stdout.flush()
            from main_window import LiveBrowser
            print(f"    [启动小号] 导入LiveBrowser成功")
            sys.stdout.flush()
            
            # 创建日志回调函数，直接发送到控制面板的日志显示
            def log_callback(text):
                """日志回调函数，将小号的日志发送到控制面板，并更新统计"""
                if hasattr(self, 'log_display') and self.log_display:
                    from datetime import datetime
                    import re
                    t = datetime.now().strftime("%H:%M:%S")
                    account_tag = f"[{account_name}]"
                    
                    # 解析日志文本，提取礼物和在线人数信息
                    # 格式: <span style='color:#FFD700;'>[礼物]</span> 用户名 送出了 X个 礼物名
                    # 格式: <span style='color:#87CEEB;'>[在线人数]</span> 人数
                    
                    # 检查是否为礼物日志
                    if '[礼物]' in text or '送出了' in text:
                        # 提取礼物信息 - 匹配格式：用户名 送出了 X个 礼物名 或 用户名 送出了 礼物名
                        gift_patterns = [
                            r'(\S+)\s+送出了\s+(\d+)\s*个\s+(\S+)',  # 用户名 送出了 X个 礼物名
                            r'(\S+)\s+送出了\s+(\S+)',  # 用户名 送出了 礼物名
                        ]
                        for pattern in gift_patterns:
                            match = re.search(pattern, text)
                            if match:
                                groups = match.groups()
                                if len(groups) >= 3:
                                    user = groups[0]
                                    gift_count = groups[1]
                                    gift_name = groups[2]
                                else:
                                    user = groups[0]
                                    gift_name = groups[1]
                                    gift_count = "1"
                                self._update_gift_statistics(user, gift_name, gift_count)
                                break
                    
                    # 检查是否为在线人数日志（静默处理，不显示在日志中）
                    is_viewer_count = False
                    if '[在线人数]' in text:
                        # 提取在线人数 - 匹配格式：[在线人数]</span> 人数
                        count_match = re.search(r'\[在线人数\]</span>\s*(\S+)', text)
                        if not count_match:
                            # 备选：匹配纯文本格式
                            count_match = re.search(r'在线人数[：:]\s*(\S+)', text)
                        if count_match:
                            count = count_match.group(1).strip()
                            self._update_viewer_count(count)
                            is_viewer_count = True  # 标记为在线人数，不追加到日志显示
                    
                    # 检查是否为弹幕日志（弹幕日志不在全局日志中显示，只在小号窗口显示）
                    is_danmu_log = '[弹幕]' in text
                    
                    # 追加到日志显示（在线人数和弹幕除外，弹幕只在小号窗口显示）
                    if not is_viewer_count and not is_danmu_log:
                        self.log_display.append(f"<b>[{t}]</b> <span style='color:#FFD700;'>{account_tag}</span> {text}")
                        self.log_display.moveCursor(QTextCursor.MoveOperation.End)
            
            # 获取其他已启动小号的昵称列表
            other_nicknames = self._get_other_account_nicknames(account_name)
            
            # 创建窗口关闭回调函数（立即清理窗口引用）
            def close_callback():
                """窗口关闭时的回调函数（在closeEvent中调用）"""
                try:
                    if account_name in self.account_windows:
                        print(f"    [关闭小号] closeEvent回调: 正在清理小号 '{account_name}' 的窗口引用")
                        sys.stdout.flush()
                        del self.account_windows[account_name]
                        # 更新所有已启动小号的其他小号昵称过滤器
                        self._update_all_account_nickname_filters()
                        # 添加关闭日志
                        if hasattr(self, 'log_display') and self.log_display:
                            from datetime import datetime
                            t = datetime.now().strftime("%H:%M:%S")
                            self.log_display.append(f"<b>[{t}]</b> <span style='color:#FF6B6B;'>[系统]</span> 关闭小号: {account_name}")
                            self.log_display.moveCursor(QTextCursor.MoveOperation.End)
                        print(f"    [关闭小号] 小号 '{account_name}' 已关闭，窗口引用已清理")
                        sys.stdout.flush()
                except Exception as e:
                    print(f"    [关闭小号] 回调执行出错: {e}")
                    import traceback
                    traceback.print_exc()
                    sys.stdout.flush()
            
            # 创建窗口，不设置父对象，确保独立窗口
            print(f"    [启动小号] 准备创建LiveBrowser窗口: {account_name}")
            sys.stdout.flush()
            window = LiveBrowser(self.cfg, account_data, self.config_signal, log_callback, other_nicknames, close_callback)
            print(f"    [启动小号] LiveBrowser窗口创建完成: {account_name}")
            sys.stdout.flush()
            # 确保窗口是独立的，不依赖于控制面板
            window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)  # 不自动删除，由我们手动管理
            print(f"    [启动小号] LiveBrowser创建成功")
            sys.stdout.flush()
            
            window.show()
            print(f"    [启动小号] 窗口已显示")
            sys.stdout.flush()
            
            self.account_windows[account_name] = window
            
            # 更新所有已启动小号的其他小号昵称过滤器（包括新启动的）
            self._update_all_account_nickname_filters()
            
            # 添加启动日志
            if hasattr(self, 'log_display') and self.log_display:
                from datetime import datetime
                t = datetime.now().strftime("%H:%M:%S")
                self.log_display.append(f"<b>[{t}]</b> <span style='color:#00FF00;'>[系统]</span> 启动小号: {account_name}")
                self.log_display.moveCursor(QTextCursor.MoveOperation.End)
            
            print(f"    [启动小号] ✓ 小号 '{account_name}' 启动成功")
            sys.stdout.flush()
            
            # 注意：窗口关闭时的清理工作已经在 close_callback 中处理
            # 不再需要连接 destroyed 信号，因为 closeEvent 会在窗口销毁之前调用
        except Exception as e:
            import traceback
            error_msg = f"[异常] 启动小号 '{account_name}' 失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
            print(error_msg)
            print(traceback.format_exc())
            sys.stdout.flush()
            QMessageBox.critical(self, "错误", f"启动小号 '{account_name}' 失败:\n{str(e)}")
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            QMessageBox.critical(self, "错误", error_msg + "\n\n请查看日志文件获取详细信息。")
        
    def _update_account_rule_combo(self):
        """更新规则配置下拉框中的账户列表"""
        if not hasattr(self, 'account_rule_combo'):
            return
        
        # 保存当前选中的账户
        current_data = self.account_rule_combo.currentData()
        
        # 清空并重新加载
        self.account_rule_combo.clear()
        self.account_rule_combo.addItem("全局配置（所有小号共用）", None)
        
        accounts = get_all_accounts()
        for acc in accounts:
            account_name = acc.get('name', '')
            nickname = acc.get('nickname', '')
            display_text = f"{account_name} ({nickname})"
            self.account_rule_combo.addItem(display_text, account_name)
        
        # 恢复之前选中的账户（如果还存在）
        if current_data:
            for i in range(self.account_rule_combo.count()):
                if self.account_rule_combo.itemData(i) == current_data:
                    self.account_rule_combo.setCurrentIndex(i)
                    break
    
    def _get_other_account_nicknames(self, exclude_account_name):
        """
        获取其他已启动小号的昵称列表（用于过滤其他小号的弹幕）
        
        Args:
            exclude_account_name: 要排除的账户名称
            
        Returns:
            list: 其他小号的昵称列表
        """
        nicknames = []
        accounts = get_all_accounts()
        for acc in accounts:
            acc_name = acc.get('name', '')
            if acc_name != exclude_account_name and acc_name in self.account_windows:
                nickname = acc.get('nickname', '')
                if nickname:
                    nicknames.append(nickname)
        return nicknames
    
    def _update_all_account_nickname_filters(self):
        """更新所有已启动小号的其他小号昵称过滤器"""
        for account_name, window in self.account_windows.items():
            other_nicknames = self._get_other_account_nicknames(account_name)
            if hasattr(window, 'update_other_account_nicknames'):
                window.update_other_account_nicknames(other_nicknames)
    
    def _open_account_rule_config(self):
        """为选中的小号打开独立的规则配置"""
        current_item = self.account_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "提示", "请先选择要配置的小号！")
            return
        
        account_name = current_item.data(Qt.ItemDataRole.UserRole)
        
        # 获取账户数据
        account_data = get_account(account_name)
        if not account_data:
            QMessageBox.warning(self, "错误", "小号不存在！")
            return
        
        # 创建规则配置菜单
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        
        action_reply = menu.addAction("📝 回复规则")
        action_reply.triggered.connect(lambda: self._open_account_specific_rule_manager(account_name, 'reply'))
        
        action_spec = menu.addAction("🎯 @回复规则")
        action_spec.triggered.connect(lambda: self._open_account_specific_rule_manager(account_name, 'spec'))
        
        action_warmup = menu.addAction("📢 暖场消息")
        action_warmup.triggered.connect(lambda: self._open_account_specific_rule_manager(account_name, 'warm'))
        
        action_advanced = menu.addAction("🔧 高级回复模式")
        action_advanced.triggered.connect(lambda: self._open_account_specific_rule_manager(account_name, 'advanced'))
        
        # 显示菜单
        btn = self.sender()
        if btn:
            menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        else:
            menu.exec(self.account_list.mapToGlobal(self.account_list.visualItemRect(current_item).bottomLeft()))
    
    def _open_account_specific_rule_manager(self, account_name, rule_type):
        """为指定小号打开规则管理器"""
        try:
            # 获取账户数据
            account_data = get_account(account_name)
            if not account_data:
                QMessageBox.warning(self, "错误", "小号不存在！")
                return
            
            # 确保账户数据中有配置字段
            if 'reply_rules' not in account_data:
                account_data['reply_rules'] = []
            if 'specific_rules' not in account_data:
                account_data['specific_rules'] = []
            if 'warmup_msgs' not in account_data:
                account_data['warmup_msgs'] = '欢迎来到直播间|喜欢主播点点关注'
            if 'advanced_reply_rules' not in account_data:
                account_data['advanced_reply_rules'] = []
            
            # 创建账户级别的规则管理器
            from ui_managers import BaseRuleManager, WarmupManager, AdvancedReplyManager
            if rule_type == 'reply':
                def save_reply(cfg_key, data):
                    update_account(account_name, **{cfg_key: data})
                
                win = BaseRuleManager(
                    account_data, 
                    f"回复规则设置 - {account_name}", 
                    "reply_rules",
                    account_name=account_name,
                    save_callback=save_reply
                )
            elif rule_type == 'spec':
                def save_spec(cfg_key, data):
                    update_account(account_name, **{cfg_key: data})
                
                win = BaseRuleManager(
                    account_data,
                    f"@回复规则设置 - {account_name}",
                    "specific_rules",
                    account_name=account_name,
                    save_callback=save_spec
                )
            elif rule_type == 'warm':
                def save_warmup(cfg_key, data):
                    update_account(account_name, **{cfg_key: data})
                
                win = WarmupManager(
                    account_data,
                    account_name=account_name,
                    save_callback=save_warmup
                )
            elif rule_type == 'advanced':
                def save_advanced(cfg_key, data):
                    update_account(account_name, **{cfg_key: data})
                
                win = AdvancedReplyManager(
                    account_data,
                    account_name=account_name,
                    save_callback=save_advanced
                )
            else:
                return
            
            # 存储窗口引用，防止被垃圾回收
            if not hasattr(self, '_rule_windows'):
                self._rule_windows = []
            self._rule_windows.append(win)
            
            # 当规则管理器窗口关闭时，通知对应的小号窗口更新配置
            def on_closed():
                if hasattr(self, '_rule_windows') and win in self._rule_windows:
                    self._rule_windows.remove(win)
                # 如果该小号窗口已打开，重新加载配置
                if account_name in self.account_windows:
                    window = self.account_windows[account_name]
                    if hasattr(window, 'reload_account_config'):
                        window.reload_account_config()
                print(f"    [配置更新] 小号 '{account_name}' 的规则配置已更新")
                sys.stdout.flush()
                
                # 上报关键词到服务器（异步，不阻塞UI）
                self._submit_keywords_async()
            
            win.destroyed.connect(on_closed)
            
            win.show()
            win.raise_()
            win.activateWindow()
            
        except Exception as e:
            error_msg = f"打开小号规则管理器失败: {type(e).__name__}: {e}"
            print(f"    [错误] {error_msg}")
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            QMessageBox.critical(self, "错误", error_msg + "\n\n请查看日志文件获取详细信息。")
    
    def closeEvent(self, event):
        """窗口关闭事件 - 清理所有资源"""
        try:
            print("    [退出] 开始清理资源...")
            sys.stdout.flush()
            
            # 停止所有定时器
            if hasattr(self, 'feature_auth_timer'):
                self.feature_auth_timer.stop()
            if hasattr(self, 'ban_check_timer'):
                self.ban_check_timer.stop()
            if hasattr(self, 'stats_timer'):
                self.stats_timer.stop()
            if hasattr(self, 'audio_check_timer'):
                self.audio_check_timer.stop()
            
            # 清理音频和TTS管理器
            if hasattr(self, 'audio_manager') and self.audio_manager:
                try:
                    if hasattr(self.audio_manager, 'current_player') and self.audio_manager.current_player:
                        self.audio_manager.current_player.stop()
                except:
                    pass
            
            if hasattr(self, 'tts_manager') and self.tts_manager:
                try:
                    if hasattr(self.tts_manager, 'tts_engine') and self.tts_manager.tts_engine:
                        self.tts_manager.tts_engine.stop()
                except:
                    pass
            
            # 关闭所有账户窗口
            print("    [退出] 关闭所有账户窗口...")
            sys.stdout.flush()
            for account_name, window in list(self.account_windows.items()):
                try:
                    # 先停止定时器
                    if hasattr(window, 'auto_refresh_timer') and window.auto_refresh_timer:
                        window.auto_refresh_timer.stop()
                    if hasattr(window, 'danmu_timer') and window.danmu_timer:
                        window.danmu_timer.stop()
                    
                    # 清理浏览器资源
                    if hasattr(window, 'browser') and window.browser:
                        try:
                            window.browser.stop()
                            try:
                                window.browser.page().profile().clearHttpCache()
                                window.browser.page().profile().clearAllVisitedLinks()
                            except:
                                pass
                            window.browser.setParent(None)
                        except:
                            pass
                    
                    # 关闭窗口（会触发closeEvent）
                    window.close()
                    # 不调用deleteLater()，让Qt自动管理窗口生命周期
                except Exception as e:
                    print(f"    [退出] 关闭窗口 {account_name} 时出错: {e}")
                    sys.stdout.flush()
            
            self.account_windows.clear()
            
            # 清理弹幕悬浮窗口
            if hasattr(self, 'danmu_overlay') and self.danmu_overlay:
                try:
                    self.danmu_overlay.close()
                    self.danmu_overlay.deleteLater()
                except:
                    pass
                self.danmu_overlay = None
            
            print("    [退出] 资源清理完成")
            sys.stdout.flush()
            
        except Exception as e:
            print(f"    [退出] 清理资源时出错: {e}")
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
        
        # 调用父类的closeEvent
        super().closeEvent(event)
    
    def _stop_account(self):
        """停止账户窗口"""
        current_item = self.account_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "提示", "请先选择要停止的小号！")
            return
            
        account_name = current_item.data(Qt.ItemDataRole.UserRole)
        
        if account_name in self.account_windows:
            self.account_windows[account_name].close()
            del self.account_windows[account_name]
            # 更新所有已启动小号的其他小号昵称过滤器
            self._update_all_account_nickname_filters()
            # global_logger.log("系统", f"停止小号: {account_name}")
            print(f"    [停止小号] 小号 '{account_name}' 已停止")
            sys.stdout.flush()
        else:
            QMessageBox.information(self, "提示", f"小号 '{account_name}' 的窗口未打开！")
            
    def _on_ai_role_changed(self, text):
        """AI预设角色切换处理"""
        role = self.ai_role_combo.currentData()
        
        if role == "clothing":
            # 显示服装类AI详细信息组，隐藏自定义提示词组
            self.clothing_info_group.setVisible(True)
            self.custom_prompt_group.setVisible(False)
            
            # 生成服装类AI的系统提示词
            self._update_clothing_prompt()
            
        else:  # custom
            # 显示自定义提示词组，隐藏服装类AI详细信息组
            self.clothing_info_group.setVisible(False)
            self.custom_prompt_group.setVisible(True)
            
        # 更新配置
        self._update_global_config()
    
    def _update_clothing_prompt(self):
        """更新服装类AI的系统提示词"""
        if not hasattr(self, 'edit_clothing_category'):
            return
            
        category = self.edit_clothing_category.text().strip() or "服装"
        height = self.sp_clothing_height.value()
        weight = self.sp_clothing_weight.value()
        
        system_prompt = (
            f"你是一个{category}直播间的专业导购助手，负责回复观众的弹幕。\n"
            f"重要信息：主播身高{height}cm，体重{weight}kg。\n"
            f"回复要求：\n"
            f"1. 简洁、专业、友好，通常不超过20字\n"
            f"2. 根据主播的身高体重推荐合适的尺码和款式\n"
            f"3. 回答关于{category}的问题，如材质、搭配、尺码等\n"
            f"4. 如果观众询问尺码，要结合主播的身高体重给出建议\n"
            f"5. 不要重复相同的内容，要根据上下文灵活回复\n"
            f"6. 保持热情，鼓励观众下单"
        )
        
        # 更新系统提示词（但不显示在自定义提示词框中，因为使用的是预设）
        self.cfg['ai_reply_system_prompt'] = system_prompt
    
    def _on_clothing_info_changed(self):
        """服装类AI详细信息变化时，更新系统提示词"""
        if hasattr(self, 'ai_role_combo') and self.ai_role_combo.currentData() == "clothing":
            self._update_clothing_prompt()
        self._update_global_config()
    
    def _toggle_danmu_display(self):
        """切换弹幕姬显示"""
        enabled = self.cb_danmu_display.isChecked()
        self.cfg['danmu_display_enabled'] = enabled
        
        if enabled:
            # 启动弹幕姬
            self._start_danmu_display()
        else:
            # 关闭弹幕姬
            self._stop_danmu_display()
        
        self._update_global_config()
    
    def _start_danmu_display(self):
        """启动弹幕姬（只显示悬浮窗口，复用自动回复的弹幕捕获逻辑）"""
        try:
            # 延迟导入，避免循环导入
            from danmu_display import DanmuOverlay, load_persistent_cfg as load_danmu_cfg
            from account_manager import get_all_accounts
            
            # 如果已经启动，先关闭
            if self.danmu_overlay:
                self._stop_danmu_display()
            
            # 加载弹幕姬配置
            danmu_cfg = load_danmu_cfg()
            
            # 获取所有小号的昵称列表（用于屏蔽自我发言）
            account_nicknames = []
            accounts = get_all_accounts()
            for acc in accounts:
                nickname = acc.get('nickname', '').strip()
                if nickname:
                    account_nicknames.append(nickname)
            
            # 只创建悬浮窗口（不创建浏览器控制窗口，复用自动回复的弹幕捕获逻辑）
            self.danmu_overlay = DanmuOverlay(danmu_cfg, account_nicknames=account_nicknames)
            self.danmu_overlay.show()
            
            print("    [弹幕姬] 弹幕姬悬浮窗口已启动（复用自动回复的弹幕捕获逻辑）")
            sys.stdout.flush()
        except Exception as e:
            print(f"    [弹幕姬] 启动失败: {e}")
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            QMessageBox.warning(self, "错误", f"启动弹幕姬失败: {e}\n\n请检查是否安装了必要的依赖库。")
            # 如果启动失败，取消勾选
            self.cb_danmu_display.setChecked(False)
            self.cfg['danmu_display_enabled'] = False
    
    def _stop_danmu_display(self):
        """关闭弹幕姬"""
        try:
            if self.danmu_overlay:
                # 保存窗口位置到配置文件
                try:
                    from danmu_display import save_persistent_cfg
                    save_persistent_cfg(self.danmu_overlay.cfg)
                except Exception as e:
                    print(f"    [弹幕姬] 保存位置失败: {e}")
                
                self.danmu_overlay.close()
                self.danmu_overlay = None
            
            print("    [弹幕姬] 弹幕姬已关闭")
            sys.stdout.flush()
        except Exception as e:
            print(f"    [弹幕姬] 关闭失败: {e}")
            sys.stdout.flush()
    
    def _open_ai_reply_config(self):
        """打开AI智能回复配置对话框"""
        try:
            dialog = AIReplyConfigDialog(self, self.cfg)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # 获取配置并保存
                config = dialog.get_config()
                # 更新全局配置
                self.cfg.update(config)
                # 保存到文件
                save_cfg(self.cfg)
                # 更新UI状态（如果有相关控件）
                if hasattr(self, 'cb_ai_reply'):
                    self.cb_ai_reply.setChecked(config.get('ai_reply_enabled', False))
                QMessageBox.information(self, "提示", "AI智能回复配置已保存")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开AI配置对话框失败：{str(e)}")
            traceback.print_exc()
    
    def _open_danmu_config(self):
        """打开弹幕姬配置对话框"""
        try:
            from danmu_display import load_persistent_cfg, save_persistent_cfg
            
            # 加载弹幕姬配置
            danmu_cfg = load_persistent_cfg()
            
            # 创建配置对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("弹幕悬浮窗口配置")
            dialog.setFixedSize(700, 900)  # 增加对话框大小以容纳新配置项
            
            layout = QVBoxLayout(dialog)
            layout.setSpacing(10)
            layout.setContentsMargins(15, 15, 15, 15)
            
            # 创建滚动区域以容纳所有内容
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll_widget = QWidget()
            scroll_layout = QVBoxLayout(scroll_widget)
            scroll_layout.setSpacing(10)
            scroll_layout.setContentsMargins(5, 5, 5, 5)
            
            # 基础设置组
            basic_group = QGroupBox("基础设置")
            basic_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 10px; }")
            basic_layout = QVBoxLayout()
            basic_layout.setSpacing(10)
            
            # 窗口大小
            size_row = QHBoxLayout()
            size_row.setSpacing(10)
            size_row.addWidget(QLabel("窗口宽度:"))
            sp_width = QSpinBox()
            sp_width.setRange(200, 2000)
            sp_width.setValue(danmu_cfg.get('win_w', 400))
            sp_width.setFixedWidth(80)
            size_row.addWidget(sp_width)
            
            size_row.addWidget(QLabel("窗口高度:"))
            sp_height = QSpinBox()
            sp_height.setRange(200, 3000)
            sp_height.setValue(danmu_cfg.get('win_h', 750))
            sp_height.setFixedWidth(80)
            size_row.addWidget(sp_height)
            size_row.addStretch()
            basic_layout.addLayout(size_row)
            
            # 弹幕字体
            danmu_font_row = QHBoxLayout()
            danmu_font_row.setSpacing(10)
            danmu_font_row.addWidget(QLabel("弹幕字号:"))
            sp_font = QSpinBox()
            sp_font.setRange(12, 100)
            sp_font.setValue(danmu_cfg.get('font_size', 24))
            sp_font.setFixedWidth(80)
            danmu_font_row.addWidget(sp_font)
            
            danmu_font_row.addWidget(QLabel("弹幕颜色:"))
            btn_font_color = QPushButton()
            # 使用列表来存储颜色值，避免nonlocal问题
            font_color_list = [danmu_cfg.get('font_color', '#FFFFFF')]
            btn_font_color.setStyleSheet(f"background:{font_color_list[0]}; color:black; padding:5px 15px; border:1px solid #666;")
            btn_font_color.setText("选择")
            btn_font_color.setFixedWidth(80)
            danmu_font_row.addWidget(btn_font_color)
            
            danmu_font_row.addWidget(QLabel("弹幕背景:"))
            btn_danmu_bg_color = QPushButton()
            danmu_bg_color_list = [danmu_cfg.get('danmu_bg_color', 'rgba(10,10,10,210)')]
            # 将rgba格式转换为rgb用于显示
            danmu_bg_display = danmu_bg_color_list[0]
            if danmu_bg_display.startswith('rgba'):
                import re
                match = re.search(r'rgba\((\d+),\s*(\d+),\s*(\d+),', danmu_bg_display)
                if match:
                    r, g, b = match.groups()
                    danmu_bg_display = f"#{int(r):02x}{int(g):02x}{int(b):02x}"
            btn_danmu_bg_color.setStyleSheet(f"background:{danmu_bg_display}; color:white; padding:5px 15px; border:1px solid #666;")
            btn_danmu_bg_color.setText("选择")
            btn_danmu_bg_color.setFixedWidth(80)
            danmu_font_row.addWidget(btn_danmu_bg_color)
            danmu_font_row.addStretch()
            basic_layout.addLayout(danmu_font_row)
            
            basic_group.setLayout(basic_layout)
            scroll_layout.addWidget(basic_group)
            
            # 颜色选择器
            from PyQt6.QtWidgets import QColorDialog
            from PyQt6.QtGui import QColor
            
            def pick_font_color():
                color = QColorDialog.getColor(QColor(font_color_list[0]), dialog)
                if color.isValid():
                    font_color_list[0] = color.name()
                    btn_font_color.setStyleSheet(f"background:{font_color_list[0]}; color:black; padding:5px 15px; border:1px solid #666;")
            
            def pick_danmu_bg_color():
                current_color = danmu_bg_color_list[0]
                if current_color.startswith('rgba'):
                    import re
                    match = re.search(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)', current_color)
                    if match:
                        r, g, b, a = match.groups()
                        color = QColor(int(r), int(g), int(b), int(float(a) * 255))
                    else:
                        color = QColor(10, 10, 10, 210)
                else:
                    color = QColor(current_color)
                
                color = QColorDialog.getColor(color, dialog)
                if color.isValid():
                    r, g, b, a = color.red(), color.green(), color.blue(), color.alpha()
                    danmu_bg_color_list[0] = f"rgba({r},{g},{b},{a})"
                    btn_danmu_bg_color.setStyleSheet(f"background:{color.name()}; color:white; padding:5px 15px; border:1px solid #666;")
            
            btn_font_color.clicked.connect(pick_font_color)
            btn_danmu_bg_color.clicked.connect(pick_danmu_bg_color)
            
            # 弹幕停留时间设置
            duration_group = QGroupBox("弹幕停留时间")
            duration_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 10px; }")
            duration_layout = QHBoxLayout()
            duration_layout.setSpacing(10)
            duration_layout.addWidget(QLabel("普通弹幕(秒):"))
            sp_duration_normal = QSpinBox()
            sp_duration_normal.setRange(1, 300)
            sp_duration_normal.setValue(danmu_cfg.get('duration_normal', 10))
            sp_duration_normal.setFixedWidth(80)
            duration_layout.addWidget(sp_duration_normal)
            
            duration_layout.addWidget(QLabel("置顶关键词(秒):"))
            sp_duration_pin = QSpinBox()
            sp_duration_pin.setRange(1, 300)
            sp_duration_pin.setValue(danmu_cfg.get('duration_pin', 60))
            sp_duration_pin.setFixedWidth(80)
            duration_layout.addWidget(sp_duration_pin)
            duration_layout.addStretch()
            duration_group.setLayout(duration_layout)
            scroll_layout.addWidget(duration_group)
            
            # 在线观众显示设置
            stats_pos_group = QGroupBox("在线观众显示")
            stats_pos_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 10px; }")
            stats_pos_layout = QHBoxLayout()
            stats_pos_layout.setSpacing(15)
            
            # 显示位置
            stats_pos_layout.addWidget(QLabel("显示位置:"))
            rb_stats_top = QRadioButton("置顶")
            rb_stats_bottom = QRadioButton("置底")
            stats_pos_group_btn = QButtonGroup()
            stats_pos_group_btn.addButton(rb_stats_top, 0)
            stats_pos_group_btn.addButton(rb_stats_bottom, 1)
            current_pos = danmu_cfg.get('stats_pos', 'bottom')
            if current_pos == 'top':
                rb_stats_top.setChecked(True)
            else:
                rb_stats_bottom.setChecked(True)
            stats_pos_layout.addWidget(rb_stats_top)
            stats_pos_layout.addWidget(rb_stats_bottom)
            
            # 字体大小
            stats_pos_layout.addWidget(QLabel("字体大小:"))
            sp_stats_font = QSpinBox()
            sp_stats_font.setRange(10, 100)
            sp_stats_font.setValue(danmu_cfg.get('stats_font_size', 18))
            sp_stats_font.setFixedWidth(80)
            stats_pos_layout.addWidget(sp_stats_font)
            stats_pos_layout.addStretch()
            
            stats_pos_group.setLayout(stats_pos_layout)
            scroll_layout.addWidget(stats_pos_group)
            
            # 礼物显示配置
            gift_group = QGroupBox("礼物消息配置")
            gift_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 10px; }")
            gift_layout = QVBoxLayout()
            gift_layout.setSpacing(10)
            
            # 第一行：屏蔽选项
            gift_row1 = QHBoxLayout()
            cb_block_gifts = QCheckBox("屏蔽礼物（不显示礼物消息）")
            cb_block_gifts.setChecked(danmu_cfg.get('block_gifts', False))
            cb_block_gifts.setToolTip("启用后，所有礼物消息将不显示在弹幕窗口中")
            gift_row1.addWidget(cb_block_gifts)
            gift_row1.addStretch()
            gift_layout.addLayout(gift_row1)
            
            # 第二行：字号、字体颜色、背景颜色
            gift_row2 = QHBoxLayout()
            gift_row2.setSpacing(10)
            gift_row2.addWidget(QLabel("字号:"))
            sp_gift_font = QSpinBox()
            sp_gift_font.setRange(12, 100)
            sp_gift_font.setValue(danmu_cfg.get('gift_font_size', 28))
            sp_gift_font.setFixedWidth(80)
            gift_row2.addWidget(sp_gift_font)
            
            gift_row2.addWidget(QLabel("字体颜色:"))
            btn_gift_font_color = QPushButton()
            gift_font_color_list = [danmu_cfg.get('gift_font_color', '#FFD700')]
            btn_gift_font_color.setStyleSheet(f"background:{gift_font_color_list[0]}; color:black; padding:5px 15px; border:1px solid #666;")
            btn_gift_font_color.setText("选择")
            btn_gift_font_color.setFixedWidth(80)
            gift_row2.addWidget(btn_gift_font_color)
            
            gift_row2.addWidget(QLabel("背景颜色:"))
            btn_gift_bg_color = QPushButton()
            gift_bg_color_list = [danmu_cfg.get('gift_bg_color', 'rgba(10,10,10,180)')]
            gift_bg_display = gift_bg_color_list[0]
            if gift_bg_display.startswith('rgba'):
                import re
                match = re.search(r'rgba\((\d+),\s*(\d+),\s*(\d+),', gift_bg_display)
                if match:
                    r, g, b = match.groups()
                    gift_bg_display = f"#{int(r):02x}{int(g):02x}{int(b):02x}"
            btn_gift_bg_color.setStyleSheet(f"background:{gift_bg_display}; color:white; padding:5px 15px; border:1px solid #666;")
            btn_gift_bg_color.setText("选择")
            btn_gift_bg_color.setFixedWidth(80)
            gift_row2.addWidget(btn_gift_bg_color)
            gift_row2.addStretch()
            gift_layout.addLayout(gift_row2)
            
            # 第三行：停留时间和最大数量
            gift_row3 = QHBoxLayout()
            gift_row3.setSpacing(10)
            gift_row3.addWidget(QLabel("停留时间(秒):"))
            sp_gift_duration = QSpinBox()
            sp_gift_duration.setRange(1, 300)
            sp_gift_duration.setValue(danmu_cfg.get('gift_duration', 10))
            sp_gift_duration.setFixedWidth(80)
            gift_row3.addWidget(sp_gift_duration)
            
            gift_row3.addWidget(QLabel("最大显示数量:"))
            sp_gift_max_count = QSpinBox()
            sp_gift_max_count.setRange(1, 10)
            sp_gift_max_count.setValue(danmu_cfg.get('gift_max_count', 3))
            sp_gift_max_count.setFixedWidth(80)
            sp_gift_max_count.setToolTip("限制礼物框的最大显示数量，避免覆盖弹幕")
            gift_row3.addWidget(sp_gift_max_count)
            gift_row3.addStretch()
            gift_layout.addLayout(gift_row3)
            
            gift_group.setLayout(gift_layout)
            scroll_layout.addWidget(gift_group)
            
            # 实时信息配置
            realtime_group = QGroupBox("实时信息配置")
            realtime_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 10px; }")
            realtime_layout = QVBoxLayout()
            realtime_layout.setSpacing(10)
            
            # 第一行：字号、字体颜色、背景颜色
            realtime_row1 = QHBoxLayout()
            realtime_row1.setSpacing(10)
            realtime_row1.addWidget(QLabel("字号:"))
            sp_realtime_font = QSpinBox()
            sp_realtime_font.setRange(12, 100)
            sp_realtime_font.setValue(danmu_cfg.get('realtime_font_size', 24))
            sp_realtime_font.setFixedWidth(80)
            realtime_row1.addWidget(sp_realtime_font)
            
            realtime_row1.addWidget(QLabel("字体颜色:"))
            btn_realtime_font_color = QPushButton()
            realtime_font_color_list = [danmu_cfg.get('realtime_font_color', '#FFFFFF')]
            btn_realtime_font_color.setStyleSheet(f"background:{realtime_font_color_list[0]}; color:black; padding:5px 15px; border:1px solid #666;")
            btn_realtime_font_color.setText("选择")
            btn_realtime_font_color.setFixedWidth(80)
            realtime_row1.addWidget(btn_realtime_font_color)
            
            realtime_row1.addWidget(QLabel("背景颜色:"))
            btn_realtime_bg_color = QPushButton()
            realtime_bg_color_list = [danmu_cfg.get('realtime_bg_color', 'rgba(10,10,10,180)')]
            realtime_bg_display = realtime_bg_color_list[0]
            if realtime_bg_display.startswith('rgba'):
                import re
                match = re.search(r'rgba\((\d+),\s*(\d+),\s*(\d+),', realtime_bg_display)
                if match:
                    r, g, b = match.groups()
                    realtime_bg_display = f"#{int(r):02x}{int(g):02x}{int(b):02x}"
            btn_realtime_bg_color.setStyleSheet(f"background:{realtime_bg_display}; color:white; padding:5px 15px; border:1px solid #666;")
            btn_realtime_bg_color.setText("选择")
            btn_realtime_bg_color.setFixedWidth(80)
            realtime_row1.addWidget(btn_realtime_bg_color)
            realtime_row1.addStretch()
            realtime_layout.addLayout(realtime_row1)
            
            # 第二行：轮播停留时间
            realtime_row2 = QHBoxLayout()
            realtime_row2.setSpacing(10)
            realtime_row2.addWidget(QLabel("轮播停留时间(秒):"))
            sp_realtime_duration = QSpinBox()
            sp_realtime_duration.setRange(1, 30)
            sp_realtime_duration.setValue(danmu_cfg.get('realtime_duration', 2))
            sp_realtime_duration.setFixedWidth(80)
            realtime_row2.addWidget(sp_realtime_duration)
            realtime_row2.addStretch()
            realtime_layout.addLayout(realtime_row2)
            
            realtime_group.setLayout(realtime_layout)
            scroll_layout.addWidget(realtime_group)
            
            # 定义礼物和实时信息的颜色选择函数（在所有按钮创建之后）
            def pick_gift_font_color():
                color = QColorDialog.getColor(QColor(gift_font_color_list[0]), dialog)
                if color.isValid():
                    gift_font_color_list[0] = color.name()
                    btn_gift_font_color.setStyleSheet(f"background:{gift_font_color_list[0]}; color:black; padding:5px 15px; border:1px solid #666;")
            
            def pick_gift_bg_color():
                current_color = gift_bg_color_list[0]
                if current_color.startswith('rgba'):
                    import re
                    match = re.search(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)', current_color)
                    if match:
                        r, g, b, a = match.groups()
                        color = QColor(int(r), int(g), int(b), int(float(a) * 255))
                    else:
                        color = QColor(10, 10, 10, 180)
                else:
                    color = QColor(current_color)
                
                color = QColorDialog.getColor(color, dialog)
                if color.isValid():
                    r, g, b, a = color.red(), color.green(), color.blue(), color.alpha()
                    gift_bg_color_list[0] = f"rgba({r},{g},{b},{a})"
                    btn_gift_bg_color.setStyleSheet(f"background:{color.name()}; color:white; padding:5px 15px; border:1px solid #666;")
            
            def pick_realtime_font_color():
                color = QColorDialog.getColor(QColor(realtime_font_color_list[0]), dialog)
                if color.isValid():
                    realtime_font_color_list[0] = color.name()
                    btn_realtime_font_color.setStyleSheet(f"background:{realtime_font_color_list[0]}; color:black; padding:5px 15px; border:1px solid #666;")
            
            def pick_realtime_bg_color():
                current_color = realtime_bg_color_list[0]
                if current_color.startswith('rgba'):
                    import re
                    match = re.search(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)', current_color)
                    if match:
                        r, g, b, a = match.groups()
                        color = QColor(int(r), int(g), int(b), int(float(a) * 255))
                    else:
                        color = QColor(10, 10, 10, 180)
                else:
                    color = QColor(current_color)
                
                color = QColorDialog.getColor(color, dialog)
                if color.isValid():
                    r, g, b, a = color.red(), color.green(), color.blue(), color.alpha()
                    realtime_bg_color_list[0] = f"rgba({r},{g},{b},{a})"
                    btn_realtime_bg_color.setStyleSheet(f"background:{color.name()}; color:white; padding:5px 15px; border:1px solid #666;")
            
            # 连接所有颜色选择按钮的事件
            btn_gift_font_color.clicked.connect(pick_gift_font_color)
            btn_gift_bg_color.clicked.connect(pick_gift_bg_color)
            btn_realtime_font_color.clicked.connect(pick_realtime_font_color)
            btn_realtime_bg_color.clicked.connect(pick_realtime_bg_color)
            
            # 屏蔽小号自我发言
            block_self_group = QGroupBox("屏蔽设置")
            block_self_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 10px; }")
            block_self_layout = QVBoxLayout()
            block_self_layout.setSpacing(8)
            
            cb_block_self = QCheckBox("屏蔽小号的自我发言（不显示小号自己的弹幕）")
            cb_block_self.setChecked(danmu_cfg.get('block_self_danmu', False))
            cb_block_self.setToolTip("启用后，所有小号昵称的发言将不显示在弹幕窗口中")
            block_self_layout.addWidget(cb_block_self)
            
            block_self_group.setLayout(block_self_layout)
            scroll_layout.addWidget(block_self_group)
            
            # 屏蔽自定义用户
            block_users_group = QGroupBox("屏蔽用户（昵称）")
            block_users_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 10px; }")
            block_users_layout = QVBoxLayout()
            block_users_layout.setSpacing(8)
            
            # 说明文字
            block_users_label = QLabel("这些用户的发言将不显示在弹幕窗口中")
            block_users_label.setStyleSheet("color: #888; font-size: 11px; margin-bottom: 5px;")
            block_users_layout.addWidget(block_users_label)
            
            # 用户输入和添加
            block_users_input_layout = QHBoxLayout()
            block_users_input_layout.setSpacing(8)
            block_users_input = QLineEdit()
            block_users_input.setPlaceholderText("输入用户昵称后按回车或点击添加")
            block_users_input.setStyleSheet("padding: 5px;")
            btn_add_block_user = QPushButton("添加")
            btn_add_block_user.setFixedWidth(60)
            btn_add_block_user.setStyleSheet("padding: 5px;")
            block_users_input_layout.addWidget(block_users_input, 1)
            block_users_input_layout.addWidget(btn_add_block_user)
            block_users_layout.addLayout(block_users_input_layout)
            
            # 用户列表
            block_users_list = QListWidget()
            block_users_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            block_users_list.setMaximumHeight(120)
            block_users_list.addItems(danmu_cfg.get('block_users', []))
            block_users_list.setStyleSheet("border: 1px solid #666;")
            block_users_layout.addWidget(block_users_list)
            
            # 删除按钮
            btn_del_block_user = QPushButton("删除选中")
            btn_del_block_user.setFixedHeight(30)
            btn_del_block_user.setStyleSheet("padding: 5px;")
            block_users_layout.addWidget(btn_del_block_user)
            
            block_users_group.setLayout(block_users_layout)
            scroll_layout.addWidget(block_users_group)
            
            # 置顶关键词设置
            pin_group = QGroupBox("置顶关键词")
            pin_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 10px; }")
            pin_layout = QVBoxLayout()
            pin_layout.setSpacing(8)
            
            # 说明文字
            pin_label = QLabel("包含这些关键词的弹幕会置顶显示")
            pin_label.setStyleSheet("color: #888; font-size: 11px; margin-bottom: 5px;")
            pin_layout.addWidget(pin_label)
            
            # 关键词输入和添加
            pin_input_layout = QHBoxLayout()
            pin_input_layout.setSpacing(8)
            pin_input = QLineEdit()
            pin_input.setPlaceholderText("输入关键词后按回车或点击添加")
            pin_input.setStyleSheet("padding: 5px;")
            btn_add_pin = QPushButton("添加")
            btn_add_pin.setFixedWidth(60)
            btn_add_pin.setStyleSheet("padding: 5px;")
            pin_input_layout.addWidget(pin_input, 1)
            pin_input_layout.addWidget(btn_add_pin)
            pin_layout.addLayout(pin_input_layout)
            
            # 关键词列表
            pin_list = QListWidget()
            pin_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            pin_list.setMaximumHeight(120)
            pin_list.addItems(danmu_cfg.get('pin_list', []))
            pin_list.setStyleSheet("border: 1px solid #666;")
            pin_layout.addWidget(pin_list)
            
            # 删除按钮
            btn_del_pin = QPushButton("删除选中")
            btn_del_pin.setFixedHeight(30)
            btn_del_pin.setStyleSheet("padding: 5px;")
            pin_layout.addWidget(btn_del_pin)
            
            # 置顶关键词样式设置
            pin_style_label = QLabel("置顶弹幕样式:")
            pin_style_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
            pin_layout.addWidget(pin_style_label)
            
            pin_style_layout = QHBoxLayout()
            pin_style_layout.setSpacing(10)
            pin_style_layout.addWidget(QLabel("文字颜色:"))
            btn_pin_color = QPushButton()
            pin_color_list = [danmu_cfg.get('pin_color', '#FF00FF')]
            btn_pin_color.setStyleSheet(f"background:{pin_color_list[0]}; color:black; padding:5px 15px; border:1px solid #666;")
            btn_pin_color.setText("选择")
            btn_pin_color.setFixedWidth(80)
            pin_style_layout.addWidget(btn_pin_color)
            
            pin_style_layout.addWidget(QLabel("背景颜色:"))
            btn_pin_bg_color = QPushButton()
            pin_bg_color_list = [danmu_cfg.get('pin_bg_color', 'rgba(40,0,40,240)')]
            # 将rgba格式转换为rgb用于显示
            bg_color_display = pin_bg_color_list[0]
            if bg_color_display.startswith('rgba'):
                # 提取rgba值并转换为rgb显示
                import re
                match = re.search(r'rgba\((\d+),\s*(\d+),\s*(\d+),', bg_color_display)
                if match:
                    r, g, b = match.groups()
                    bg_color_display = f"#{int(r):02x}{int(g):02x}{int(b):02x}"
            btn_pin_bg_color.setStyleSheet(f"background:{bg_color_display}; color:black; padding:5px 15px; border:1px solid #666;")
            btn_pin_bg_color.setText("选择")
            btn_pin_bg_color.setFixedWidth(80)
            pin_style_layout.addWidget(btn_pin_bg_color)
            pin_style_layout.addStretch()
            pin_layout.addLayout(pin_style_layout)
            
            # 颜色选择器
            def pick_pin_color():
                color = QColorDialog.getColor(QColor(pin_color_list[0]), dialog)
                if color.isValid():
                    pin_color_list[0] = color.name()
                    btn_pin_color.setStyleSheet(f"background:{pin_color_list[0]}; color:black; padding:5px 15px; border:1px solid #666;")
            
            def pick_pin_bg_color():
                # 先尝试解析当前颜色
                current_color = pin_bg_color_list[0]
                if current_color.startswith('rgba'):
                    import re
                    match = re.search(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)', current_color)
                    if match:
                        r, g, b, a = match.groups()
                        color = QColor(int(r), int(g), int(b), int(float(a) * 255))
                    else:
                        color = QColor(64, 0, 40, 240)
                else:
                    color = QColor(current_color)
                
                color = QColorDialog.getColor(color, dialog)
                if color.isValid():
                    # 转换为rgba格式
                    r, g, b, a = color.red(), color.green(), color.blue(), color.alpha()
                    pin_bg_color_list[0] = f"rgba({r},{g},{b},{a/255:.2f})"
                    btn_pin_bg_color.setStyleSheet(f"background:{color.name()}; color:black; padding:5px 15px; border:1px solid #666;")
            
            btn_pin_color.clicked.connect(pick_pin_color)
            btn_pin_bg_color.clicked.connect(pick_pin_bg_color)
            
            pin_group.setLayout(pin_layout)
            scroll_layout.addWidget(pin_group)
            
            # 屏蔽关键词设置
            block_group = QGroupBox("屏蔽关键词")
            block_group.setStyleSheet("QGroupBox { font-weight: bold; margin-top: 10px; }")
            block_layout = QVBoxLayout()
            block_layout.setSpacing(8)
            
            # 说明文字
            block_label = QLabel("包含这些关键词的弹幕不显示")
            block_label.setStyleSheet("color: #888; font-size: 11px; margin-bottom: 5px;")
            block_layout.addWidget(block_label)
            
            # 关键词输入和添加
            block_input_layout = QHBoxLayout()
            block_input_layout.setSpacing(8)
            block_input = QLineEdit()
            block_input.setPlaceholderText("输入关键词后按回车或点击添加")
            block_input.setStyleSheet("padding: 5px;")
            btn_add_block = QPushButton("添加")
            btn_add_block.setFixedWidth(60)
            btn_add_block.setStyleSheet("padding: 5px;")
            block_input_layout.addWidget(block_input, 1)
            block_input_layout.addWidget(btn_add_block)
            block_layout.addLayout(block_input_layout)
            
            # 关键词列表
            block_list = QListWidget()
            block_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            block_list.setMaximumHeight(120)
            block_list.addItems(danmu_cfg.get('block_list', []))
            block_list.setStyleSheet("border: 1px solid #666;")
            block_layout.addWidget(block_list)
            
            # 删除按钮
            btn_del_block = QPushButton("删除选中")
            btn_del_block.setFixedHeight(30)
            btn_del_block.setStyleSheet("padding: 5px;")
            block_layout.addWidget(btn_del_block)
            
            block_group.setLayout(block_layout)
            scroll_layout.addWidget(block_group)
            
            # 设置滚动区域
            scroll.setWidget(scroll_widget)
            layout.addWidget(scroll)
            
            # 添加/删除置顶关键词
            def add_pin():
                text = pin_input.text().strip()
                if text and text not in [pin_list.item(i).text() for i in range(pin_list.count())]:
                    pin_list.addItem(text)
                    pin_input.clear()
            
            def del_pin():
                for item in pin_list.selectedItems():
                    pin_list.takeItem(pin_list.row(item))
            
            btn_add_pin.clicked.connect(add_pin)
            pin_input.returnPressed.connect(add_pin)
            btn_del_pin.clicked.connect(del_pin)
            
            # 添加/删除屏蔽关键词
            def add_block():
                text = block_input.text().strip()
                if text and text not in [block_list.item(i).text() for i in range(block_list.count())]:
                    block_list.addItem(text)
                    block_input.clear()
            
            def del_block():
                for item in block_list.selectedItems():
                    block_list.takeItem(block_list.row(item))
            
            btn_add_block.clicked.connect(add_block)
            block_input.returnPressed.connect(add_block)
            btn_del_block.clicked.connect(del_block)
            
            # 添加/删除屏蔽用户
            def add_block_user():
                text = block_users_input.text().strip()
                if text and text not in [block_users_list.item(i).text() for i in range(block_users_list.count())]:
                    block_users_list.addItem(text)
                    block_users_input.clear()
            
            def del_block_user():
                for item in block_users_list.selectedItems():
                    block_users_list.takeItem(block_users_list.row(item))
            
            btn_add_block_user.clicked.connect(add_block_user)
            block_users_input.returnPressed.connect(add_block_user)
            btn_del_block_user.clicked.connect(del_block_user)
            
            # 按钮
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            buttons.setStyleSheet("padding: 10px;")
            layout.addWidget(buttons)
            
            # 显示对话框
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # 保存配置
                danmu_cfg['win_w'] = sp_width.value()
                danmu_cfg['win_h'] = sp_height.value()
                danmu_cfg['win_w'] = sp_width.value()
                danmu_cfg['win_h'] = sp_height.value()
                danmu_cfg['font_size'] = sp_font.value()
                danmu_cfg['font_color'] = font_color_list[0]
                danmu_cfg['danmu_bg_color'] = danmu_bg_color_list[0]
                danmu_cfg['duration_normal'] = sp_duration_normal.value()
                danmu_cfg['duration_pin'] = sp_duration_pin.value()
                danmu_cfg['pin_color'] = pin_color_list[0]
                danmu_cfg['pin_bg_color'] = pin_bg_color_list[0]
                danmu_cfg['pin_list'] = [pin_list.item(i).text() for i in range(pin_list.count())]
                danmu_cfg['block_list'] = [block_list.item(i).text() for i in range(block_list.count())]
                danmu_cfg['block_gifts'] = cb_block_gifts.isChecked()
                danmu_cfg['block_self_danmu'] = cb_block_self.isChecked()
                danmu_cfg['block_users'] = [block_users_list.item(i).text() for i in range(block_users_list.count())]
                # 保存在线观众显示位置和字体大小
                danmu_cfg['stats_pos'] = 'top' if rb_stats_top.isChecked() else 'bottom'
                danmu_cfg['stats_font_size'] = sp_stats_font.value()
                # 保存礼物配置
                danmu_cfg['gift_font_size'] = sp_gift_font.value()
                danmu_cfg['gift_font_color'] = gift_font_color_list[0]
                danmu_cfg['gift_bg_color'] = gift_bg_color_list[0]
                danmu_cfg['gift_duration'] = sp_gift_duration.value()
                danmu_cfg['gift_max_count'] = sp_gift_max_count.value()
                # 保存实时信息配置
                danmu_cfg['realtime_font_size'] = sp_realtime_font.value()
                danmu_cfg['realtime_font_color'] = realtime_font_color_list[0]
                danmu_cfg['realtime_bg_color'] = realtime_bg_color_list[0]
                danmu_cfg['realtime_duration'] = sp_realtime_duration.value()
                
                save_persistent_cfg(danmu_cfg)
                
                # 如果弹幕窗口已打开，更新配置
                if self.danmu_overlay:
                    self.danmu_overlay.cfg = danmu_cfg
                    self.danmu_overlay.refresh_window()
                
                QMessageBox.information(self, "成功", "弹幕悬浮窗口配置已保存！")
                print("    [弹幕姬] 配置已更新")
                sys.stdout.flush()
                
        except Exception as e:
            error_msg = f"打开弹幕姬配置失败: {type(e).__name__}: {e}"
            print(f"    [弹幕姬] ✗ {error_msg}")
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            QMessageBox.critical(self, "错误", error_msg + "\n\n请查看日志文件获取详细信息。")
    
    def _toggle_audio_enabled(self):
        """切换音频播放功能"""
        enabled = self.cb_audio_enabled.isChecked()
        self.cfg['audio_enabled'] = enabled
        if hasattr(self, 'audio_manager') and self.audio_manager:
            self.audio_manager.set_enabled(enabled)
        self._update_global_config()
    
    def _toggle_tts_enabled(self):
        """切换TTS文字转语音功能"""
        enabled = self.cb_tts_enabled.isChecked()
        self.cfg['tts_enabled'] = enabled
        if hasattr(self, 'tts_manager') and self.tts_manager:
            self.tts_manager.set_enabled(enabled)
        # 更新"播报所有弹幕"开关的启用状态
        if hasattr(self, 'cb_tts_speak_all'):
            self.cb_tts_speak_all.setEnabled(enabled)
            if not enabled:
                # 如果禁用TTS，也禁用"播报所有弹幕"
                self.cb_tts_speak_all.setChecked(False)
        self._update_global_config()
    
    def _toggle_tts_speak_all(self):
        """切换播报所有弹幕功能"""
        enabled = self.cb_tts_speak_all.isChecked()
        self.cfg['tts_speak_all_danmu'] = enabled
        if hasattr(self, 'tts_manager') and self.tts_manager:
            self.tts_manager.set_speak_all_danmu(enabled)
        self._update_global_config()
    
    def _on_tts_queue_timeout_changed(self, value):
        """TTS队列超时时间改变"""
        self.cfg['tts_queue_timeout'] = value
        if hasattr(self, 'tts_manager') and self.tts_manager:
            self.tts_manager.set_queue_timeout(value)
        self._update_global_config()
    
    def _refresh_audio_rules(self):
        """刷新音频规则列表"""
        # 从管理器直接获取规则（更可靠）
        keyword_rules = []
        timer_rules = []
        
        if hasattr(self, 'audio_manager') and self.audio_manager:
            # 从管理器获取规则
            keyword_rules = [rule.to_dict() for rule in self.audio_manager.keyword_rules]
            timer_rules = self.audio_manager.timer_rules.copy()
        else:
            # 如果管理器未初始化，从配置读取
            keyword_rules = self.cfg.get('audio_keyword_rules', [])
            timer_rules = self.cfg.get('audio_timer_rules', [])
        
        # 刷新关键词规则表格
        if hasattr(self, 'keyword_table'):
            self.keyword_table.setRowCount(len(keyword_rules))
            
            for row, rule in enumerate(keyword_rules):
                keyword = rule.get('keyword', '')
                audio_file = rule.get('audio_file', '')
                match_mode = rule.get('match_mode', 'contains')
                play_mode = rule.get('play_mode', '随机挑一')
                
                # 匹配模式显示
                mode_map = {"contains": "包含", "exact": "精确", "regex": "正则"}
                mode_display = mode_map.get(match_mode, match_mode)
                
                # 播放模式显示
                play_mode_display = play_mode if play_mode in ["随机挑一", "顺序全发"] else "随机挑一"
                
                # 音频文件名（如果有多个文件，显示数量）
                if "|" in audio_file:
                    files = [f.strip() for f in audio_file.split("|") if f.strip()]
                    audio_name = f"{len(files)}个文件 ({os.path.basename(files[0])}...)" if files else '未设置'
                else:
                    audio_name = os.path.basename(audio_file) if audio_file else '未设置'
                
                # 设置表格项
                self.keyword_table.setItem(row, 0, QTableWidgetItem(keyword))
                self.keyword_table.setItem(row, 1, QTableWidgetItem(mode_display))
                self.keyword_table.setItem(row, 2, QTableWidgetItem(play_mode_display))
                self.keyword_table.setItem(row, 3, QTableWidgetItem(audio_name))
                
                # 测试按钮
                btn_test = QPushButton("🔊 测试")
                btn_test.setMaximumWidth(80)
                btn_test.clicked.connect(lambda checked, idx=row: self._test_keyword_audio_by_index(idx))
                self.keyword_table.setCellWidget(row, 4, btn_test)
        
        # 刷新定时规则表格
        if hasattr(self, 'timer_table'):
            self.timer_table.setRowCount(len(timer_rules))
            
            for row, rule in enumerate(timer_rules):
                interval = rule.get('interval', 0)
                audio_file = rule.get('audio_file', '')
                interval_str = self._format_interval(interval)
                audio_name = os.path.basename(audio_file) if audio_file else '未设置'
                
                # 设置表格项
                self.timer_table.setItem(row, 0, QTableWidgetItem(interval_str))
                self.timer_table.setItem(row, 1, QTableWidgetItem(audio_name))
                
                # 测试按钮
                btn_test = QPushButton("🔊 测试")
                btn_test.setMaximumWidth(80)
                btn_test.clicked.connect(lambda checked, idx=row: self._test_timer_audio_by_index(idx))
                self.timer_table.setCellWidget(row, 2, btn_test)
    
    def _refresh_tts_rules(self):
        """刷新TTS规则列表"""
        # 从管理器直接获取规则（更可靠）
        tts_rules = []
        
        if hasattr(self, 'tts_manager') and self.tts_manager:
            # 从管理器获取规则
            tts_rules = [rule.to_dict() for rule in self.tts_manager.tts_rules]
        else:
            # 如果管理器未初始化，从配置读取
            tts_rules = self.cfg.get('tts_rules', [])
        
        if hasattr(self, 'tts_table'):
            self.tts_table.setRowCount(len(tts_rules))
            
            for row, rule in enumerate(tts_rules):
                keyword = rule.get('keyword', '')
                match_mode = rule.get('match_mode', 'contains')
                tts_text = rule.get('tts_text', '')
                
                # 匹配模式显示
                mode_map = {"contains": "包含", "exact": "精确", "regex": "正则"}
                mode_display = mode_map.get(match_mode, match_mode)
                
                # 播报内容显示
                if tts_text:
                    tts_display = tts_text[:30] + "..." if len(tts_text) > 30 else tts_text
                else:
                    tts_display = "完整弹幕内容"
                
                # 设置表格项
                self.tts_table.setItem(row, 0, QTableWidgetItem(keyword))
                self.tts_table.setItem(row, 1, QTableWidgetItem(mode_display))
                self.tts_table.setItem(row, 2, QTableWidgetItem(tts_display))
                
                # 测试按钮
                btn_test = QPushButton("🔊 测试")
                btn_test.setMaximumWidth(80)
                btn_test.clicked.connect(lambda checked, idx=row: self._test_tts_rule_by_index(idx))
                self.tts_table.setCellWidget(row, 3, btn_test)
    
    def _add_tts_rule(self):
        """添加TTS规则"""
        try:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox
            from PyQt6.QtWidgets import QPushButton, QDialogButtonBox
            
            dialog = QDialog(self)
            dialog.setWindowTitle("添加TTS规则")
            dialog.setMinimumWidth(500)
            layout = QVBoxLayout(dialog)
            
            # 关键词输入
            keyword_layout = QHBoxLayout()
            keyword_layout.addWidget(QLabel("关键词:"))
            keyword_input = QLineEdit()
            keyword_input.setPlaceholderText("输入触发关键词")
            keyword_layout.addWidget(keyword_input)
            layout.addLayout(keyword_layout)
            
            # 匹配模式
            mode_layout = QHBoxLayout()
            mode_layout.addWidget(QLabel("匹配模式:"))
            mode_combo = QComboBox()
            mode_combo.addItems(["包含", "精确", "正则"])
            mode_combo.setCurrentIndex(0)
            mode_layout.addWidget(mode_combo)
            layout.addLayout(mode_layout)
            
            # 播报内容
            tts_text_layout = QVBoxLayout()
            tts_text_layout.addWidget(QLabel("播报内容:"))
            tts_text_input = QLineEdit()
            tts_text_input.setPlaceholderText("留空则播报完整弹幕内容，或输入自定义文字")
            tts_text_layout.addWidget(tts_text_input)
            layout.addLayout(tts_text_layout)
            
            # 说明
            desc_label = QLabel("💡 提示：如果播报内容留空，将播报完整的弹幕内容；如果填写了自定义内容，则播报自定义内容。")
            desc_label.setStyleSheet("color: #888; font-size: 10px; padding: 5px;")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)
            
            # 按钮
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                keyword = keyword_input.text().strip()
                tts_text = tts_text_input.text().strip()
                mode_index = mode_combo.currentIndex()
                match_mode = ["contains", "exact", "regex"][mode_index]
                
                if not keyword:
                    QMessageBox.warning(self, "错误", "请输入关键词！")
                    return
                
                if hasattr(self, 'tts_manager') and self.tts_manager:
                    if self.tts_manager.add_tts_rule(keyword, match_mode, tts_text):
                        self._refresh_tts_rules()
                        QMessageBox.information(self, "成功", "TTS规则已添加！")
                    else:
                        QMessageBox.warning(self, "错误", "添加失败，可能规则已存在！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"添加TTS规则失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _remove_tts_rule(self):
        """删除TTS规则"""
        if not hasattr(self, 'tts_table'):
            return
        
        current_row = self.tts_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的规则！")
            return
        
        if hasattr(self, 'tts_manager') and self.tts_manager:
            if self.tts_manager.remove_tts_rule(current_row):
                self._refresh_tts_rules()
                QMessageBox.information(self, "成功", "TTS规则已删除！")
            else:
                QMessageBox.warning(self, "错误", "删除失败！")
    
    def _test_tts_rule(self):
        """测试选中的TTS规则"""
        if not hasattr(self, 'tts_table'):
            return
        
        current_row = self.tts_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要测试的规则！")
            return
        
        self._test_tts_rule_by_index(current_row)
    
    def _test_tts_rule_by_index(self, index: int):
        """通过索引测试TTS规则"""
        try:
            tts_rules = self.cfg.get('tts_rules', [])
            if 0 <= index < len(tts_rules):
                rule = tts_rules[index]
                tts_text = rule.get('tts_text', '')
                
                # 确定测试文字
                if tts_text:
                    test_text = tts_text
                else:
                    test_text = "这是一条测试弹幕，用于测试TTS文字转语音功能。"
                
                if hasattr(self, 'tts_manager') and self.tts_manager and self.tts_manager.tts_engine:
                    self.tts_manager.tts_engine.speak(test_text)
                    QMessageBox.information(self, "成功", f"正在使用TTS播报（测试）:\n{test_text[:50]}...")
                else:
                    QMessageBox.warning(self, "错误", "TTS引擎未初始化或不可用！\n请安装pyttsx3: pip install pyttsx3")
            else:
                QMessageBox.warning(self, "错误", "规则索引无效！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _refresh_tts_block_keywords(self):
        """刷新TTS屏蔽关键词列表"""
        if hasattr(self, 'tts_block_list'):
            # 从管理器直接获取屏蔽关键词
            block_keywords = []
            if hasattr(self, 'tts_manager') and self.tts_manager:
                block_keywords = list(self.tts_manager.block_keywords)
            else:
                block_keywords = self.cfg.get('tts_block_keywords', [])
            
            self.tts_block_list.clear()
            for keyword in block_keywords:
                self.tts_block_list.addItem(keyword)
    
    def _add_tts_block_keyword(self):
        """添加TTS屏蔽关键词"""
        try:
            from PyQt6.QtWidgets import QInputDialog
            keyword, ok = QInputDialog.getText(
                self,
                "添加屏蔽关键词",
                "请输入要屏蔽的关键词：",
                text=""
            )
            
            if ok and keyword:
                keyword = keyword.strip()
                if not keyword:
                    QMessageBox.warning(self, "错误", "关键词不能为空！")
                    return
                
                if hasattr(self, 'tts_manager') and self.tts_manager:
                    if self.tts_manager.add_block_keyword(keyword):
                        self._refresh_tts_block_keywords()
                        QMessageBox.information(self, "成功", "屏蔽关键词已添加！")
                    else:
                        QMessageBox.warning(self, "错误", "添加失败，可能关键词已存在！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"添加屏蔽关键词失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _remove_tts_block_keyword(self):
        """删除TTS屏蔽关键词"""
        if not hasattr(self, 'tts_block_list'):
            return
        
        current_row = self.tts_block_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的关键词！")
            return
        
        if hasattr(self, 'tts_manager') and self.tts_manager:
            if self.tts_manager.remove_block_keyword(current_row):
                self._refresh_tts_block_keywords()
                QMessageBox.information(self, "成功", "屏蔽关键词已删除！")
            else:
                QMessageBox.warning(self, "错误", "删除失败！")
    
    def _format_interval(self, seconds):
        """格式化时间间隔"""
        if seconds < 60:
            return f"{seconds}秒"
        elif seconds < 3600:
            return f"{seconds // 60}分钟"
        else:
            hours = seconds // 3600
            mins = (seconds % 3600) // 60
            if mins > 0:
                return f"{hours}小时{mins}分钟"
            return f"{hours}小时"
    
    def _add_keyword_rule(self):
        """添加关键词规则"""
        try:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox
            from PyQt6.QtWidgets import QPushButton, QDialogButtonBox
            
            dialog = QDialog(self)
            dialog.setWindowTitle("添加关键词规则")
            dialog.setMinimumWidth(500)
            layout = QVBoxLayout(dialog)
            
            # 关键词输入
            keyword_layout = QHBoxLayout()
            keyword_layout.addWidget(QLabel("关键词:"))
            keyword_input = QLineEdit()
            keyword_input.setPlaceholderText("输入触发关键词")
            keyword_layout.addWidget(keyword_input)
            layout.addLayout(keyword_layout)
            
            # 匹配模式
            mode_layout = QHBoxLayout()
            mode_layout.addWidget(QLabel("匹配模式:"))
            mode_combo = QComboBox()
            mode_combo.addItems(["包含", "精确", "正则"])
            mode_combo.setCurrentIndex(0)
            mode_layout.addWidget(mode_combo)
            layout.addLayout(mode_layout)
            
            # 播放模式
            play_mode_layout = QHBoxLayout()
            play_mode_layout.addWidget(QLabel("播放模式:"))
            play_mode_combo = QComboBox()
            play_mode_combo.addItems(["随机挑一", "顺序全发"])
            play_mode_combo.setCurrentIndex(0)
            play_mode_combo.setToolTip("随机挑一：随机选一个音频播放\n顺序全发：按顺序播放所有音频（多个文件用|分隔）")
            play_mode_layout.addWidget(play_mode_combo)
            layout.addLayout(play_mode_layout)
            
            # 音频文件选择（支持多个文件，用|分隔）
            audio_layout = QVBoxLayout()
            audio_label_layout = QHBoxLayout()
            audio_label_layout.addWidget(QLabel("音频文件:"))
            audio_label_layout.addWidget(QLabel("（多个文件用 | 分隔，顺序全发模式下会按顺序播放）"))
            audio_label_layout.addStretch()
            audio_layout.addLayout(audio_label_layout)
            
            audio_input_layout = QHBoxLayout()
            audio_input = QLineEdit()
            audio_input.setPlaceholderText("选择音频文件（支持多个文件，用|分隔）...")
            audio_input_layout.addWidget(audio_input)
            btn_browse = QPushButton("浏览...")
            btn_browse_multi = QPushButton("添加多个...")
            
            def browse_audio():
                file_path, _ = QFileDialog.getOpenFileName(
                    dialog, "选择音频文件", "", 
                    "音频文件 (*.mp3 *.wav *.ogg *.m4a);;所有文件 (*)"
                )
                if file_path:
                    current_text = audio_input.text().strip()
                    if current_text:
                        audio_input.setText(current_text + "|" + file_path)
                    else:
                        audio_input.setText(file_path)
            
            def browse_multi_audio():
                file_paths, _ = QFileDialog.getOpenFileNames(
                    dialog, "选择多个音频文件", "", 
                    "音频文件 (*.mp3 *.wav *.ogg *.m4a);;所有文件 (*)"
                )
                if file_paths:
                    audio_input.setText("|".join(file_paths))
            
            btn_browse.clicked.connect(browse_audio)
            btn_browse_multi.clicked.connect(browse_multi_audio)
            audio_input_layout.addWidget(btn_browse)
            audio_input_layout.addWidget(btn_browse_multi)
            audio_layout.addLayout(audio_input_layout)
            layout.addLayout(audio_layout)
            
            # 按钮
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                keyword = keyword_input.text().strip()
                audio_file = audio_input.text().strip()
                mode_index = mode_combo.currentIndex()
                match_mode = ["contains", "exact", "regex"][mode_index]
                play_mode = play_mode_combo.currentText()  # "随机挑一" 或 "顺序全发"
                
                if not keyword or not audio_file:
                    QMessageBox.warning(self, "错误", "请填写完整信息！")
                    return
                
                # 检查音频文件是否存在（支持多个文件）
                audio_files = [f.strip() for f in audio_file.split("|") if f.strip()]
                if not audio_files:
                    QMessageBox.warning(self, "错误", "请至少选择一个音频文件！")
                    return
                
                # 检查所有文件是否存在
                missing_files = [f for f in audio_files if not os.path.exists(f)]
                if missing_files:
                    QMessageBox.warning(self, "错误", f"以下音频文件不存在：\n" + "\n".join(missing_files[:5]))
                    return
                
                if hasattr(self, 'audio_manager') and self.audio_manager:
                    if self.audio_manager.add_keyword_rule(keyword, audio_file, match_mode, play_mode):
                        self._refresh_audio_rules()
                        QMessageBox.information(self, "成功", "关键词规则已添加！")
                    else:
                        QMessageBox.warning(self, "错误", "添加失败，可能规则已存在或文件不存在！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"添加关键词规则失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _remove_keyword_rule(self):
        """删除关键词规则"""
        if not hasattr(self, 'keyword_table'):
            return
        
        current_row = self.keyword_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的规则！")
            return
        
        if hasattr(self, 'audio_manager') and self.audio_manager:
            if self.audio_manager.remove_keyword_rule(current_row):
                self._refresh_audio_rules()
                QMessageBox.information(self, "成功", "关键词规则已删除！")
            else:
                QMessageBox.warning(self, "错误", "删除失败！")
    
    def _test_keyword_audio(self):
        """测试选中的关键词规则音频"""
        if not hasattr(self, 'keyword_table'):
            return
        
        current_row = self.keyword_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要测试的规则！")
            return
        
        self._test_keyword_audio_by_index(current_row)
    
    def _test_keyword_audio_by_index(self, index: int):
        """通过索引测试关键词规则音频"""
        try:
            keyword_rules = self.cfg.get('audio_keyword_rules', [])
            if 0 <= index < len(keyword_rules):
                rule = keyword_rules[index]
                audio_file = rule.get('audio_file', '')
                play_mode = rule.get('play_mode', '随机挑一')
                
                # 获取音频文件列表（支持多个文件）
                if "|" in audio_file:
                    audio_files = [f.strip() for f in audio_file.split("|") if f.strip()]
                else:
                    audio_files = [audio_file] if audio_file else []
                
                if not audio_files:
                    QMessageBox.warning(self, "错误", "音频文件未设置！")
                    return
                
                # 检查文件是否存在
                missing_files = [f for f in audio_files if not os.path.exists(f)]
                if missing_files:
                    QMessageBox.warning(self, "错误", f"以下音频文件不存在：\n" + "\n".join(missing_files[:5]))
                    return
                
                if hasattr(self, 'audio_manager') and self.audio_manager:
                    # 测试播放第一个文件（或根据播放模式选择）
                    import random
                    if play_mode == "随机挑一":
                        test_file = random.choice(audio_files)
                    else:
                        test_file = audio_files[0]
                    
                    if self.audio_manager.test_play_audio(test_file):
                        if len(audio_files) > 1:
                            QMessageBox.information(self, "成功", f"正在播放音频（测试）:\n{os.path.basename(test_file)}\n\n共{len(audio_files)}个文件，播放模式: {play_mode}")
                        else:
                            QMessageBox.information(self, "成功", f"正在播放音频:\n{os.path.basename(test_file)}")
                    else:
                        QMessageBox.warning(self, "错误", "音频播放失败，请检查音频文件是否有效！")
                else:
                    QMessageBox.warning(self, "错误", "音频管理器未初始化！")
            else:
                QMessageBox.warning(self, "错误", "规则索引无效！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _add_timer_rule(self):
        """添加定时播放规则"""
        try:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox
            
            dialog = QDialog(self)
            dialog.setWindowTitle("添加定时播放规则")
            dialog.setMinimumWidth(500)
            layout = QVBoxLayout(dialog)
            
            # 时间间隔输入
            interval_layout = QHBoxLayout()
            interval_layout.addWidget(QLabel("播放间隔:"))
            
            # 小时、分钟、秒
            hours_spin = QSpinBox()
            hours_spin.setRange(0, 23)
            hours_spin.setValue(0)
            interval_layout.addWidget(QLabel("小时:"))
            interval_layout.addWidget(hours_spin)
            
            mins_spin = QSpinBox()
            mins_spin.setRange(0, 59)
            mins_spin.setValue(5)
            interval_layout.addWidget(QLabel("分钟:"))
            interval_layout.addWidget(mins_spin)
            
            secs_spin = QSpinBox()
            secs_spin.setRange(0, 59)
            secs_spin.setValue(0)
            interval_layout.addWidget(QLabel("秒:"))
            interval_layout.addWidget(secs_spin)
            layout.addLayout(interval_layout)
            
            # 音频文件选择
            audio_layout = QHBoxLayout()
            audio_layout.addWidget(QLabel("音频文件:"))
            audio_input = QLineEdit()
            audio_input.setPlaceholderText("选择音频文件...")
            audio_input.setReadOnly(True)
            audio_layout.addWidget(audio_input)
            btn_browse = QPushButton("浏览...")
            def browse_audio():
                file_path, _ = QFileDialog.getOpenFileName(
                    dialog, "选择音频文件", "", 
                    "音频文件 (*.mp3 *.wav *.ogg *.m4a);;所有文件 (*)"
                )
                if file_path:
                    audio_input.setText(file_path)
            btn_browse.clicked.connect(browse_audio)
            audio_layout.addWidget(btn_browse)
            layout.addLayout(audio_layout)
            
            # 按钮
            from PyQt6.QtWidgets import QDialogButtonBox
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                hours = hours_spin.value()
                mins = mins_spin.value()
                secs = secs_spin.value()
                interval = hours * 3600 + mins * 60 + secs
                audio_file = audio_input.text().strip()
                
                if interval <= 0:
                    QMessageBox.warning(self, "错误", "播放间隔必须大于0！")
                    return
                
                if not audio_file:
                    QMessageBox.warning(self, "错误", "请选择音频文件！")
                    return
                
                if not os.path.exists(audio_file):
                    QMessageBox.warning(self, "错误", "音频文件不存在！")
                    return
                
                if hasattr(self, 'audio_manager') and self.audio_manager:
                    if self.audio_manager.add_timer_rule(interval, audio_file):
                        self._refresh_audio_rules()
                        QMessageBox.information(self, "成功", "定时播放规则已添加！")
                    else:
                        QMessageBox.warning(self, "错误", "添加失败！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"添加定时播放规则失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _remove_timer_rule(self):
        """删除定时播放规则"""
        if not hasattr(self, 'timer_table'):
            return
        
        current_row = self.timer_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的规则！")
            return
        
        if hasattr(self, 'audio_manager') and self.audio_manager:
            if self.audio_manager.remove_timer_rule(current_row):
                self._refresh_audio_rules()
                QMessageBox.information(self, "成功", "定时播放规则已删除！")
            else:
                QMessageBox.warning(self, "错误", "删除失败！")
    
    def _test_timer_audio(self):
        """测试选中的定时规则音频"""
        if not hasattr(self, 'timer_table'):
            return
        
        current_row = self.timer_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要测试的规则！")
            return
        
        self._test_timer_audio_by_index(current_row)
    
    def _test_timer_audio_by_index(self, index: int):
        """通过索引测试定时规则音频"""
        try:
            timer_rules = self.cfg.get('audio_timer_rules', [])
            if 0 <= index < len(timer_rules):
                rule = timer_rules[index]
                audio_file = rule.get('audio_file', '')
                if audio_file and os.path.exists(audio_file):
                    if hasattr(self, 'audio_manager') and self.audio_manager:
                        if self.audio_manager.test_play_audio(audio_file):
                            QMessageBox.information(self, "成功", f"正在播放音频:\n{os.path.basename(audio_file)}")
                        else:
                            QMessageBox.warning(self, "错误", "音频播放失败，请检查音频文件是否有效！")
                    else:
                        QMessageBox.warning(self, "错误", "音频管理器未初始化！")
                else:
                    QMessageBox.warning(self, "错误", f"音频文件不存在:\n{audio_file}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"测试音频失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _check_audio_timers(self):
        """检查定时播放规则"""
        if hasattr(self, 'audio_manager') and self.audio_manager:
            self.audio_manager.check_timer_rules()
    
    def _on_danmu_for_audio(self, data):
        """处理弹幕信号，用于音频播放"""
        try:
            if hasattr(self, 'audio_manager') and self.audio_manager:
                data_type = data.get('type', 'danmu')
                if data_type == 'danmu':
                    content = data.get('content', '').strip()
                    if content:
                        self.audio_manager.process_danmu(content)
        except Exception as e:
            print(f"    [音频播放] 处理弹幕信号失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_danmu_for_tts(self, data):
        """处理弹幕信号，用于TTS播报"""
        try:
            if hasattr(self, 'tts_manager') and self.tts_manager:
                data_type = data.get('type', 'danmu')
                # 只处理弹幕类型的消息，过滤礼物等其他类型
                if data_type == 'danmu':
                    user = data.get('user', '').strip()
                    content = data.get('content', '').strip()
                    if content:
                        # 传递用户昵称和内容
                        self.tts_manager.process_danmu(content, user)
        except Exception as e:
            print(f"    [TTS播报] 处理弹幕信号失败: {e}")
            import traceback
            traceback.print_exc()
            
    def _update_global_config(self):
        """更新全局配置"""
        self.cfg['reply_interval'] = self.sp_interval.value()
        self.cfg['random_jitter'] = self.sp_jitter.value()
        self.cfg['auto_reply_enabled'] = self.cb_reply.isChecked()
        # 注意：授权相关的开关状态不保存到本地配置文件，但需要在内存中更新以便传递给子窗口
        # 这些状态完全由服务器授权决定，只在内存中更新，不持久化
        if hasattr(self, 'cb_specific') and self.cb_specific.isEnabled():
            self.cfg['specific_reply_enabled'] = self.cb_specific.isChecked()
        if hasattr(self, 'cb_advanced') and self.cb_advanced.isEnabled():
            self.cfg['advanced_reply_enabled'] = self.cb_advanced.isChecked()
        if hasattr(self, 'cb_warmup') and self.cb_warmup.isEnabled():
            self.cfg['warmup_enabled'] = self.cb_warmup.isChecked()
        if hasattr(self, 'cb_command') and self.cb_command.isEnabled():
            self.cfg['command_enabled'] = self.cb_command.isChecked()
        self.cfg['hide_web'] = self.cb_hide.isChecked()
        self.cfg['random_space_insert_enabled'] = self.cb_random_space.isChecked()
        self.cfg['danmu_display_enabled'] = self.cb_danmu_display.isChecked()
        # command_user 和 command_silent_mode 可以保存，因为它们不是授权相关的，只是功能配置
        self.cfg['command_user'] = self.edit_command_user.text().strip()
        self.cfg['command_silent_mode'] = self.cb_command_silent.isChecked()
        
        # AI回复配置现在在独立对话框中保存，这里不再保存
        
        # 注意：授权相关的开关状态（specific_reply_enabled, advanced_reply_enabled, 
        # warmup_enabled, command_enabled）不保存到本地配置文件
        # 这些状态完全由服务器授权决定，只在内存中更新，用于传递给子窗口
        # 每次启动时都会从服务器重新获取授权状态
        
        # 更新队列配置（转换模式名称，从单选按钮获取）
        mode_map = {"轮流": "轮询", "优先": "优先级", "随机": "随机", "先到先得": "第一个可用"}
        # 获取当前选中的单选按钮
        ui_mode = None
        for mode_text, radio in self.queue_mode_radios.items():
            if radio.isChecked():
                ui_mode = mode_text
                break
        if not ui_mode:
            ui_mode = "轮流"  # 默认值
        cfg_mode = mode_map.get(ui_mode, "轮询")
        self.cfg['queue_mode'] = cfg_mode
        self.cfg['queue_time_window'] = self.sp_queue_window.value()
        self.cfg['queue_lock_timeout'] = self.sp_queue_timeout.value()
        
        # 根据单选按钮状态设置回复模式
        self.cfg['allow_multiple_reply'] = self.rb_multiple_reply.isChecked()
        # 单回复模式下，strict_single_reply 始终为 True（确保严格单回复）
        self.cfg['strict_single_reply'] = True  # 单回复模式下始终启用严格模式
        
        self.cfg['auto_cleanup_locks'] = self.cb_auto_cleanup.isChecked()
        
        # 初始化账户优先级配置（如果不存在）
        if 'account_priorities' not in self.cfg:
            self.cfg['account_priorities'] = {}
        
        # 保存授权功能的开关状态到独立的配置字段（用于记忆状态）
        # 这些状态只在已授权的情况下保存，用于下次启动时恢复
        auth_feature_states = {}
        if hasattr(self, 'cb_specific') and self.cb_specific.isEnabled():
            auth_feature_states['specific_reply_enabled'] = self.cb_specific.isChecked()
        if hasattr(self, 'cb_advanced') and self.cb_advanced.isEnabled():
            auth_feature_states['advanced_reply_enabled'] = self.cb_advanced.isChecked()
        if hasattr(self, 'cb_warmup') and self.cb_warmup.isEnabled():
            auth_feature_states['warmup_enabled'] = self.cb_warmup.isChecked()
        if hasattr(self, 'cb_command') and self.cb_command.isEnabled():
            auth_feature_states['command_enabled'] = self.cb_command.isChecked()
        
        # 保存授权功能的开关状态到配置文件（用于记忆）
        if auth_feature_states:
            self.cfg['auth_feature_states'] = auth_feature_states
        
        # 保存配置前，临时移除授权相关字段（这些字段不应该保存到本地文件）
        # 这些字段只在内存中更新，完全由服务器授权状态控制
        auth_fields_to_remove = ['specific_reply_enabled', 'advanced_reply_enabled', 'warmup_enabled', 'command_enabled']
        saved_auth_values = {}
        for field in auth_fields_to_remove:
            if field in self.cfg:
                saved_auth_values[field] = self.cfg[field]
                del self.cfg[field]
        
        # 保存配置（不包含授权相关字段，但包含auth_feature_states用于记忆）
        save_cfg(self.cfg)
        
        # 恢复授权字段到内存中的配置（用于传递给子窗口，但不持久化）
        for field, value in saved_auth_values.items():
            self.cfg[field] = value
        
        # 更新全局队列配置
        global_queue.set_queue_mode(self.cfg['queue_mode'])
        global_queue.set_time_window(self.cfg['queue_time_window'])
        global_queue.set_lock_timeout(self.cfg['queue_lock_timeout'])
        # 单回复模式下，strict_single_reply 始终为 True
        global_queue.set_strict_single_reply(True)  # 单回复模式始终启用严格模式
        global_queue.set_auto_cleanup(self.cfg['auto_cleanup_locks'])
        global_queue.set_allow_multiple_reply(self.cfg.get('allow_multiple_reply', False))
        
        # 更新账户优先级
        account_priorities = self.cfg.get('account_priorities', {})
        for account_name, priority in account_priorities.items():
            global_queue.set_account_priority(account_name, priority)
        
        # 保存配置到文件（但不保存授权相关的开关状态）
        save_cfg_dict = self.cfg.copy()
        # 移除授权相关的字段，不保存到文件
        save_cfg_dict.pop('specific_reply_enabled', None)
        save_cfg_dict.pop('advanced_reply_enabled', None)
        save_cfg_dict.pop('warmup_enabled', None)
        save_cfg_dict.pop('command_enabled', None)
        save_cfg(save_cfg_dict)
        
        # 通知所有已打开的账户窗口更新配置
        # 注意：这里发送完整的配置（包括授权相关字段），用于传递给子窗口
        self.config_signal.config_updated.emit(self.cfg.copy())
        # global_logger.log("系统", "全局配置已更新")
        print("    [配置更新] 全局配置已更新")
        sys.stdout.flush()
        
        # 上报关键词到服务器（异步，不阻塞UI）
        self._submit_keywords_async()
    
    def _submit_keywords_async(self):
        """异步提交关键词到服务器"""
        def submit():
            try:
                submit_keywords()
            except Exception as e:
                # 静默失败，不影响UI
                pass
        
        # 在后台线程中执行提交
        thread = threading.Thread(target=submit, daemon=True)
        thread.start()
    
    def _check_feature_auth(self):
        """检查功能授权状态（异步，支持CDK和服务器授权）"""
        # 使用新的合并授权检查方法
        self._check_feature_auth_with_cdk()
    
    def _update_feature_auth_ui(self, auth_result):
        """根据授权状态更新UI（在主线程中调用）"""
        try:
            print(f"    [更新UI状态] 开始更新，授权结果: {auth_result}")
            sys.stdout.flush()
            self.feature_auth = auth_result
            
            # 从服务器授权状态更新内存中的配置（但不保存到文件）
            # 这样 main_window.py 可以读取到正确的授权状态
            specific_enabled = auth_result.get("specific_reply", False)
            advanced_enabled = auth_result.get("advanced_reply", False)
            warmup_enabled = auth_result.get("warmup", False)
            command_enabled = auth_result.get("command", False)
            
            # 从配置文件加载之前保存的开关状态（如果存在）
            saved_states = self.cfg.get('auth_feature_states', {})
            
            # 更新内存中的配置（不持久化）
            # 如果已授权，则从保存的状态中恢复开关状态；如果未授权，则设置为False
            if specific_enabled:
                self.cfg['specific_reply_enabled'] = saved_states.get('specific_reply_enabled', False)
            else:
                self.cfg['specific_reply_enabled'] = False
                
            if advanced_enabled:
                self.cfg['advanced_reply_enabled'] = saved_states.get('advanced_reply_enabled', False)
            else:
                self.cfg['advanced_reply_enabled'] = False
                
            if warmup_enabled:
                self.cfg['warmup_enabled'] = saved_states.get('warmup_enabled', False)
            else:
                self.cfg['warmup_enabled'] = False
                
            if command_enabled:
                self.cfg['command_enabled'] = saved_states.get('command_enabled', False)
            else:
                self.cfg['command_enabled'] = False
            
            # @回复功能
            if hasattr(self, 'cb_specific'):
                print(f"    [更新UI状态] @回复功能: {'已授权' if specific_enabled else '未授权'}")
                if specific_enabled:
                    # 已授权：启用开关，移除灰色样式，恢复之前保存的状态
                    self.cb_specific.setEnabled(True)
                    self.cb_specific.setStyleSheet("")
                    saved_state = saved_states.get('specific_reply_enabled', False)
                    self.cb_specific.setChecked(saved_state)
                    self.cfg['specific_reply_enabled'] = saved_state
                    print(f"    [更新UI状态] @回复功能开关已启用，恢复状态: {saved_state}")
                else:
                    # 未授权：禁用开关，设置为未勾选，显示灰色
                    self.cb_specific.setEnabled(False)
                    self.cb_specific.setChecked(False)
                    self.cb_specific.setStyleSheet("color: #888;")
                    print(f"    [更新UI状态] @回复功能开关已禁用")
            
            # 高级回复模式
            if hasattr(self, 'cb_advanced'):
                print(f"    [更新UI状态] 高级回复模式: {'已授权' if advanced_enabled else '未授权'}")
                if advanced_enabled:
                    # 已授权：启用开关，移除灰色样式，恢复之前保存的状态
                    self.cb_advanced.setEnabled(True)
                    self.cb_advanced.setStyleSheet("")
                    saved_state = saved_states.get('advanced_reply_enabled', False)
                    self.cb_advanced.setChecked(saved_state)
                    self.cfg['advanced_reply_enabled'] = saved_state
                    print(f"    [更新UI状态] 高级回复模式开关已启用，恢复状态: {saved_state}")
                else:
                    # 未授权：禁用开关，设置为未勾选，显示灰色
                    self.cb_advanced.setEnabled(False)
                    self.cb_advanced.setChecked(False)
                    self.cb_advanced.setStyleSheet("color: #888;")
                    print(f"    [更新UI状态] 高级回复模式开关已禁用")
            
            # 暖场功能
            if hasattr(self, 'cb_warmup'):
                print(f"    [更新UI状态] 暖场功能: {'已授权' if warmup_enabled else '未授权'}")
                if warmup_enabled:
                    # 已授权：启用开关，移除灰色样式，恢复之前保存的状态
                    self.cb_warmup.setEnabled(True)
                    self.cb_warmup.setStyleSheet("")
                    saved_state = saved_states.get('warmup_enabled', False)
                    self.cb_warmup.setChecked(saved_state)
                    self.cfg['warmup_enabled'] = saved_state
                    print(f"    [更新UI状态] 暖场功能开关已启用，恢复状态: {saved_state}")
                else:
                    # 未授权：禁用开关，设置为未勾选，显示灰色
                    self.cb_warmup.setEnabled(False)
                    self.cb_warmup.setChecked(False)
                    self.cb_warmup.setStyleSheet("color: #888;")
                    print(f"    [更新UI状态] 暖场功能开关已禁用")
            
            # 指令控制功能
            if hasattr(self, 'cb_command'):
                print(f"    [更新UI状态] 指令控制功能: {'已授权' if command_enabled else '未授权'}")
                if command_enabled:
                    # 已授权：启用开关，移除灰色样式，恢复之前保存的状态
                    self.cb_command.setEnabled(True)
                    self.cb_command.setStyleSheet("")
                    saved_state = saved_states.get('command_enabled', False)
                    self.cb_command.setChecked(saved_state)
                    self.cfg['command_enabled'] = saved_state
                    print(f"    [更新UI状态] 指令控制功能开关已启用，恢复状态: {saved_state}")
                else:
                    # 未授权：禁用开关，设置为未勾选，显示灰色
                    self.cb_command.setEnabled(False)
                    self.cb_command.setChecked(False)
                    self.cb_command.setStyleSheet("color: #888;")
                    print(f"    [更新UI状态] 指令控制功能开关已禁用")
            
            # 通知所有已打开的小号窗口更新配置（授权状态已改变）
            if hasattr(self, 'config_signal'):
                self.config_signal.config_updated.emit(self.cfg.copy())
            
            print(f"    [更新UI状态] 更新完成")
            sys.stdout.flush()
                
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"    [更新UI状态] 失败: {e}")
            print(f"    [更新UI状态] 详细错误: {error_detail}")
            sys.stdout.flush()
    
    def _check_ban_status(self):
        """检查设备封禁状态（定时调用）"""
        def check():
            try:
                is_banned, message, ban_reason = check_ban_status()
                if is_banned:
                    # 在主线程中显示消息并退出
                    QTimer.singleShot(0, lambda: self._handle_ban(ban_reason))
            except Exception as e:
                # 检查失败不处理，避免误报
                pass
        
        # 在后台线程中执行检查
        thread = threading.Thread(target=check, daemon=True)
        thread.start()
    
    def _handle_ban(self, ban_reason):
        """处理封禁情况（在主线程中调用）"""
        import os
        reason_text = ban_reason if ban_reason else "未知原因"
        QMessageBox.critical(
            self,
            "设备已被封禁",
            f"您的设备已被封禁，程序将强制退出。\n\n"
            f"封禁原因：{reason_text}\n\n"
            f"如有疑问，请联系开发者：\n"
            f"邮箱：ncomscook@qq.com"
        )
        # 停止定时器
        if hasattr(self, 'ban_check_timer'):
            self.ban_check_timer.stop()
        if hasattr(self, 'feature_auth_timer'):
            self.feature_auth_timer.stop()
        # 强制退出程序（使用os._exit确保立即退出，不执行清理代码）
        try:
            QApplication.quit()
        except:
            pass
        # 使用os._exit强制退出，确保无法绕过
        os._exit(1)
        
    def _open_rule_manager_with_account(self, rule_type):
        """打开规则管理器（根据下拉框选择全局或小号配置）"""
        # 获取选中的账户（如果选择了"全局配置"则为None）
        current_data = self.account_rule_combo.currentData()
        account_name = current_data if current_data else None
        
        if account_name:
            # 为指定小号打开规则配置
            self._open_account_specific_rule_manager(account_name, rule_type)
        else:
            # 打开全局规则配置
            self._open_rule_manager(rule_type)
    
    def _open_rule_manager(self, rule_type):
        """打开全局规则管理器"""
        try:
            if rule_type == 'reply':
                win = BaseRuleManager(self.cfg, "回复规则设置（全局）", "reply_rules")
            elif rule_type == 'spec':
                win = BaseRuleManager(self.cfg, "@回复规则设置（全局）", "specific_rules")
            elif rule_type == 'warm':
                win = WarmupManager(self.cfg)
            elif rule_type == 'advanced':
                from ui_managers import AdvancedReplyManager
                win = AdvancedReplyManager(self.cfg)
            else:
                return
            
            # 存储窗口引用，防止被垃圾回收
            if not hasattr(self, '_rule_windows'):
                self._rule_windows = []
            self._rule_windows.append(win)
            
            # 当规则管理器窗口关闭时，重新加载配置并通知所有窗口更新
            def on_closed():
                # 从列表中移除
                if hasattr(self, '_rule_windows') and win in self._rule_windows:
                    self._rule_windows.remove(win)
                # 重新加载配置以确保获取最新数据
                self.cfg = load_cfg()
                # 通知所有已打开的小号窗口更新配置
                self.config_signal.config_updated.emit(self.cfg.copy())
                # global_logger.log("系统", "规则配置已更新")
                print("    [配置更新] 全局规则配置已更新")
                sys.stdout.flush()
                
                # 上报关键词到服务器（异步，不阻塞UI）
                self._submit_keywords_async()
            
            win.destroyed.connect(on_closed)
            
            win.show()
            win.raise_()  # 确保窗口置顶
            win.activateWindow()  # 激活窗口
            
        except Exception as e:
            error_msg = f"打开规则管理器失败: {type(e).__name__}: {e}"
            print(f"    [错误] {error_msg}")
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            QMessageBox.critical(self, "错误", error_msg + "\n\n请查看日志文件获取详细信息。")
    
    def _on_config_updated_from_window(self, new_cfg):
        """接收来自main_window的配置更新（用于同步开关状态）"""
        try:
            # 只更新开关相关的配置字段，并且只在值确实发生变化时才更新UI
            # 注意：这个方法只在接收到来自main_window的配置更新时调用（如弹幕指令执行后）
            # 不会在用户手动点击开关时调用（因为用户操作会触发_update_global_config，但不会触发这个方法）
            switch_fields = ['auto_reply_enabled', 'specific_reply_enabled', 'advanced_reply_enabled', 'warmup_enabled']
            need_update = False
            
            for key in switch_fields:
                if key in new_cfg:
                    old_value = self.cfg.get(key, False)
                    new_value = new_cfg[key]
                    
                    # 获取当前开关状态用于调试
                    checkbox_state = None
                    if key == 'auto_reply_enabled' and hasattr(self, 'cb_reply'):
                        checkbox_state = self.cb_reply.isChecked()
                    elif key == 'specific_reply_enabled' and hasattr(self, 'cb_specific'):
                        checkbox_state = self.cb_specific.isChecked()
                    elif key == 'advanced_reply_enabled' and hasattr(self, 'cb_advanced'):
                        checkbox_state = self.cb_advanced.isChecked()
                    elif key == 'warmup_enabled' and hasattr(self, 'cb_warmup'):
                        checkbox_state = self.cb_warmup.isChecked()
                    
                    print(f"    [配置同步] {key}: 旧值={old_value}, 新值={new_value}, 当前开关={checkbox_state}")
                    
                    # 如果新值与旧值不同，说明配置确实发生了变化（来自弹幕指令）
                    # 或者如果新值与当前开关状态不同，也需要更新（确保UI同步）
                    if old_value != new_value or (checkbox_state is not None and checkbox_state != new_value):
                        # 更新内存中的配置
                        self.cfg[key] = new_value
                        need_update = True
                        print(f"    [配置同步] ✓ {key} 已更新: {old_value} -> {new_value}")
                    else:
                        print(f"    [配置同步] - {key} 无需更新（值相同）")
                else:
                    print(f"    [配置同步] - {key} 不在new_cfg中")
            
            # 只有在配置确实发生变化时才更新开关状态
            if need_update:
                print(f"    [配置同步] 需要更新开关状态，调用 _update_switches_from_config")
                self._update_switches_from_config()
            else:
                print(f"    [配置同步] 无需更新开关状态")
        except Exception as e:
            print(f"    [配置同步] 错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _update_switches_from_config(self):
        """根据配置更新开关状态（用于同步指令执行后的状态）"""
        try:
            print(f"    [更新开关状态] 开始更新开关状态")
            # 更新自动回复开关（只在状态不一致时更新）
            if hasattr(self, 'cb_reply'):
                current_state = self.cb_reply.isChecked()
                target_state = self.cfg.get('auto_reply_enabled', False)
                print(f"    [更新开关状态] 自动回复: 当前={current_state}, 目标={target_state}")
                if current_state != target_state:
                    print(f"    [更新开关状态] ✓ 更新自动回复开关: {current_state} -> {target_state}")
                    self.cb_reply.blockSignals(True)  # 阻止信号触发，避免循环更新
                    self.cb_reply.setChecked(target_state)
                    self.cb_reply.blockSignals(False)
            
            # 更新@回复开关（只在状态不一致时更新）
            if hasattr(self, 'cb_specific'):
                current_state = self.cb_specific.isChecked()
                target_state = self.cfg.get('specific_reply_enabled', False)
                is_enabled = self.cb_specific.isEnabled()
                print(f"    [更新开关状态] @回复: 当前={current_state}, 目标={target_state}, 启用={is_enabled}")
                if current_state != target_state:
                    print(f"    [更新开关状态] ✓ 更新@回复开关: {current_state} -> {target_state}")
                    self.cb_specific.blockSignals(True)
                    self.cb_specific.setChecked(target_state)
                    self.cb_specific.blockSignals(False)
            
            # 更新高级回复模式开关（只在状态不一致时更新）
            if hasattr(self, 'cb_advanced'):
                current_state = self.cb_advanced.isChecked()
                target_state = self.cfg.get('advanced_reply_enabled', False)
                is_enabled = self.cb_advanced.isEnabled()
                print(f"    [更新开关状态] 高级回复模式: 当前={current_state}, 目标={target_state}, 启用={is_enabled}")
                if current_state != target_state:
                    print(f"    [更新开关状态] ✓ 更新高级回复模式开关: {current_state} -> {target_state}")
                    self.cb_advanced.blockSignals(True)
                    self.cb_advanced.setChecked(target_state)
                    self.cb_advanced.blockSignals(False)
            
            # 更新暖场开关（只在状态不一致时更新）
            if hasattr(self, 'cb_warmup'):
                current_state = self.cb_warmup.isChecked()
                target_state = self.cfg.get('warmup_enabled', False)
                is_enabled = self.cb_warmup.isEnabled()
                print(f"    [更新开关状态] 暖场: 当前={current_state}, 目标={target_state}, 启用={is_enabled}")
                if current_state != target_state:
                    print(f"    [更新开关状态] ✓ 更新暖场开关: {current_state} -> {target_state}")
                    self.cb_warmup.blockSignals(True)
                    self.cb_warmup.setChecked(target_state)
                    self.cb_warmup.blockSignals(False)
            
            print(f"    [更新开关状态] 更新完成")
        except Exception as e:
            print(f"    [更新开关状态] 错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _show_command_help(self):
        """显示指令说明窗口"""
        help_dialog = QDialog(self)
        help_dialog.setWindowTitle("弹幕指令说明")
        help_dialog.setMinimumSize(600, 500)
        help_dialog.resize(700, 600)
        
        # 设置窗口图标
        icon_path = get_icon_path()
        if icon_path:
            help_dialog.setWindowIcon(QIcon(icon_path))
        
        layout = QVBoxLayout(help_dialog)
        
        # 标题
        title = QLabel("📖 弹幕指令说明")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFD700; padding: 10px;")
        layout.addWidget(title)
        
        # 说明文本
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setStyleSheet("font-size: 11px; padding: 10px; background-color: #1e1e1e; color: #ffffff;")
        
        help_content = """
<h2 style='color: #FFD700;'>💡 使用说明</h2>
<p style='color: #87CEEB;'>• 指令必须<strong style='color: #FF6B6B;'>严格匹配</strong>，不支持模糊匹配</p>
<p style='color: #87CEEB;'>• 多个指令用户用 <strong>|</strong> 分隔（例如：用户A|用户B）</p>
<p style='color: #87CEEB;'>• 只有指定的指令用户发送的指令才会被执行</p>

<h2 style='color: #FFD700; margin-top: 20px;'>🛑 停止/启动功能</h2>
<p><strong style='color: #00FF00;'>停止指令（任选其一）：</strong></p>
<ul>
<li>停止弹幕机</li>
<li>停止弹幕姬</li>
<li>停止自动回复</li>
<li>关闭弹幕机</li>
<li>关闭弹幕姬</li>
<li>关闭自动回复</li>
<li>暂停弹幕机</li>
<li>暂停弹幕姬</li>
</ul>
<p style='color: #888;'>功能：停止自动回复和暖场功能</p>

<p><strong style='color: #00FF00;'>启动指令（任选其一）：</strong></p>
<ul>
<li>启动弹幕机</li>
<li>启动弹幕姬</li>
<li>启动自动回复</li>
<li>打开弹幕机</li>
<li>打开弹幕姬</li>
<li>打开自动回复</li>
<li>开启弹幕机</li>
<li>开启弹幕姬</li>
<li>开启自动回复</li>
<li>开始弹幕机</li>
<li>开始弹幕姬</li>
</ul>
<p style='color: #888;'>功能：启动自动回复和暖场功能</p>

<h2 style='color: #FFD700; margin-top: 20px;'>@回复控制</h2>
<p><strong style='color: #00FF00;'>启用@回复（任选其一）：</strong></p>
<ul>
<li>启用@回复</li>
<li>启用@回复功能</li>
<li>开启@回复</li>
<li>开启@回复功能</li>
<li>打开@回复</li>
<li>打开@回复功能</li>
</ul>

<p><strong style='color: #00FF00;'>禁用@回复（任选其一）：</strong></p>
<ul>
<li>禁用@回复</li>
<li>禁用@回复功能</li>
<li>关闭@回复</li>
<li>关闭@回复功能</li>
<li>停止@回复</li>
<li>停止@回复功能</li>
</ul>

<h2 style='color: #FFD700; margin-top: 20px;'>暖场控制</h2>
<p><strong style='color: #00FF00;'>启用暖场（任选其一）：</strong></p>
<ul>
<li>启用暖场</li>
<li>启用暖场功能</li>
<li>开启暖场</li>
<li>开启暖场功能</li>
<li>打开暖场</li>
<li>打开暖场功能</li>
</ul>

<p><strong style='color: #00FF00;'>禁用暖场（任选其一）：</strong></p>
<ul>
<li>禁用暖场</li>
<li>禁用暖场功能</li>
<li>关闭暖场</li>
<li>关闭暖场功能</li>
<li>停止暖场</li>
<li>停止暖场功能</li>
</ul>

<h2 style='color: #FFD700; margin-top: 20px;'>📊 统计与查询</h2>
<ul>
<li><strong>统计</strong> / <strong>查看统计</strong> / <strong>获取统计</strong> - 查看统计信息</li>
</ul>

<h2 style='color: #FFD700; margin-top: 20px;'>⚙️ 参数设置</h2>
<ul>
<li><strong>设置间隔:5</strong> - 设置回复间隔（1-30秒）</li>
<li>示例：设置间隔:3（设置回复间隔为3秒）</li>
</ul>

<h2 style='color: #FFD700; margin-top: 20px;'>📝 规则管理</h2>
<ul>
<li><strong>添加规则:关键词|回复</strong> - 添加回复规则</li>
<li>示例：添加规则:你好|欢迎来到直播间</li>
<li><strong>删除规则:关键词</strong> - 删除回复规则</li>
<li>示例：删除规则:你好</li>
</ul>

<h2 style='color: #FFD700; margin-top: 20px;'>🧹 清理操作</h2>
<ul>
<li><strong>清空队列</strong> / <strong>清空消息队列</strong> - 清空消息队列</li>
<li><strong>重置统计</strong> / <strong>清空统计</strong> - 重置统计数据（需确认）</li>
</ul>

<h2 style='color: #FF6B6B; margin-top: 20px;'>⚠️ 注意事项</h2>
<p style='color: #FF6B6B;'>• 所有指令必须<strong>完全匹配</strong>，不支持部分匹配或模糊匹配</p>
<p style='color: #FF6B6B;'>• 指令不区分大小写，但必须完全匹配（包括标点符号）</p>
<p style='color: #FF6B6B;'>• 重置统计等敏感操作需要二次确认</p>
        """
        
        help_text.setHtml(help_content)
        layout.addWidget(help_text)
        
        # 关闭按钮
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(help_dialog.accept)
        btn_close.setStyleSheet("padding: 8px; font-size: 12px;")
        layout.addWidget(btn_close)
        
        help_dialog.exec()
    
    def _open_danmu_test_window(self):
        """打开弹幕捕获测试窗口"""
        try:
            from danmu_test_window import DanmuTestWindow
            # 检查是否已经打开了测试窗口
            if hasattr(self, '_test_window') and self._test_window is not None:
                # 如果窗口已存在，将其置前
                self._test_window.raise_()
                self._test_window.activateWindow()
                return
            
            # 创建新的测试窗口
            self._test_window = DanmuTestWindow(self)
            self._test_window.show()
            self._test_window.raise_()
            self._test_window.activateWindow()
        except ImportError as e:
            QMessageBox.critical(
                self,
                "错误",
                f"无法导入测试窗口模块：{str(e)}\n\n请确保 danmu_test_window.py 文件存在。"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "错误",
                f"打开测试窗口失败：{str(e)}\n\n{traceback.format_exc()}"
            )


def main():
    """主函数（仅用于直接运行此模块时，打包环境不应执行）"""
    # 检查是否已有QApplication实例（防止在打包环境中重复创建）
    app = QApplication.instance()
    if app is None:
        try:
            QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
            app = QApplication(sys.argv)
            QWebEngineProfile.defaultProfile().setHttpUserAgent(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
            
            print("  → 正在创建控制面板...")
            panel = ControlPanel()
            print("  ✓ 控制面板创建成功")
            
            print("\n[3/3] 显示窗口...")
            panel.show()
            print("  ✓ 窗口已显示")
            print("\n程序运行中... (关闭窗口即可退出)")
            
            sys.exit(app.exec())
        except Exception as e:
            print(f"\n❌ 创建控制面板时出错: {e}")
            traceback.print_exc()
            raise
    else:
        # 如果已有QApplication实例，说明可能是从主程序导入的，不应该创建新窗口
        print("警告: control_panel.main() 不应在已有QApplication的情况下调用")
        return


# 仅在直接运行此文件时执行（打包环境不应触发）
# 添加额外检查，确保不是从打包的EXE中调用
if __name__ == "__main__":
    # 检查是否在打包环境中（PyInstaller会设置frozen标志）
    if not getattr(sys, 'frozen', False):
        # 只有在非打包环境中才允许执行
        main()
    else:
        print("错误: control_panel.py 不应在打包环境中作为入口点执行")
        print("请使用 main.py 作为程序入口点")

