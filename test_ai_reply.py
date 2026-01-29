"""
AI回复功能测试窗口
测试DeepSeek API集成和过滤功能
"""
import os
import sys
import json
import requests
import re
from typing import Optional, List, Dict, Tuple
from datetime import datetime

# 环境优化
os.environ["QT_GL_DEFAULT_BACKEND"] = "software"

from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QTextEdit, QCheckBox,
                             QGroupBox, QSpinBox, QComboBox, QMessageBox, QScrollArea, QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QTextCursor, QIcon


class DeepSeekAPI:
    """DeepSeek API客户端"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com"
        self.model = "deepseek-chat"
        self.timeout = 30
        
    def chat(self, messages: List[Dict[str, str]], stream: bool = False) -> Optional[str]:
        """
        调用DeepSeek API进行对话
        
        Args:
            messages: 消息列表，格式：[{"role": "user", "content": "..."}]
            stream: 是否使用流式输出
        
        Returns:
            AI回复内容，失败返回None
        """
        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            data = {
                "model": self.model,
                "messages": messages,
                "stream": stream
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=self.timeout)
            response.raise_for_status()
            
            result = response.json()
            
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            else:
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"API请求失败: {e}")
            return None
        except Exception as e:
            print(f"处理响应失败: {e}")
            return None


class AIReplyWorker(QThread):
    """AI回复工作线程（避免阻塞UI）"""
    
    finished = pyqtSignal(str, bool)  # 回复内容, 是否成功
    
    def __init__(self, api: DeepSeekAPI, messages: List[Dict[str, str]]):
        super().__init__()
        self.api = api
        self.messages = messages
        
    def run(self):
        """执行AI回复请求"""
        reply = self.api.chat(self.messages)
        if reply:
            self.finished.emit(reply, True)
        else:
            self.finished.emit("AI回复失败，请检查API配置", False)


class AIReplyTestWindow(QWidget):
    """AI回复测试窗口"""
    
    def __init__(self):
        super().__init__()
        self.api_key = "sk-486ca90f1a274a8f88b3490d6fab6762"
        self.api = DeepSeekAPI(self.api_key)
        self.conversation_history: List[Dict[str, str]] = []
        self.worker: Optional[AIReplyWorker] = None
        
        # 过滤配置
        self.filter_config = {
            'min_length': 2,
            'filter_emoji_only': True,
            'filter_numbers_only': True,
            'filter_punctuation_only': True,
            'filter_repeated_chars': True,
            'filter_keywords': [],
            'require_keywords': False,
        }
        
        # AI角色配置
        self.ai_role = 'custom'  # 'custom' or 'clothing'
        self.clothing_category = ''
        self.clothing_height = 165
        self.clothing_weight = 55
        
        self.init_ui()
        
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("AI回复功能测试 - DeepSeek（含过滤测试）")
        self.setMinimumSize(900, 700)
        self.resize(1000, 800)
        
        # 设置窗口图标
        try:
            icon_path = "favicon.ico"
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except:
            pass
        
        # 使用滚动区域包装内容
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # API配置组
        api_group = QGroupBox("API配置")
        api_layout = QVBoxLayout()
        
        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setText(self.api_key)
        self.api_key_input.setPlaceholderText("输入DeepSeek API Key")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_key_layout.addWidget(self.api_key_input)
        
        btn_toggle_api = QPushButton("👁️")
        btn_toggle_api.setMaximumWidth(40)
        btn_toggle_api.clicked.connect(lambda: self.api_key_input.setEchoMode(
            QLineEdit.EchoMode.Normal if self.api_key_input.echoMode() == QLineEdit.EchoMode.Password 
            else QLineEdit.EchoMode.Password
        ))
        api_key_layout.addWidget(btn_toggle_api)
        
        btn_save_api = QPushButton("保存")
        btn_save_api.clicked.connect(self.save_api_key)
        api_key_layout.addWidget(btn_save_api)
        api_layout.addLayout(api_key_layout)
        
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("模型:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["deepseek-chat", "deepseek-reasoner"])
        self.model_combo.setCurrentText("deepseek-chat")
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        model_layout.addWidget(self.model_combo)
        model_layout.addStretch()
        api_layout.addLayout(model_layout)
        
        api_group.setLayout(api_layout)
        layout.addWidget(api_group)
        
        # AI角色配置组
        role_group = QGroupBox("AI角色设置")
        role_layout = QVBoxLayout()
        role_layout.setSpacing(8)
        
        role_row = QHBoxLayout()
        role_row.addWidget(QLabel("预设角色:"))
        self.role_combo = QComboBox()
        self.role_combo.addItem("自定义提示词", "custom")
        self.role_combo.addItem("服装类直播AI", "clothing")
        self.role_combo.currentTextChanged.connect(self.on_role_changed)
        role_row.addWidget(self.role_combo)
        role_row.addStretch()
        role_layout.addLayout(role_row)
        
        # 服装类AI详细信息
        self.clothing_info_group = QGroupBox("服装类AI详细信息")
        clothing_layout = QVBoxLayout()
        clothing_layout.setSpacing(8)
        
        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("品类:"))
        self.clothing_category_input = QLineEdit()
        self.clothing_category_input.setPlaceholderText("例如：女装、男装、童装、运动装等")
        self.clothing_category_input.textChanged.connect(self.on_clothing_info_changed)
        category_layout.addWidget(self.clothing_category_input)
        clothing_layout.addLayout(category_layout)
        
        host_info_layout = QHBoxLayout()
        host_info_layout.addWidget(QLabel("主播身高(cm):"))
        self.clothing_height_spin = QSpinBox()
        self.clothing_height_spin.setRange(100, 250)
        self.clothing_height_spin.setValue(165)
        self.clothing_height_spin.valueChanged.connect(self.on_clothing_info_changed)
        host_info_layout.addWidget(self.clothing_height_spin)
        
        host_info_layout.addWidget(QLabel("主播体重(kg):"))
        self.clothing_weight_spin = QSpinBox()
        self.clothing_weight_spin.setRange(30, 200)
        self.clothing_weight_spin.setValue(55)
        self.clothing_weight_spin.valueChanged.connect(self.on_clothing_info_changed)
        host_info_layout.addWidget(self.clothing_weight_spin)
        clothing_layout.addLayout(host_info_layout)
        
        self.clothing_info_group.setLayout(clothing_layout)
        self.clothing_info_group.setVisible(False)
        role_layout.addWidget(self.clothing_info_group)
        
        # 自定义提示词
        self.custom_prompt_group = QGroupBox("自定义提示词")
        custom_prompt_layout = QVBoxLayout()
        self.system_prompt_input = QTextEdit()
        self.system_prompt_input.setPlaceholderText(
            "例如：你是一个抖音直播间的智能助手，负责回复观众的弹幕。"
            "回复要简洁、友好、有趣，不超过20字。"
        )
        self.system_prompt_input.setMaximumHeight(100)
        custom_prompt_layout.addWidget(self.system_prompt_input)
        self.custom_prompt_group.setLayout(custom_prompt_layout)
        role_layout.addWidget(self.custom_prompt_group)
        
        role_group.setLayout(role_layout)
        layout.addWidget(role_group)
        
        # 弹幕过滤设置组
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
        self.filter_min_length_spin = QSpinBox()
        self.filter_min_length_spin.setRange(1, 20)
        self.filter_min_length_spin.setValue(2)
        self.filter_min_length_spin.setSuffix(" 字符")
        min_length_layout.addWidget(self.filter_min_length_spin)
        min_length_layout.addStretch()
        filter_layout.addLayout(min_length_layout)
        
        filter_options_layout = QHBoxLayout()
        filter_left_layout = QVBoxLayout()
        filter_right_layout = QVBoxLayout()
        
        self.cb_filter_emoji = QCheckBox("过滤纯表情符号")
        self.cb_filter_emoji.setChecked(True)
        filter_left_layout.addWidget(self.cb_filter_emoji)
        
        self.cb_filter_numbers = QCheckBox("过滤纯数字")
        self.cb_filter_numbers.setChecked(True)
        filter_left_layout.addWidget(self.cb_filter_numbers)
        
        self.cb_filter_punctuation = QCheckBox("过滤纯标点符号")
        self.cb_filter_punctuation.setChecked(True)
        filter_right_layout.addWidget(self.cb_filter_punctuation)
        
        self.cb_filter_repeated = QCheckBox("过滤重复字符")
        self.cb_filter_repeated.setChecked(True)
        filter_right_layout.addWidget(self.cb_filter_repeated)
        
        filter_options_layout.addLayout(filter_left_layout)
        filter_options_layout.addLayout(filter_right_layout)
        filter_layout.addLayout(filter_options_layout)
        
        keyword_layout = QVBoxLayout()
        keyword_header_layout = QHBoxLayout()
        self.cb_require_keywords = QCheckBox("仅回复包含关键词的弹幕")
        keyword_header_layout.addWidget(self.cb_require_keywords)
        keyword_header_layout.addStretch()
        keyword_layout.addLayout(keyword_header_layout)
        
        keyword_input_layout = QHBoxLayout()
        keyword_input_layout.addWidget(QLabel("关键词:"))
        self.filter_keywords_input = QLineEdit()
        self.filter_keywords_input.setPlaceholderText("多个关键词用 | 分隔，例如：尺码|颜色|材质")
        keyword_input_layout.addWidget(self.filter_keywords_input)
        keyword_layout.addLayout(keyword_input_layout)
        filter_layout.addLayout(keyword_layout)
        
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)
        
        # 对话历史组
        history_group = QGroupBox("对话历史")
        history_layout = QVBoxLayout()
        
        toolbar = QHBoxLayout()
        btn_clear_history = QPushButton("清空历史")
        btn_clear_history.clicked.connect(self.clear_history)
        toolbar.addWidget(btn_clear_history)
        toolbar.addStretch()
        self.max_history_spin = QSpinBox()
        self.max_history_spin.setRange(5, 50)
        self.max_history_spin.setValue(10)
        self.max_history_spin.setPrefix("保留最近 ")
        self.max_history_spin.setSuffix(" 轮对话")
        toolbar.addWidget(QLabel("历史记录限制:"))
        toolbar.addWidget(self.max_history_spin)
        history_layout.addLayout(toolbar)
        
        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        self.history_text.setPlaceholderText("对话历史将显示在这里...")
        history_layout.addWidget(self.history_text)
        
        history_group.setLayout(history_layout)
        layout.addWidget(history_group)
        
        # 输入组
        input_group = QGroupBox("输入消息")
        input_layout = QVBoxLayout()
        
        self.user_input = QTextEdit()
        self.user_input.setPlaceholderText("输入要发送给AI的消息...")
        self.user_input.setMaximumHeight(100)
        self.user_input.setAcceptRichText(False)
        input_layout.addWidget(self.user_input)
        
        btn_layout = QHBoxLayout()
        btn_send = QPushButton("发送消息")
        btn_send.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        btn_send.clicked.connect(self.send_message)
        btn_layout.addWidget(btn_send)
        
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #666; padding: 5px;")
        btn_layout.addWidget(self.status_label)
        btn_layout.addStretch()
        
        input_layout.addLayout(btn_layout)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        # 测试场景组
        test_group = QGroupBox("快速测试")
        test_layout = QVBoxLayout()
        
        test_btn_layout = QHBoxLayout()
        
        btn_test1 = QPushButton("测试1: 简单问候")
        btn_test1.clicked.connect(lambda: self.test_message("你好"))
        test_btn_layout.addWidget(btn_test1)
        
        btn_test2 = QPushButton("测试2: 弹幕回复")
        btn_test2.clicked.connect(lambda: self.test_message("主播今天播什么？"))
        test_btn_layout.addWidget(btn_test2)
        
        btn_test3 = QPushButton("测试3: 感谢礼物")
        btn_test3.clicked.connect(lambda: self.test_message("谢谢你的礼物！"))
        test_btn_layout.addWidget(btn_test3)
        
        test_btn_layout.addStretch()
        test_layout.addLayout(test_btn_layout)
        
        # 过滤测试组
        filter_test_layout = QVBoxLayout()
        filter_test_layout.addWidget(QLabel("过滤测试（测试弹幕是否会被过滤）:"))
        filter_test_btn_layout = QHBoxLayout()
        
        btn_test_filter1 = QPushButton("测试: 纯表情 😀😀😀")
        btn_test_filter1.clicked.connect(lambda: self.test_filter("😀😀😀"))
        filter_test_btn_layout.addWidget(btn_test_filter1)
        
        btn_test_filter2 = QPushButton("测试: 纯数字 666")
        btn_test_filter2.clicked.connect(lambda: self.test_filter("666"))
        filter_test_btn_layout.addWidget(btn_test_filter2)
        
        btn_test_filter3 = QPushButton("测试: 重复字符 哈哈哈")
        btn_test_filter3.clicked.connect(lambda: self.test_filter("哈哈哈"))
        filter_test_btn_layout.addWidget(btn_test_filter3)
        
        btn_test_filter4 = QPushButton("测试: 过短 a")
        btn_test_filter4.clicked.connect(lambda: self.test_filter("a"))
        filter_test_btn_layout.addWidget(btn_test_filter4)
        
        filter_test_btn_layout.addStretch()
        filter_test_layout.addLayout(filter_test_btn_layout)
        test_layout.addLayout(filter_test_layout)
        
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)
        
        scroll_area.setWidget(content_widget)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area)
        
    def save_api_key(self):
        """保存API Key"""
        new_key = self.api_key_input.text().strip()
        if new_key:
            self.api_key = new_key
            self.api = DeepSeekAPI(new_key)
            QMessageBox.information(self, "提示", "API Key已保存")
        else:
            QMessageBox.warning(self, "警告", "API Key不能为空")
            
    def on_model_changed(self, model: str):
        """模型切换"""
        self.api.model = model
    
    def on_role_changed(self, text):
        """角色切换"""
        self.ai_role = self.role_combo.currentData()
        if self.ai_role == "clothing":
            self.clothing_info_group.setVisible(True)
            self.custom_prompt_group.setVisible(False)
            self._update_clothing_prompt()
        else:
            self.clothing_info_group.setVisible(False)
            self.custom_prompt_group.setVisible(True)
    
    def on_clothing_info_changed(self):
        """服装类信息变化"""
        if self.ai_role == "clothing":
            self.clothing_category = self.clothing_category_input.text().strip()
            self.clothing_height = self.clothing_height_spin.value()
            self.clothing_weight = self.clothing_weight_spin.value()
            self._update_clothing_prompt()
    
    def _update_clothing_prompt(self):
        """更新服装类AI的系统提示词"""
        category = self.clothing_category or "服装"
        system_prompt = (
            f"你是一个{category}直播间的专业导购助手，负责回复观众的弹幕。\n"
            f"重要信息：主播身高{self.clothing_height}cm，体重{self.clothing_weight}kg。\n"
            f"回复要求：\n"
            f"1. 简洁、专业、友好，通常不超过20字\n"
            f"2. 根据主播的身高体重推荐合适的尺码和款式\n"
            f"3. 回答关于{category}的问题，如材质、搭配、尺码等\n"
            f"4. 如果观众询问尺码，要结合主播的身高体重给出建议\n"
            f"5. 不要重复相同的内容，要根据上下文灵活回复\n"
            f"6. 保持热情，鼓励观众下单"
        )
        # 更新到自定义提示词框（但不显示）
        if self.ai_role == "clothing":
            self.system_prompt_input.setPlainText(system_prompt)
    
    def should_filter_danmu(self, content: str) -> Tuple[bool, str]:
        """判断弹幕是否应该被过滤"""
        if not content or not isinstance(content, str):
            return True, "内容为空或无效"
        
        content = content.strip()
        
        # 检查最小长度
        min_length = self.filter_min_length_spin.value()
        if len(content) < min_length:
            return True, f"长度不足（少于{min_length}个字符）"
        
        # 过滤纯表情符号
        if self.cb_filter_emoji.isChecked():
            emoji_pattern = re.compile(
                r'[\U0001F600-\U0001F64F]|'
                r'[\U0001F300-\U0001F5FF]|'
                r'[\U0001F680-\U0001F6FF]|'
                r'[\U0001F1E0-\U0001F1FF]|'
                r'[\U00002702-\U000027B0]|'
                r'[\U000024C2-\U0001F251]|'
                r'[😀-🙏]|'
                r'[👍-👎]|'
                r'[❤️-💯]'
            )
            content_without_emoji = emoji_pattern.sub('', content)
            if not content_without_emoji.strip():
                return True, "纯表情符号"
        
        # 过滤纯数字
        if self.cb_filter_numbers.isChecked():
            if content.replace(' ', '').isdigit():
                return True, "纯数字"
        
        # 过滤纯标点符号
        if self.cb_filter_punctuation.isChecked():
            punctuation_only = re.sub(r'[\w\s]', '', content)
            if len(punctuation_only) == len(content.replace(' ', '')):
                return True, "纯标点符号"
        
        # 过滤重复字符
        if self.cb_filter_repeated.isChecked():
            if len(content) >= 3:
                char_counts = {}
                for char in content:
                    if char.strip():
                        char_counts[char] = char_counts.get(char, 0) + 1
                if char_counts:
                    max_count = max(char_counts.values())
                    if max_count >= len(content.replace(' ', '')) * 0.6:
                        return True, "重复字符过多"
        
        # 关键词过滤
        keywords_text = self.filter_keywords_input.text().strip()
        if keywords_text:
            keywords_list = [k.strip() for k in keywords_text.split('|') if k.strip()]
            if keywords_list:
                content_lower = content.lower()
                has_keyword = any(keyword.lower() in content_lower for keyword in keywords_list)
                if self.cb_require_keywords.isChecked():
                    if not has_keyword:
                        return True, "不包含关键词"
                else:
                    if not has_keyword:
                        return True, "不包含关键词"
        
        return False, ""
    
    def test_filter(self, message: str):
        """测试过滤功能"""
        should_filter, reason = self.should_filter_danmu(message)
        if should_filter:
            QMessageBox.information(
                self, 
                "过滤测试结果", 
                f"弹幕: {message}\n\n会被过滤\n原因: {reason}"
            )
        else:
            QMessageBox.information(
                self, 
                "过滤测试结果", 
                f"弹幕: {message}\n\n不会被过滤\n可以发送给AI"
            )
        
    def clear_history(self):
        """清空对话历史"""
        self.conversation_history.clear()
        self.history_text.clear()
        self.status_label.setText("历史已清空")
        
    def test_message(self, message: str):
        """快速测试消息"""
        self.user_input.setPlainText(message)
        self.send_message()
        
    def send_message(self):
        """发送消息给AI"""
        user_message = self.user_input.toPlainText().strip()
        if not user_message:
            QMessageBox.warning(self, "警告", "请输入消息内容")
            return
        
        # 先进行过滤检查
        should_filter, reason = self.should_filter_danmu(user_message)
        if should_filter:
            QMessageBox.warning(
                self, 
                "弹幕被过滤", 
                f"弹幕: {user_message}\n\n被过滤，不会发送给AI\n原因: {reason}"
            )
            return
            
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "警告", "AI正在处理中，请稍候...")
            return
        
        # 更新服装类提示词（如果使用服装类角色）
        if self.ai_role == "clothing":
            self._update_clothing_prompt()
            
        # 更新状态
        self.status_label.setText("正在发送...")
        self.status_label.setStyleSheet("color: #FF9800; padding: 5px;")
        
        # 添加用户消息到历史
        self.add_to_history("用户", user_message)
        
        # 构建消息列表
        messages = []
        
        # 添加系统提示词（如果有）
        system_prompt = self.system_prompt_input.toPlainText().strip()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        # 添加对话历史（限制数量）
        max_history = self.max_history_spin.value()
        history_to_use = self.conversation_history[-max_history:] if len(self.conversation_history) > max_history else self.conversation_history
        
        for msg in history_to_use:
            messages.append(msg)
            
        # 添加当前用户消息
        messages.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "user", "content": user_message})
        
        # 启动工作线程
        self.worker = AIReplyWorker(self.api, messages)
        self.worker.finished.connect(self.on_ai_reply)
        self.worker.start()
        
        # 清空输入框
        self.user_input.clear()
        
    def on_ai_reply(self, reply: str, success: bool):
        """AI回复完成回调"""
        if success:
            self.status_label.setText("回复成功")
            self.status_label.setStyleSheet("color: #4CAF50; padding: 5px;")
            
            # 添加AI回复到历史
            self.add_to_history("AI", reply)
            self.conversation_history.append({"role": "assistant", "content": reply})
            
            # 限制历史记录长度
            max_history = self.max_history_spin.value() * 2  # 用户+AI算一轮
            if len(self.conversation_history) > max_history:
                self.conversation_history = self.conversation_history[-max_history:]
        else:
            self.status_label.setText("回复失败")
            self.status_label.setStyleSheet("color: #F44336; padding: 5px;")
            QMessageBox.warning(self, "错误", reply)
            
    def add_to_history(self, role: str, content: str):
        """添加消息到历史显示"""
        self.history_text.moveCursor(QTextCursor.MoveOperation.End)
        
        role_color = "#2196F3" if role == "用户" else "#4CAF50"
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        html = f'<div style="margin: 5px 0;"><span style="color: {role_color}; font-weight: bold;">[{role}]</span> <span style="color: #999; font-size: 10px;">({timestamp})</span>: {self.escape_html(content)}</div>'
        self.history_text.insertHtml(html)
        self.history_text.moveCursor(QTextCursor.MoveOperation.End)
        
    def escape_html(self, text: str) -> str:
        """转义HTML特殊字符"""
        return (text.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
                   .replace("\n", "<br>"))


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle("Fusion")
    
    window = AIReplyTestWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
