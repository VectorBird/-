"""
全局消息队列管理器 - 防止多小号重复回复同一弹幕
"""
import time
import hashlib
import threading
from typing import Optional, Dict, Tuple
from statistics_manager import statistics_manager


class GlobalMessageQueue:
    """全局消息队列管理器 - 单例模式"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(GlobalMessageQueue, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._message_locks: Dict[str, Tuple[float, str]] = {}  # {fingerprint: (lock_time, account_name)}
        self._queue_mode = "轮询"  # 轮询、优先级、随机、第一个可用
        self._time_window = 5.0  # 消息指纹时间窗口（秒）
        self._lock_timeout = 30.0  # 锁超时时间（秒）
        self._account_priority: Dict[str, int] = {}  # 账户优先级
        self._last_account_index = 0  # 轮询索引
        self._active_accounts = set()  # 活跃账户集合
        self._internal_lock = threading.Lock()  # 内部锁
        self._strict_single_reply = True  # 严格单回复模式
        self._auto_cleanup = True  # 自动清理过期锁
        self._max_lock_history = 1000  # 最大锁历史记录数
        self._lock_count = 0  # 锁计数器（用于统计）
        self._allow_multiple_reply = False  # 允许多小号同时回复
        
        # 全局消息记录（用于防止循环回复）
        # 格式：[(message_content, timestamp), ...]
        self._global_sent_messages = []  # 全局最近发送的消息列表
        self._global_message_ttl = 30.0  # 消息记录保留时间（秒）
        self._max_global_messages = 100  # 最多记录的消息数量
        
    def set_queue_mode(self, mode: str):
        """设置队列模式"""
        with self._internal_lock:
            self._queue_mode = mode
            
    def set_time_window(self, window: float):
        """设置消息指纹时间窗口（秒）"""
        with self._internal_lock:
            self._time_window = window
            
    def set_lock_timeout(self, timeout: float):
        """设置锁超时时间（秒）"""
        with self._internal_lock:
            self._lock_timeout = timeout
            
    def set_strict_single_reply(self, enabled: bool):
        """设置严格单回复模式"""
        with self._internal_lock:
            self._strict_single_reply = enabled
            
    def set_auto_cleanup(self, enabled: bool):
        """设置自动清理过期锁"""
        with self._internal_lock:
            self._auto_cleanup = enabled
            
    def set_max_lock_history(self, max_count: int):
        """设置最大锁历史记录数"""
        with self._internal_lock:
            self._max_lock_history = max_count
    
    def set_allow_multiple_reply(self, enabled: bool):
        """设置允许多小号同时回复"""
        with self._internal_lock:
            self._allow_multiple_reply = enabled
            
    def set_account_priority(self, account_name: str, priority: int):
        """设置账户优先级（数字越大优先级越高）"""
        with self._internal_lock:
            self._account_priority[account_name] = priority
            
    def register_account(self, account_name: str):
        """注册账户（账户窗口启动时调用）"""
        with self._internal_lock:
            self._active_accounts.add(account_name)
            
    def unregister_account(self, account_name: str):
        """注销账户（账户窗口关闭时调用）"""
        with self._internal_lock:
            self._active_accounts.discard(account_name)
            # 释放该账户持有的所有锁
            to_remove = []
            for fingerprint, (lock_time, locked_account) in list(self._message_locks.items()):
                if locked_account == account_name:
                    to_remove.append(fingerprint)
            for fp in to_remove:
                del self._message_locks[fp]
                
    def _generate_fingerprint(self, user: str, content: str, timestamp: float) -> str:
        """生成消息指纹"""
        # 使用用户+内容+时间窗口生成指纹
        time_bucket = int(timestamp / self._time_window)
        raw = f"{user}|{content}|{time_bucket}"
        return hashlib.md5(raw.encode('utf-8')).hexdigest()
        
    def _cleanup_expired_locks(self):
        """清理过期的锁"""
        if not self._auto_cleanup:
            return
            
        now = time.time()
        to_remove = []
        for fingerprint, (lock_time, account_name) in self._message_locks.items():
            if now - lock_time > self._lock_timeout:
                to_remove.append(fingerprint)
        for fp in to_remove:
            del self._message_locks[fp]
            
    def _enforce_max_history(self):
        """强制执行最大历史记录数限制（防止内存泄漏）"""
        if len(self._message_locks) > self._max_lock_history:
            # 如果超过最大记录数，清理最旧的锁
            now = time.time()
            locks_with_time = [(fp, lock_time) for fp, (lock_time, _) in self._message_locks.items()]
            locks_with_time.sort(key=lambda x: x[1])  # 按时间排序
            
            # 删除最旧的一半锁
            remove_count = len(locks_with_time) - self._max_lock_history // 2
            for fp, _ in locks_with_time[:remove_count]:
                if fp in self._message_locks:
                    del self._message_locks[fp]
            
    def try_lock_message(self, user: str, content: str, account_name: str, timestamp: float = None) -> bool:
        """
        尝试锁定消息（原子操作）
        
        Args:
            user: 用户名
            content: 弹幕内容
            account_name: 账户名称
            timestamp: 时间戳（如果为None则使用当前时间）
            
        Returns:
            bool: 如果成功锁定返回True，否则返回False（已被其他账户锁定）
        """
        # 如果允许多小号同时回复，直接返回True（不进行锁定）
        if self._allow_multiple_reply:
            return True
        
        if timestamp is None:
            timestamp = time.time()
            
        fingerprint = self._generate_fingerprint(user, content, timestamp)
        
        with self._internal_lock:
            # 清理过期锁
            self._cleanup_expired_locks()
            
            # 强制执行最大历史记录数限制
            self._enforce_max_history()
            
            # 再次检查锁是否存在（在清理过期锁之后，避免竞态条件）
            # 严格单回复模式：如果锁存在且未过期，直接拒绝
            if fingerprint in self._message_locks:
                lock_time, locked_account = self._message_locks[fingerprint]
                # 检查锁是否过期
                if time.time() - lock_time < self._lock_timeout:
                    # 记录锁竞争
                    statistics_manager.record_lock_contention(1)
                    return False  # 已被其他账户锁定
                else:
                    # 锁已过期，移除它
                    del self._message_locks[fingerprint]
            
            # 根据队列模式决定是否锁定
            if self._queue_mode == "第一个可用":
                # 第一个尝试锁定的账户获得锁（此时锁肯定不存在）
                self._message_locks[fingerprint] = (time.time(), account_name)
                self._lock_count += 1
                return True
            elif self._queue_mode == "轮询":
                # 轮询模式：按账户列表顺序分配
                if not self._active_accounts:
                    self._message_locks[fingerprint] = (time.time(), account_name)
                    self._lock_count += 1
                    return True
                    
                accounts_list = sorted(list(self._active_accounts))
                if account_name in accounts_list:
                    # 如果消息还未被锁定，确保至少当前账户可以获得锁（防止所有账户都失败）
                    if fingerprint not in self._message_locks:
                        # 消息未被锁定，当前账户可以获得锁
                        self._message_locks[fingerprint] = (time.time(), account_name)
                        # 更新轮询索引，确保下次轮到下一个账户
                        current_index = accounts_list.index(account_name)
                        self._last_account_index = (current_index + 1) % len(accounts_list)
                        self._lock_count += 1
                        return True
                    else:
                        # 消息已被锁定，检查是否轮到当前账户
                        current_index = accounts_list.index(account_name)
                        expected_index = self._last_account_index % len(accounts_list)
                        if current_index == expected_index:
                            # 虽然已被锁定，但轮到了当前账户，更新锁（防止锁持有者已失效）
                            self._message_locks[fingerprint] = (time.time(), account_name)
                            self._last_account_index = (self._last_account_index + 1) % len(accounts_list)
                            self._lock_count += 1
                            return True
                return False
            elif self._queue_mode == "优先级":
                # 优先级模式：优先级最高的账户获得锁
                if not self._active_accounts:
                    self._message_locks[fingerprint] = (time.time(), account_name)
                    self._lock_count += 1
                    return True
                    
                # 如果消息还未被锁定，确保至少当前账户可以获得锁（防止所有账户都失败）
                if fingerprint not in self._message_locks:
                    # 消息未被锁定，当前账户可以获得锁
                    self._message_locks[fingerprint] = (time.time(), account_name)
                    self._lock_count += 1
                    return True
                
                # 获取所有账户的优先级
                account_priorities = {}
                for acc in self._active_accounts:
                    account_priorities[acc] = self._account_priority.get(acc, 0)
                    
                # 找到最高优先级的账户
                max_priority = max(account_priorities.values())
                highest_priority_accounts = [acc for acc, prio in account_priorities.items() if prio == max_priority]
                
                if account_name in highest_priority_accounts:
                    # 当前账户是最高优先级之一，可以更新锁（防止锁持有者已失效）
                    self._message_locks[fingerprint] = (time.time(), account_name)
                    self._lock_count += 1
                    return True
                return False
            elif self._queue_mode == "随机":
                # 随机模式：使用第一个可用策略（实际随机性由各账户独立决定）
                self._message_locks[fingerprint] = (time.time(), account_name)
                self._lock_count += 1
                return True
            else:
                # 默认：第一个可用
                self._message_locks[fingerprint] = (time.time(), account_name)
                self._lock_count += 1
                return True
                
    def release_message_lock(self, user: str, content: str, timestamp: float = None):
        """释放消息锁（可选，锁会在超时后自动释放）"""
        if timestamp is None:
            timestamp = time.time()
            
        fingerprint = self._generate_fingerprint(user, content, timestamp)
        
        with self._internal_lock:
            if fingerprint in self._message_locks:
                del self._message_locks[fingerprint]
                
    def is_message_locked(self, user: str, content: str, timestamp: float = None) -> bool:
        """检查消息是否已被锁定"""
        if timestamp is None:
            timestamp = time.time()
            
        fingerprint = self._generate_fingerprint(user, content, timestamp)
        
        with self._internal_lock:
            self._cleanup_expired_locks()
            if fingerprint in self._message_locks:
                lock_time, _ = self._message_locks[fingerprint]
                if time.time() - lock_time < self._lock_timeout:
                    return True
                else:
                    # 锁已过期，移除它
                    del self._message_locks[fingerprint]
            return False
            
    def record_sent_message(self, message_content: str):
        """
        记录发送的消息内容（全局，用于防止所有小号循环回复）
        
        Args:
            message_content: 发送的消息内容（字符串）
        """
        if not message_content:
            return
        
        now = time.time()
        with self._internal_lock:
            # 清理过期的消息记录
            self._global_sent_messages = [
                (msg, ts) for msg, ts in self._global_sent_messages
                if now - ts < self._global_message_ttl
            ]
            
            # 添加新消息记录
            self._global_sent_messages.append((message_content, now))
            
            # 限制记录数量
            if len(self._global_sent_messages) > self._max_global_messages:
                self._global_sent_messages = self._global_sent_messages[-self._max_global_messages:]
    
    def is_recent_sent_message(self, content: str) -> bool:
        """
        检查内容是否与最近发送的消息匹配（全局检查，包括所有小号）
        
        Args:
            content: 弹幕内容
            
        Returns:
            bool: 如果匹配最近发送的消息，返回True
        """
        if not content:
            return False
        
        now = time.time()
        with self._internal_lock:
            # 清理过期的消息记录
            self._global_sent_messages = [
                (msg, ts) for msg, ts in self._global_sent_messages
                if now - ts < self._global_message_ttl
            ]
            
            # 标准化弹幕内容（去除空格，用于匹配）
            content_normalized = content.strip().replace(' ', '').replace('　', '')  # 去除普通空格和全角空格
            
            # 检查是否与最近发送的消息匹配
            for sent_msg, _ in self._global_sent_messages:
                if not sent_msg:
                    continue
                
                # 标准化发送的消息（去除空格，用于匹配）
                sent_msg_normalized = sent_msg.strip().replace(' ', '').replace('　', '')
                
                # 1. 完全匹配（原始内容）
                if content.strip() == sent_msg.strip():
                    return True
                
                # 2. 标准化后的完全匹配（处理空格插入的情况）
                if content_normalized and sent_msg_normalized:
                    if content_normalized == sent_msg_normalized:
                        return True
                
                # 3. 包含匹配（去除空格后检查，更严格）
                # 如果发送的消息（去除空格后）完全包含在弹幕中（去除空格后），或反之
                # 只有当匹配的部分长度足够长时（>= 5个字符），才认为是循环
                min_match_length = 5
                if len(sent_msg_normalized) >= min_match_length and sent_msg_normalized in content_normalized:
                    return True
                if len(content_normalized) >= min_match_length and content_normalized in sent_msg_normalized:
                    return True
                
                # 4. 原始内容的包含匹配（保留，但要求更严格）
                # 只有当匹配的部分长度足够长时（>= 5个字符），才认为是循环
                if len(sent_msg.strip()) >= min_match_length and sent_msg.strip() in content:
                    return True
                if len(content.strip()) >= min_match_length and content.strip() in sent_msg:
                    return True
        
        return False
    
    def get_queue_stats(self) -> Dict:
        """获取队列统计信息"""
        with self._internal_lock:
            self._cleanup_expired_locks()
            return {
                'active_locks': len(self._message_locks),
                'active_accounts': len(self._active_accounts),
                'queue_mode': self._queue_mode,
                'time_window': self._time_window,
                'lock_timeout': self._lock_timeout,
                'strict_single_reply': self._strict_single_reply,
                'total_locks_created': self._lock_count
            }


# 全局单例实例
global_queue = GlobalMessageQueue()






