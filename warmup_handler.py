"""
暖场处理模块 - 处理多场景暖场逻辑
"""
import time
import random

class WarmupHandler:
    """暖场处理器 - 负责在无弹幕时自动发送暖场消息（支持多规则多场景）"""
    
    def __init__(self, cfg, log_callback=None):
        """
        初始化暖场处理器
        
        Args:
            cfg: 配置字典引用
            log_callback: 日志回调函数
        """
        self.cfg = cfg
        self.log_callback = log_callback
        self.enabled = False
        self.rule_last_t = {}  # 每个规则的冷却时间记录（只在功能启用时使用）
        self.first_danmu_received = False  # 是否已收到首条弹幕（用于防止异常情况）
        self.enabled_since = None  # 功能启用的时间戳（用于确保计时器只在启用后开始）
        
    def set_enabled(self, enabled):
        """
        设置暖场开关
        
        Args:
            enabled: True表示启用，False表示禁用
        """
        was_enabled = self.enabled
        self.enabled = enabled
        
        if enabled:
            # 功能被启用：初始化计时器（如果之前未启用，则开始新的计时周期）
            if not was_enabled:
                # 之前未启用，现在启用：重置所有计时器，开始新的计时周期
                self.rule_last_t = {}
                self.first_danmu_received = False
                self.enabled_since = time.time()
                if self.log_callback:
                    self.log_callback(f"<span style='color:#DA70D6;'>【暖场功能】</span> 已启用，计时器已初始化")
        else:
            # 功能被禁用：重置计时器，避免下次启用时使用旧的计时数据
            if was_enabled:
                self.rule_last_t = {}
                self.first_danmu_received = False
                self.enabled_since = None
                if self.log_callback:
                    self.log_callback(f"<span style='color:#DA70D6;'>【暖场功能】</span> 已禁用，计时器已重置")
    
    def get_state(self):
        """
        获取暖场处理器的状态（用于保存和恢复）
        注意：只有在功能启用时才保存状态，禁用时不保存
        """
        if not self.enabled:
            # 功能未启用，不保存状态
            return None
        return {
            'rule_last_t': self.rule_last_t.copy(),
            'first_danmu_received': self.first_danmu_received,
            'enabled_since': self.enabled_since
        }
    
    def restore_state(self, state):
        """
        恢复暖场处理器的状态（用于避免重新初始化时重置计时器）
        注意：只有在功能启用时才恢复状态，禁用时不恢复
        """
        if not self.enabled:
            # 功能未启用，不恢复状态（保持重置状态）
            return
        if state and isinstance(state, dict):
            # 只有在功能启用时才恢复状态
            self.rule_last_t = state.get('rule_last_t', {}).copy()
            self.first_danmu_received = state.get('first_danmu_received', False)
            self.enabled_since = state.get('enabled_since', None)
    
    def set_frequency(self, frequency):
        """设置暖场频率（秒）- 保留兼容性，但不再使用"""
        # 新版本使用规则的cooldown，此方法保留兼容性
        pass
    
    def set_no_danmu_time(self, no_danmu_time):
        """设置无弹幕时间（秒）- 保留兼容性，但不再使用"""
        # 新版本使用规则的min_no_danmu_time，此方法保留兼容性
        pass
    
    def should_warmup(self, has_pending_messages=False, last_danmu_time=None):
        """
        检查是否应该触发暖场
        
        Args:
            has_pending_messages: 是否有待发送消息
            last_danmu_time: 最后一次收到弹幕的时间（time.time()），如果为None则表示还未收到弹幕
            
        Returns:
            str or None: 如果需要暖场返回消息内容，否则返回None
        """
        # 功能未启用，直接返回None（不进行任何计时检查）
        if not self.enabled:
            return None
        
        # 确保计时器已初始化（如果功能刚启用，enabled_since应该已设置）
        if self.enabled_since is None:
            # 如果enabled_since未设置，说明状态异常，初始化它
            self.enabled_since = time.time()
            self.rule_last_t = {}
            self.first_danmu_received = False
            
        # 如果有待发送消息，不触发暖场
        if has_pending_messages:
            return None
        
        # 必须检测捕获到首条弹幕才开始计时，以防异常情况
        if last_danmu_time is None:
            # 还未收到弹幕，不触发暖场
            return None
        
        # 标记已收到首条弹幕（只在功能启用后标记）
        if not self.first_danmu_received:
            self.first_danmu_received = True
        
        now = time.time()
        
        # 优先使用新的warmup_rules规则系统
        rules = self.cfg.get('warmup_rules', [])
        
        if rules:
            # 新规则系统：多规则多场景（支持无弹幕触发和定时触发）
            return self._process_warmup_rules(rules, last_danmu_time, now)
        else:
            # 兼容旧版本：使用warmup_msgs
            return self._process_legacy_warmup(last_danmu_time, now)
    
    def _process_warmup_rules(self, rules, last_danmu_time, now):
        """处理新的多规则暖场系统（支持无弹幕触发和定时触发）"""
        # 必须检测捕获到首条弹幕才开始计时，以防异常情况
        # 注意：last_danmu_time 在 should_warmup 中已经检查过不为 None，这里可以安全使用
        
        # 筛选出激活的规则
        active_rules = [(i, rule) for i, rule in enumerate(rules) if rule.get('active', True)]
        if not active_rules:
            return None
        
        matched_rules = []
        
        # 分别处理定时触发和无弹幕触发规则
        for i, rule in active_rules:
            trigger_type = rule.get('trigger_type', '无弹幕触发')
            last_trigger_time = self.rule_last_t.get(i, 0)
            cooldown = rule.get('cooldown', 60)
            
            if trigger_type == '定时触发':
                # 定时触发：按时间间隔触发（但必须已收到首条弹幕）
                # 检查是否到了触发时间（cooldown作为时间间隔）
                if now - last_trigger_time >= cooldown:
                    matched_rules.append((i, rule))
            else:
                # 无弹幕触发：基于无弹幕时间范围
                # last_danmu_time 已经确保不为 None（在 should_warmup 中检查）
                time_since_last_danmu = now - last_danmu_time
                min_time = rule.get('min_no_danmu_time', 120)
                max_time = rule.get('max_no_danmu_time', 0)  # 0表示无上限
                
                # 检查时间范围
                if time_since_last_danmu < min_time:
                    continue
                if max_time > 0 and time_since_last_danmu > max_time:
                    continue
                
                # 检查冷却时间
                if now - last_trigger_time < cooldown:
                    continue
                
                matched_rules.append((i, rule))
        
        if not matched_rules:
            return None
        
        # 从匹配的规则中随机选择一个（增加随机性，避免总是使用同一个规则）
        rule_index, rule = random.choice(matched_rules)
        
        # 生成消息
        messages = self._generate_messages(rule, rule_index)
        if not messages:
            return None
        
        # 更新冷却时间/最后触发时间
        self.rule_last_t[rule_index] = now
        
        rule_name = rule.get('name', f'规则{rule_index+1}')
        trigger_type = rule.get('trigger_type', '无弹幕触发')
        
        if self.log_callback:
            if trigger_type == '定时触发':
                self.log_callback(
                    f"<span style='color:#DA70D6;'>【暖场触发-定时】</span> {rule_name} "
                    f"(间隔{rule.get('cooldown', 60)}秒，生成 {len(messages)} 条消息)"
                )
            else:
                time_since_last_danmu = now - last_danmu_time if last_danmu_time else 0
                self.log_callback(
                    f"<span style='color:#DA70D6;'>【暖场触发】</span> {rule_name} "
                    f"(无弹幕{int(time_since_last_danmu)}秒，生成 {len(messages)} 条消息)"
                )
        
        # 返回消息列表（顺序全发模式会返回多条，随机挑一返回一条）
        return messages if messages else None
    
    def _process_legacy_warmup(self, last_danmu_time, now):
        """处理旧版本的暖场逻辑（兼容性）"""
        # 获取旧的暖场消息池
        warmup_msgs = self.cfg.get('warmup_msgs', '')
        pool = [m.strip() for m in warmup_msgs.split('|') if m.strip()]
        
        if not pool:
            return None
        
        # 检查时间间隔（使用默认值）
        if last_danmu_time is not None:
            time_since_last_danmu = now - last_danmu_time
            if time_since_last_danmu < 120:  # 默认2分钟
                return None
        
        # 检查全局冷却（使用默认频率）
        if not hasattr(self, 'last_warmup_t'):
            self.last_warmup_t = 0
        if now - self.last_warmup_t < 60:  # 默认1分钟
            return None
        
        # 更新最后暖场时间
        self.last_warmup_t = now
        
        # 随机选择一条消息
        message = random.choice(pool)
        
        if self.log_callback:
            self.log_callback(f"<span style='color:#DA70D6;'>【暖场触发】</span> 任务已加入队列")
        
        return message
    
    def _generate_messages(self, rule, rule_index=None):
        """
        根据规则生成消息列表
        
        Args:
            rule: 规则字典
            rule_index: 规则索引（用于顺序全发模式的跟踪）
            
        Returns:
            list: 消息列表
        """
        messages_str = rule.get('messages', '')
        mode = rule.get('mode', '随机挑一')
        
        # 解析消息池
        msgs = [m.strip() for m in messages_str.split('|') if m.strip()]
        if not msgs:
            return []
        
        # 根据模式处理
        if mode == "随机挑一":
            return [random.choice(msgs)]
        else:  # 顺序全发
            # 顺序全发模式：返回所有消息（由消息队列按顺序发送）
            return msgs
