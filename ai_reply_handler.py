"""
AI回复处理模块 - 集成DeepSeek API进行智能回复
"""
import os
import sys
import json
import requests
import re
from typing import Optional, List, Dict, Tuple
from datetime import datetime
import threading
import time


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
            import traceback
            error_msg = f"[异常] AI回复API请求失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
            print(error_msg)
            print(traceback.format_exc())
            import sys
            sys.stdout.flush()
            return None
        except Exception as e:
            import traceback
            error_msg = f"[异常] AI回复处理响应失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
            print(error_msg)
            print(traceback.format_exc())
            import sys
            sys.stdout.flush()
            return None


class AIReplyHandler:
    """AI回复处理器"""
    
    def __init__(self, api_key: str, system_prompt: str = "", max_history: int = 5, 
                 filter_config: Dict = None, cdk: str = None):
        """
        初始化AI回复处理器
        
        Args:
            api_key: DeepSeek API密钥
            system_prompt: 系统提示词（AI角色设定）
            max_history: 保留的最大对话历史轮数
            filter_config: 过滤配置字典，包含以下可选键：
                - min_length: 最小长度（默认2）
                - filter_emoji_only: 是否过滤纯表情符号（默认True）
                - filter_numbers_only: 是否过滤纯数字（默认True）
                - filter_punctuation_only: 是否过滤纯标点符号（默认True）
                - filter_repeated_chars: 是否过滤重复字符（如"哈哈哈"）（默认True）
                - filter_keywords: 关键词列表，只回复包含这些关键词的弹幕（可选，默认None表示不过滤）
                - require_keywords: 是否必须包含关键词（默认False，即关键词为白名单模式）
            cdk: CDK代码（用于token消耗上报）
        """
        self.api = DeepSeekAPI(api_key)
        self.system_prompt = system_prompt or self._get_default_system_prompt()
        self.max_history = max_history
        self.conversation_history: Dict[str, List[Dict[str, str]]] = {}  # {user: [messages]}
        self.lock = threading.Lock()
        self.cdk = cdk  # CDK代码，用于token消耗上报
        
        # 初始化过滤配置
        self.filter_config = filter_config or {}
        self.min_length = self.filter_config.get('min_length', 2)
        self.filter_emoji_only = self.filter_config.get('filter_emoji_only', True)
        self.filter_numbers_only = self.filter_config.get('filter_numbers_only', True)
        self.filter_punctuation_only = self.filter_config.get('filter_punctuation_only', True)
        self.filter_repeated_chars = self.filter_config.get('filter_repeated_chars', True)
        self.filter_keywords = self.filter_config.get('filter_keywords', [])
        self.require_keywords = self.filter_config.get('require_keywords', False)
        
    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示词"""
        return (
            "你是一个抖音直播间的智能助手，负责回复观众的弹幕。"
            "回复要简洁、友好、有趣，通常不超过20字。"
            "如果观众问问题，要给出有用的回答；如果是闲聊，要热情互动。"
            "不要重复相同的内容，要根据上下文灵活回复。"
        )
    
    def set_system_prompt(self, prompt: str):
        """设置系统提示词"""
        self.system_prompt = prompt or self._get_default_system_prompt()
    
    def set_max_history(self, max_history: int):
        """设置最大历史记录数"""
        self.max_history = max(max_history, 1)
    
    def set_filter_config(self, filter_config: Dict):
        """更新过滤配置"""
        self.filter_config = filter_config or {}
        self.min_length = self.filter_config.get('min_length', 2)
        self.filter_emoji_only = self.filter_config.get('filter_emoji_only', True)
        self.filter_numbers_only = self.filter_config.get('filter_numbers_only', True)
        self.filter_punctuation_only = self.filter_config.get('filter_punctuation_only', True)
        self.filter_repeated_chars = self.filter_config.get('filter_repeated_chars', True)
        self.filter_keywords = self.filter_config.get('filter_keywords', [])
        self.require_keywords = self.filter_config.get('require_keywords', False)
    
    def set_cdk(self, cdk: str):
        """设置CDK代码（用于token消耗上报）"""
        self.cdk = cdk
    
    def should_filter_danmu(self, content: str) -> Tuple[bool, str]:
        """
        判断弹幕是否应该被过滤（不进行AI回复）
        
        Args:
            content: 弹幕内容
        
        Returns:
            (should_filter, reason): 是否过滤，以及过滤原因
        """
        if not content or not isinstance(content, str):
            return True, "内容为空或无效"
        
        content = content.strip()
        
        # 1. 检查最小长度
        if len(content) < self.min_length:
            return True, f"长度不足（少于{self.min_length}个字符）"
        
        # 2. 过滤纯表情符号（使用正则表达式匹配常见表情符号）
        if self.filter_emoji_only:
            # 移除所有常见表情符号和emoji，检查是否还有内容
            emoji_pattern = re.compile(
                r'[\U0001F600-\U0001F64F]|'  # 表情符号
                r'[\U0001F300-\U0001F5FF]|'  # 符号和象形文字
                r'[\U0001F680-\U0001F6FF]|'  # 交通和地图符号
                r'[\U0001F1E0-\U0001F1FF]|'  # 旗帜
                r'[\U00002702-\U000027B0]|'  # 其他符号
                r'[\U000024C2-\U0001F251]|'  # 封闭字符
                r'[😀-🙏]|'  # 常见表情
                r'[👍-👎]|'  # 手势
                r'[❤️-💯]'   # 心形等
            )
            content_without_emoji = emoji_pattern.sub('', content)
            if not content_without_emoji.strip():
                return True, "纯表情符号"
        
        # 3. 过滤纯数字
        if self.filter_numbers_only:
            if content.replace(' ', '').isdigit():
                return True, "纯数字"
        
        # 4. 过滤纯标点符号
        if self.filter_punctuation_only:
            punctuation_only = re.sub(r'[\w\s]', '', content)  # 移除所有字母数字和空格
            if len(punctuation_only) == len(content.replace(' ', '')):
                return True, "纯标点符号"
        
        # 5. 过滤重复字符（如"哈哈哈"、"666666"）
        if self.filter_repeated_chars:
            # 检查是否超过60%的字符是重复的
            if len(content) >= 3:
                char_counts = {}
                for char in content:
                    if char.strip():  # 忽略空格
                        char_counts[char] = char_counts.get(char, 0) + 1
                if char_counts:
                    max_count = max(char_counts.values())
                    if max_count >= len(content.replace(' ', '')) * 0.6:
                        return True, "重复字符过多"
        
        # 6. 关键词过滤（如果配置了关键词）
        if self.filter_keywords:
            content_lower = content.lower()
            has_keyword = any(keyword.lower() in content_lower for keyword in self.filter_keywords if keyword.strip())
            if self.require_keywords:
                # 必须包含关键词模式：如果没有关键词，则过滤
                if not has_keyword:
                    return True, "不包含关键词"
            else:
                # 白名单模式：如果有关键词列表，只回复包含关键词的弹幕
                # 如果关键词列表为空，则不过滤
                if self.filter_keywords and not has_keyword:
                    return True, "不包含关键词"
        
        return False, ""
    
    def get_reply(self, user: str, content: str, context_messages: List[Dict[str, str]] = None) -> Optional[str]:
        """
        获取AI回复
        
        Args:
            user: 用户名
            content: 用户消息内容
            context_messages: 额外的上下文消息（可选）
        
        Returns:
            AI回复内容，失败返回None；如果弹幕被过滤，返回None
        """
        # 先进行过滤检查
        should_filter, reason = self.should_filter_danmu(content)
        if should_filter:
            return None  # 被过滤，不进行AI回复
        
        with self.lock:
            # 获取或创建用户对话历史
            if user not in self.conversation_history:
                self.conversation_history[user] = []
            
            user_history = self.conversation_history[user]
            
            # 构建消息列表
            messages = []
            
            # 添加系统提示词
            if self.system_prompt:
                messages.append({"role": "system", "content": self.system_prompt})
            
            # 添加上下文消息（如果有）
            if context_messages:
                messages.extend(context_messages)
            
            # 添加用户历史（限制数量）
            history_to_use = user_history[-self.max_history:] if len(user_history) > self.max_history else user_history
            messages.extend(history_to_use)
            
            # 添加当前用户消息
            messages.append({"role": "user", "content": content})
            
            # 计算请求长度（所有消息的字符数总和）
            request_length = sum(len(msg.get("content", "")) for msg in messages)
            
            # 调用API
            reply = self.api.chat(messages)
            
            if reply:
                # 计算响应长度
                response_length = len(reply)
                
                # 上报token消耗（异步，不阻塞）
                self._report_token_usage(request_length, response_length)
                
                # 更新对话历史
                user_history.append({"role": "user", "content": content})
                user_history.append({"role": "assistant", "content": reply})
                
                # 限制历史记录长度
                if len(user_history) > self.max_history * 2:  # 用户+AI算一轮
                    user_history = user_history[-self.max_history * 2:]
                    self.conversation_history[user] = user_history
                
                return reply
            else:
                return None
    
    def _report_token_usage(self, request_length: int, response_length: int):
        """上报token消耗（异步，不阻塞主流程）"""
        def report():
            try:
                from server_client import report_ai_token_usage
                success, message = report_ai_token_usage(
                    request_length=request_length,
                    response_length=response_length,
                    cdk=self.cdk
                )
                if not success:
                    print(f"[AI Token上报] 失败: {message}")
            except Exception as e:
                # 记录异常但不影响主流程
                import traceback
                error_msg = f"[异常] AI Token消耗上报失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
                print(error_msg)
                print(traceback.format_exc())
                import sys
                sys.stdout.flush()
        
        # 在后台线程中执行上报，不阻塞主流程
        thread = threading.Thread(target=report, daemon=True)
        thread.start()
    
    def clear_user_history(self, user: str = None):
        """
        清空对话历史
        
        Args:
            user: 用户名，如果为None则清空所有用户的历史
        """
        with self.lock:
            if user:
                if user in self.conversation_history:
                    del self.conversation_history[user]
            else:
                self.conversation_history.clear()
    
    def get_user_history_count(self, user: str) -> int:
        """获取用户的对话历史数量"""
        with self.lock:
            if user in self.conversation_history:
                return len(self.conversation_history[user])
            return 0
