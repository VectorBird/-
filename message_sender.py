"""
消息发送模块 - 统一处理消息发送和队列管理
"""
import time
import random
import json
import re
from collections import deque
from statistics_manager import statistics_manager

class MessageSender:
    """消息发送器 - 负责消息队列管理和发送控制"""
    
    def __init__(self, web_page, log_callback=None, account_name=None):
        """
        初始化消息发送器
        
        Args:
            web_page: QWebEnginePage对象，用于执行JavaScript
            log_callback: 日志回调函数
            account_name: 账户名称（用于统计）
        """
        self.web_page = web_page
        self.log_callback = log_callback
        self.account_name = account_name or "default"
        self.task_queue = deque()
        self.last_send_action_t = 0
        self.next_action_wait = 0
        self.reply_interval = 4
        self.random_jitter = 2.0
        self.random_space_insert_enabled = False  # 随机空格插入功能开关
        
    def set_intervals(self, interval, jitter):
        """
        设置发送间隔参数
        
        Args:
            interval: 基础间隔（秒）
            jitter: 随机抖动范围（秒）
        """
        self.reply_interval = interval
        self.random_jitter = jitter
    
    def set_random_space_insert(self, enabled):
        """
        设置随机空格插入功能开关
        
        Args:
            enabled: 是否启用随机空格插入
        """
        self.random_space_insert_enabled = enabled
        
    def _insert_random_spaces(self, text):
        """
        在文本中随机插入空格（防风控）
        避免在抖音官方表情符号（如[庆祝]）的中括号内插入空格
        
        Args:
            text: 原始文本
            
        Returns:
            str: 插入空格后的文本
        """
        if not text or not self.random_space_insert_enabled:
            return text
        
        # 使用正则表达式找到所有抖音表情符号（格式：[文字]）
        # 例如：[庆祝]、[礼物]、[玫瑰] 等
        emoji_pattern = r'\[[^\]]+\]'
        emoji_matches = list(re.finditer(emoji_pattern, text))
        
        # 记录表情符号的位置范围（起始位置到结束位置，包括中括号）
        protected_ranges = []
        for match in emoji_matches:
            protected_ranges.append((match.start(), match.end()))
        
        # 将文本转换为字符列表，便于插入
        chars = list(text)
        if len(chars) <= 1:
            return text  # 太短的文本不处理
        
        # 检查位置是否在受保护范围内（表情符号内部）
        def is_protected(pos):
            """检查位置是否在表情符号内部"""
            for start, end in protected_ranges:
                # 如果位置在表情符号内部（包括中括号），返回True
                if start <= pos < end:
                    return True
            return False
        
        # 随机决定插入空格的数量（1-3个位置）
        # 根据文本长度决定插入位置数量
        max_insertions = min(3, max(1, len(chars) // 5))  # 每5个字符最多插入1个空格位置
        num_insertions = random.randint(1, max_insertions)
        
        # 随机选择插入位置（不能是第一个和最后一个字符，也不能在表情符号内部）
        # 使用set确保位置不重复
        insert_positions = set()
        max_attempts = 200  # 最大尝试次数，避免死循环（增加尝试次数，因为有保护区域）
        attempts = 0
        
        while len(insert_positions) < num_insertions and attempts < max_attempts:
            attempts += 1
            # 随机选择位置（跳过第一个和最后一个字符）
            pos = random.randint(1, len(chars) - 1)
            
            # 检查是否在受保护范围内（表情符号内部）
            if is_protected(pos):
                continue  # 跳过受保护的位置
            
            # 确保不选择已选位置的相邻位置（避免空格太密集）
            can_insert = True
            for existing_pos in insert_positions:
                if abs(pos - existing_pos) <= 1:
                    can_insert = False
                    break
            if can_insert:
                insert_positions.add(pos)
        
        # 如果尝试了max_attempts次还没有找到足够的位置，使用已找到的位置
        if not insert_positions and len(chars) > 1:
            # 如果完全没有找到位置，尝试找到一个不在受保护范围内的位置
            for pos in range(1, len(chars) - 1):
                if not is_protected(pos):
                    insert_positions.add(pos)
                    break
        
        # 按位置从后往前插入，避免索引偏移问题
        sorted_positions = sorted(insert_positions, reverse=True)
        
        for pos in sorted_positions:
            # 随机插入1-3个空格
            num_spaces = random.randint(1, 3)
            chars.insert(pos, ' ' * num_spaces)
        
        return ''.join(chars)
        
    def add_message(self, message):
        """添加消息到队列"""
        if isinstance(message, str):
            self.task_queue.append(message)
        elif isinstance(message, list):
            self.task_queue.extend(message)
        
        # 记录队列大小
        statistics_manager.record_queue_size(self.account_name, len(self.task_queue))
            
    def has_pending(self):
        """检查是否有待发送消息"""
        return len(self.task_queue) > 0
        
    def process_queue(self):
        """
        处理消息队列，发送下一条消息
        
        Returns:
            str or None: 如果发送了消息，返回消息内容；否则返回None
        """
        if not self.task_queue:
            return None
            
        now = time.time()
        
        # 检查是否到达发送时间
        if now - self.last_send_action_t < self.next_action_wait:
            return None
            
        # 取出消息（原始消息）
        original_msg = self.task_queue.popleft()
        self.last_send_action_t = now
        
        # 判断是否是特定回复（以@用户名 开头，例如：@张三 消息内容）
        # 特定回复不需要插入空格，因为@用户名本身就是随机的
        is_specific_reply = original_msg.strip().startswith('@')
        
        # 应用随机空格插入（如果启用且不是特定回复）
        msg_to_send = original_msg
        if self.random_space_insert_enabled and not is_specific_reply:
            msg_to_send = self._insert_random_spaces(original_msg)
        
        # 计算下次发送等待时间
        base_interval = self.reply_interval
        jitter = random.uniform(0, self.random_jitter)
        self.next_action_wait = base_interval + jitter
        
        # 发送消息（发送插入空格后的消息）
        self._send_message(msg_to_send)
        
        # 记录日志（显示插入空格后的消息，用户看到的）
        if self.log_callback:
            self.log_callback(
                f"<span style='color:#00BFFF;'>【执行发送】</span> {msg_to_send} "
                f"<span style='color:#FF69B4;'>(间隔: {base_interval}s + 抖动: {jitter:.2f}s = 下次发送需等 {self.next_action_wait:.2f}s | 队列余量: {len(self.task_queue)})</span>"
            )
            
        # 返回原始消息（用于循环检测，因为弹幕捕获时是原始内容）
        return original_msg
        
    def _send_message(self, msg):
        """执行消息发送的JavaScript代码"""
        # 使用json.dumps确保字符串正确转义
        msg_json = json.dumps(msg, ensure_ascii=False)
        js_code = f"""
        (function() {{
            const ed = document.querySelector('[data-slate-editor="true"]') || document.querySelector('.ace-line')?.parentElement;
            if(!ed) return;
            ed.focus();
            window.getSelection().selectAllChildren(ed);
            document.execCommand('delete');
            ed.innerHTML = ''; 
            const msgText = {msg_json};
            document.execCommand('insertText', false, msgText);
            ed.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: msgText }}));
            setTimeout(() => {{
                let btn = document.querySelector('.webcast-chatroom___send-btn');
                if(btn) {{ ['mousedown','mouseup','click'].forEach(t => btn.dispatchEvent(new MouseEvent(t, {{ bubbles: true }}))); }}
                ed.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
            }}, 400);
        }})();
        """
        self.web_page.runJavaScript(js_code)
        
    def clear_queue(self):
        """清空消息队列"""
        self.task_queue.clear()

