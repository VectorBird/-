"""
回复处理模块 - 处理关键词回复和特定回复逻辑
"""
import time
import random
import os
import re
import string
from datetime import datetime
from global_message_queue import global_queue
from statistics_manager import statistics_manager

# 尝试导入AI回复模块（可选功能）
try:
    from ai_reply_handler import AIReplyHandler
    AI_REPLY_AVAILABLE = True
except ImportError:
    AI_REPLY_AVAILABLE = False
    print("[回复处理器] AI回复功能不可用（缺少ai_reply_handler模块或依赖）")

# 调试日志文件路径
_debug_log_file = None

def _get_debug_log_file():
    """获取调试日志文件路径"""
    global _debug_log_file
    if _debug_log_file is None:
        try:
            from path_utils import get_log_dir
            log_dir = get_log_dir()
        except ImportError:
            log_dir = "logs"
            os.makedirs(log_dir, exist_ok=True)
        _debug_log_file = os.path.join(log_dir, "reply_debug.log")
    return _debug_log_file

def _write_debug_log(message):
    """写入调试日志到文件"""
    try:
        log_file = _get_debug_log_file()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")
            f.flush()
    except Exception as e:
        # 记录日志写入错误（但不影响主流程）
        try:
            import sys
            print(f"[回复处理器-日志错误] 写入调试日志失败: {type(e).__name__}: {str(e)}", file=sys.stderr)
        except:
            pass  # 如果连打印都失败，完全忽略

class ReplyHandler:
    """回复处理器 - 负责关键词匹配和回复生成"""
    
    def __init__(self, cfg, log_callback=None, account_name=None):
        """
        初始化回复处理器
        
        Args:
            cfg: 配置字典引用
            log_callback: 日志回调函数
            account_name: 账户名称（多小号模式时需要）
        """
        self.cfg = cfg
        self.log_callback = log_callback
        self.account_name = account_name or "default"
        self.rule_last_t = {}  # 关键词规则冷却时间记录
        self.spec_last_t = {}  # 特定规则冷却时间记录
        self.advanced_last_t = {}  # 高级回复规则冷却时间记录
        
        # 注意：防止循环回复现在使用全局消息队列，不再使用本地记录
        
        # 初始化功能开关（从配置中读取，避免未初始化的问题）
        self.auto_reply_enabled = cfg.get('auto_reply_enabled', False)
        self.specific_reply_enabled = cfg.get('specific_reply_enabled', False)
        self.advanced_reply_enabled = cfg.get('advanced_reply_enabled', False)
        # AI功能默认禁用，只有CDK授权后才能启用
        self.ai_reply_enabled = cfg.get('ai_reply_enabled', False)
        
        # 检查AI功能授权状态
        self.ai_authorized = False
        self.ai_cdk = None
        try:
            from server_client import check_feature_auth
            auth_status = check_feature_auth()
            self.ai_authorized = auth_status.get('ai_reply', False)
            # 如果已授权，获取CDK代码（用于token消耗上报）
            if self.ai_authorized:
                self.ai_cdk = cfg.get('ai_reply_cdk')
        except Exception as e:
            import traceback
            error_msg = f"[异常] AI授权检查失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
            _write_debug_log(error_msg)
            _write_debug_log(f"堆栈: {traceback.format_exc()}")
            print(error_msg)
            print(traceback.format_exc())
            import sys
            sys.stdout.flush()
            self.ai_authorized = False
        
        # 如果未授权，强制禁用AI功能
        if not self.ai_authorized:
            self.ai_reply_enabled = False
        
        # 初始化AI回复处理器（如果可用且启用且已授权）
        self.ai_reply_handler = None
        if AI_REPLY_AVAILABLE and self.ai_reply_enabled and self.ai_authorized:
            api_key = cfg.get('ai_reply_api_key', '')
            system_prompt = cfg.get('ai_reply_system_prompt', '')
            max_history = cfg.get('ai_reply_max_history', 5)
            
            # 如果使用预设角色（服装类），根据配置生成系统提示词
            ai_role = cfg.get('ai_reply_role', 'custom')
            if ai_role == 'clothing' and not system_prompt:
                category = cfg.get('ai_reply_clothing_category', '服装')
                height = cfg.get('ai_reply_clothing_height', 165)
                weight = cfg.get('ai_reply_clothing_weight', 55)
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
            
            # 获取过滤配置
            filter_config = {
                'min_length': cfg.get('ai_reply_filter_min_length', 2),
                'filter_emoji_only': cfg.get('ai_reply_filter_emoji_only', True),
                'filter_numbers_only': cfg.get('ai_reply_filter_numbers_only', True),
                'filter_punctuation_only': cfg.get('ai_reply_filter_punctuation_only', True),
                'filter_repeated_chars': cfg.get('ai_reply_filter_repeated_chars', True),
                'filter_keywords': cfg.get('ai_reply_filter_keywords', []),
                'require_keywords': cfg.get('ai_reply_require_keywords', False),
            }
            
            if api_key:
                try:
                    self.ai_reply_handler = AIReplyHandler(
                        api_key=api_key,
                        system_prompt=system_prompt,
                        max_history=max_history,
                        filter_config=filter_config,
                        cdk=self.ai_cdk  # 传递CDK用于token消耗上报
                    )
                    _write_debug_log(f"[AI回复] 初始化成功，max_history={max_history}, role={ai_role}, filter_config={filter_config}, cdk={'已设置' if self.ai_cdk else '未设置'}")
                except Exception as e:
                    import traceback
                    error_msg = f"[异常] AI回复处理器初始化失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
                    _write_debug_log(error_msg)
                    _write_debug_log(f"堆栈: {traceback.format_exc()}")
                    print(error_msg)
                    print(traceback.format_exc())
                    import sys
                    sys.stdout.flush()
                    self.ai_reply_handler = None
            else:
                _write_debug_log("[AI回复] API Key未配置，AI回复功能未启用")
        elif not self.ai_authorized:
            _write_debug_log("[AI回复] AI功能未授权，需要CDK激活")
        elif not AI_REPLY_AVAILABLE:
            _write_debug_log("[AI回复] AI回复模块不可用")
        
        # 调试日志：记录初始化信息
        reply_rules = cfg.get('reply_rules', [])
        specific_rules = cfg.get('specific_rules', [])
        advanced_rules = cfg.get('advanced_reply_rules', [])
        reply_rules_count = len(reply_rules) if isinstance(reply_rules, list) else 0
        specific_rules_count = len(specific_rules) if isinstance(specific_rules, list) else 0
        advanced_rules_count = len(advanced_rules) if isinstance(advanced_rules, list) else 0
        
        _write_debug_log(f"[初始化] 账户: {account_name or 'default'}, "
                        f"auto_reply_enabled={self.auto_reply_enabled}, "
                        f"specific_reply_enabled={self.specific_reply_enabled}, "
                        f"advanced_reply_enabled={self.advanced_reply_enabled}, "
                        f"关键词规则数={reply_rules_count}, 特定规则数={specific_rules_count}, "
                        f"高级回复规则数={advanced_rules_count}")
        
        # 记录高级回复规则详情
        if isinstance(advanced_rules, list) and advanced_rules:
            for i, rule in enumerate(advanced_rules):
                if isinstance(rule, dict):
                    pattern = rule.get('pattern', '')
                    active = rule.get('active', True)
                    ignore_punct = rule.get('ignore_punctuation', True)
                    _write_debug_log(f"  高级规则{i}: pattern='{pattern}', active={active}, "
                                    f"ignore_punctuation={ignore_punct}, "
                                    f"resp='{str(rule.get('resp', ''))[:50]}...'")
                else:
                    _write_debug_log(f"  高级规则{i}: 类型错误 type={type(rule)}")
        
        # 记录规则详情
        if isinstance(reply_rules, list) and reply_rules:
            for i, rule in enumerate(reply_rules):
                if isinstance(rule, dict):
                    kw = rule.get('kw', '')
                    active = rule.get('active', True)
                    _write_debug_log(f"  规则{i}: kw='{kw}', active={active}, "
                                    f"resp='{str(rule.get('resp', ''))[:50]}...', "
                                    f"mode={rule.get('mode', 'N/A')}")
                else:
                    _write_debug_log(f"  规则{i}: 类型错误 type={type(rule)}")
        
        # 注册账户到全局队列
        if account_name:
            global_queue.register_account(account_name)
        
    def set_enabled(self, auto_reply, specific_reply, advanced_reply=None, ai_reply=None):
        """设置功能开关"""
        self.auto_reply_enabled = auto_reply
        self.specific_reply_enabled = specific_reply
        if advanced_reply is not None:
            self.advanced_reply_enabled = advanced_reply
        if ai_reply is not None:
            # 检查授权状态
            try:
                from server_client import check_feature_auth
                auth_status = check_feature_auth()
                self.ai_authorized = auth_status.get('ai_reply', False)
                if self.ai_authorized:
                    self.ai_cdk = self.cfg.get('ai_reply_cdk')
                else:
                    self.ai_cdk = None
            except Exception:
                self.ai_authorized = False
                self.ai_cdk = None
            
            # 如果未授权，强制禁用
            if not self.ai_authorized:
                self.ai_reply_enabled = False
                ai_reply = False
            else:
                self.ai_reply_enabled = ai_reply
            
            # 如果启用AI回复，重新初始化AI处理器
            if ai_reply and AI_REPLY_AVAILABLE and self.ai_authorized:
                api_key = self.cfg.get('ai_reply_api_key', '')
                system_prompt = self.cfg.get('ai_reply_system_prompt', '')
                max_history = self.cfg.get('ai_reply_max_history', 5)
                # 获取过滤配置
                filter_config = {
                    'min_length': self.cfg.get('ai_reply_filter_min_length', 2),
                    'filter_emoji_only': self.cfg.get('ai_reply_filter_emoji_only', True),
                    'filter_numbers_only': self.cfg.get('ai_reply_filter_numbers_only', True),
                    'filter_punctuation_only': self.cfg.get('ai_reply_filter_punctuation_only', True),
                    'filter_repeated_chars': self.cfg.get('ai_reply_filter_repeated_chars', True),
                    'filter_keywords': self.cfg.get('ai_reply_filter_keywords', []),
                    'require_keywords': self.cfg.get('ai_reply_require_keywords', False),
                }
                
                if api_key:
                    try:
                        self.ai_reply_handler = AIReplyHandler(
                            api_key=api_key,
                            system_prompt=system_prompt,
                            max_history=max_history,
                            filter_config=filter_config,
                            cdk=self.ai_cdk  # 传递CDK用于token消耗上报
                        )
                    except Exception as e:
                        _write_debug_log(f"[AI回复] 重新初始化失败: {e}")
                        self.ai_reply_handler = None
                elif self.ai_reply_handler:
                    # 如果处理器已存在，只更新过滤配置和CDK
                    self.ai_reply_handler.set_filter_config(filter_config)
                    self.ai_reply_handler.set_cdk(self.ai_cdk)
            elif not ai_reply:
                self.ai_reply_handler = None
    
    def record_sent_message(self, message_content):
        """
        记录发送的消息内容（用于防止循环回复，全局共享）
        
        Args:
            message_content: 发送的消息内容（字符串）
        """
        # 使用全局消息队列记录，所有小号共享
        global_queue.record_sent_message(message_content)
        
    def process_danmu(self, user, content):
        """
        处理弹幕，匹配规则并生成回复消息
        
        Args:
            user: 用户名
            content: 弹幕内容
            
        Returns:
            list: 需要发送的消息列表，如果无匹配或已被其他账户处理则返回空列表
        """
        if not user or not content:
            return []
        
        # 检查是否是最近发送的消息（防止循环回复，包括自己和其他小号的消息）
        if global_queue.is_recent_sent_message(content):
            # 静默运行，只记录到调试日志，不在UI中显示
            _write_debug_log(f"[处理弹幕] 跳过循环回复: 内容 '{content[:50]}' 匹配最近发送的消息（全局）")
            return []
        
        # 调试日志：记录弹幕处理开始
        _write_debug_log(f"[处理弹幕] 用户: {user}, 内容: {content[:100]}, "
                        f"auto_reply={self.auto_reply_enabled}, specific_reply={self.specific_reply_enabled}, "
                        f"advanced_reply={self.advanced_reply_enabled}")
        
        # 检查功能开关（调试用）
        if not self.auto_reply_enabled and not self.specific_reply_enabled and not self.advanced_reply_enabled and not self.ai_reply_enabled:
            # 如果所有功能都关闭，直接返回（不记录日志，避免日志过多）
            _write_debug_log(f"  [跳过] 所有回复功能都已禁用")
            return []
            
        # 检查是否允许多小号同时回复
        allow_multiple_reply = self.cfg.get('allow_multiple_reply', False)
        
        # 如果不允许多小号同时回复，则尝试锁定消息（防止多小号重复回复）
        timestamp = time.time()
        if not allow_multiple_reply:
            if not global_queue.try_lock_message(user, content, self.account_name, timestamp):
                if self.log_callback:
                    self.log_callback(
                        f"<span style='color:gray;'>[队列跳过]</span> 弹幕已被其他账户处理: {user}: {content[:20]}..."
                    )
                return []
            
        now = time.time()
        messages = []
        
        try:
            # 处理特定回复（优先）
            if self.specific_reply_enabled:
                _write_debug_log(f"  [开始] 处理特定回复")
                messages = self._process_specific_reply(user, content, now)
                if messages:
                    _write_debug_log(f"  [结果] 特定回复匹配成功，生成{len(messages)}条消息")
                    return messages
                else:
                    _write_debug_log(f"  [结果] 特定回复未匹配")
            else:
                _write_debug_log(f"  [跳过] 特定回复功能已禁用")
                    
            # 处理高级回复（正则表达式匹配，优先于关键词回复）
            if self.advanced_reply_enabled:
                _write_debug_log(f"  [开始] 处理高级回复（正则表达式）")
                messages = self._process_advanced_reply(user, content, now)
                if messages:
                    _write_debug_log(f"  [结果] 高级回复匹配成功，生成{len(messages)}条消息")
                    return messages
                else:
                    _write_debug_log(f"  [结果] 高级回复未匹配")
            else:
                _write_debug_log(f"  [跳过] 高级回复功能已禁用，advanced_reply_enabled={self.advanced_reply_enabled}")
                    
            # 处理关键词回复
            if self.auto_reply_enabled:
                _write_debug_log(f"  [开始] 处理关键词回复")
                messages = self._process_keyword_reply(user, content, now)
                if messages:
                    _write_debug_log(f"  [结果] 关键词回复匹配成功，生成{len(messages)}条消息")
                else:
                    _write_debug_log(f"  [结果] 关键词回复未匹配")
            else:
                _write_debug_log(f"  [跳过] 关键词回复功能已禁用，auto_reply_enabled={self.auto_reply_enabled}")
            
            # 处理AI回复（作为后备选项，当其他规则都不匹配时使用）
            # 需要同时满足：启用、已授权、处理器已初始化
            if not messages and self.ai_reply_enabled and self.ai_authorized and self.ai_reply_handler:
                _write_debug_log(f"  [开始] 处理AI回复（后备模式）")
                try:
                    ai_reply = self.ai_reply_handler.get_reply(user, content)
                    if ai_reply:
                        messages = [ai_reply]
                        _write_debug_log(f"  [结果] AI回复成功: {ai_reply[:50]}...")
                    else:
                        _write_debug_log(f"  [结果] AI回复失败或返回空")
                except Exception as e:
                    import traceback
                    error_msg = f"[异常] AI回复处理异常 | 类型: {type(e).__name__} | 错误: {str(e)}"
                    _write_debug_log(error_msg)
                    _write_debug_log(f"堆栈: {traceback.format_exc()}")
                    print(error_msg)
                    print(traceback.format_exc())
                    import sys
                    sys.stdout.flush()
                    messages = []
            elif not messages and self.ai_reply_enabled and not self.ai_authorized:
                _write_debug_log(f"  [跳过] AI回复功能已启用但未授权（需要CDK激活）")
            elif not messages and self.ai_reply_enabled and not self.ai_reply_handler:
                _write_debug_log(f"  [跳过] AI回复功能已启用但处理器未初始化")
                
            # 如果没有匹配到规则，记录未匹配的弹幕（用于统计高频未匹配关键词）
            if not messages:
                # 只有在回复功能启用的情况下才记录（避免记录因功能关闭而未回复的弹幕）
                if self.auto_reply_enabled or self.specific_reply_enabled:
                    statistics_manager.record_unmatched_danmu(content)
                
                # 释放锁（仅在不允许多回复模式下）
                if not allow_multiple_reply:
                    global_queue.release_message_lock(user, content, timestamp)
                
            return messages
        except Exception as e:
            import traceback
            # 发生异常时释放锁（仅在不允许多回复模式下）
            if not allow_multiple_reply:
                try:
                    global_queue.release_message_lock(user, content, timestamp)
                except Exception as release_error:
                    _write_debug_log(f"[异常] 释放消息锁失败: {release_error}")
            
            # 调试日志：记录异常
            error_msg = f"[异常] 处理弹幕回复异常 | 类型: {type(e).__name__} | 错误: {str(e)} | 用户: {user} | 内容: {content[:50]}"
            _write_debug_log(error_msg)
            _write_debug_log(f"堆栈: {traceback.format_exc()}")
            print(error_msg)
            print(traceback.format_exc())
            import sys
            sys.stdout.flush()
            import traceback
            error_detail = traceback.format_exc()
            _write_debug_log(f"  [异常] 处理弹幕时发生异常: {e}")
            _write_debug_log(f"  [异常详情] {error_detail}")
            
            if self.log_callback:
                self.log_callback(f"<span style='color:red;'>[错误]</span> 处理弹幕时发生异常: {e}")
            return []
        
    def _process_specific_reply(self, user, content, now):
        """处理特定回复规则（优先匹配更长的关键词）"""
        rules = self.cfg.get('specific_rules', [])
        
        # 检查规则列表是否存在且为列表类型
        if not isinstance(rules, list) or not rules:
            return []
        
        # 先筛选出激活的规则并按关键词长度降序排序（长的优先）
        # 确保rule是字典类型
        active_rules = []
        for i, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            if rule.get('active', True):
                active_rules.append((i, rule))
        
        if not active_rules:
            return []
        # 按关键词长度降序排序（使用最长的关键词长度进行排序）
        def get_max_keyword_length(rule_item):
            kw_str = rule_item[1].get('kw', '')
            if '|' in kw_str:
                # 如果有多个关键词，取最长的那个
                keywords = [k.strip() for k in kw_str.split('|') if k.strip()]
                return max(len(k) for k in keywords) if keywords else 0
            return len(kw_str)
        active_rules.sort(key=get_max_keyword_length, reverse=True)
        
        for i, rule in active_rules:
            keyword_str = rule.get('kw', '')
            if not keyword_str:
                continue
            
            # 支持|分隔的多个关键词，只要其中任意一个匹配即可
            keywords = [k.strip() for k in keyword_str.split('|') if k.strip()]
            if not keywords:
                continue
            
            # 检查是否有任意关键词匹配
            matched_keyword = None
            for kw in keywords:
                if kw in content:
                    matched_keyword = kw
                    break
            
            if not matched_keyword:
                continue
            
            keyword = keyword_str  # 使用完整的关键词字符串用于日志显示
                
            # 检查冷却时间
            diff = now - self.spec_last_t.get(i, 0)
            cooldown = rule.get('cooldown', 15)
            if diff < cooldown:
                if self.log_callback:
                    display_keyword = keyword_str if '|' not in keyword_str else keyword_str.split('|')[0].strip() + '...'
                    self.log_callback(
                        f"<span style='color:gray;'>[冷却中] 特定规则 '{display_keyword}' 剩余 {int(cooldown-diff)}s</span>"
                    )
                return []
                
            # 生成回复消息
            self.spec_last_t[i] = now
            start_time = time.time()
            messages = self._generate_messages(rule, user, prefix=f"@{user} ")
            response_time = time.time() - start_time
            
            # 记录统计（使用匹配到的关键词）
            statistics_manager.record_reply(self.account_name, matched_keyword)
            statistics_manager.record_response_time(self.account_name, response_time)
            
            if self.log_callback:
                # 如果关键词包含|，显示匹配到的那个
                display_keyword = matched_keyword if '|' in keyword_str else keyword_str
                self.log_callback(
                    f"<span style='color:#FF4500;'>【特定命中】</span> {display_keyword} (生成 {len(messages)} 条消息)"
                )
                
            return messages
            
        return []
        
    def _process_keyword_reply(self, user, content, now):
        """处理关键词回复规则（优先匹配更长的关键词）"""
        rules = self.cfg.get('reply_rules', [])
        
        # 调试日志：记录规则列表状态
        _write_debug_log(f"    [关键词回复] 获取规则列表: type={type(rules)}, "
                        f"len={len(rules) if isinstance(rules, list) else 'N/A'}")
        
        # 检查规则列表是否存在且为列表类型
        if not isinstance(rules, list) or not rules:
            _write_debug_log(f"    [关键词回复] 规则列表为空或类型错误，返回空列表")
            return []
        
        # 先筛选出激活的规则并按关键词长度降序排序（长的优先）
        # 确保rule是字典类型
        active_rules = []
        for i, rule in enumerate(rules):
            if not isinstance(rule, dict):
                _write_debug_log(f"    [关键词回复] 规则{i}不是字典类型: type={type(rule)}")
                continue
            active = rule.get('active', True)
            kw = rule.get('kw', '')
            if active:
                active_rules.append((i, rule))
                _write_debug_log(f"    [关键词回复] 规则{i}激活: kw='{kw}'")
            else:
                _write_debug_log(f"    [关键词回复] 规则{i}未激活: kw='{kw}'")
        
        _write_debug_log(f"    [关键词回复] 激活规则数: {len(active_rules)}/{len(rules)}")
        
        if not active_rules:
            _write_debug_log(f"    [关键词回复] 没有激活的规则，返回空列表")
            return []
        # 按关键词长度降序排序（使用最长的关键词长度进行排序）
        def get_max_keyword_length(rule_item):
            kw_str = rule_item[1].get('kw', '')
            if '|' in kw_str:
                # 如果有多个关键词，取最长的那个
                keywords = [k.strip() for k in kw_str.split('|') if k.strip()]
                return max(len(k) for k in keywords) if keywords else 0
            return len(kw_str)
        active_rules.sort(key=get_max_keyword_length, reverse=True)
        
        for i, rule in active_rules:
            keyword_str = rule.get('kw', '')
            if not keyword_str:
                _write_debug_log(f"      [规则{i}] 关键词为空，跳过")
                continue
            
            # 支持|分隔的多个关键词，只要其中任意一个匹配即可
            keywords = [k.strip() for k in keyword_str.split('|') if k.strip()]
            if not keywords:
                _write_debug_log(f"      [规则{i}] 关键词'{keyword_str}'解析后为空，跳过")
                continue
            
            _write_debug_log(f"      [规则{i}] 检查关键词: '{keyword_str}' -> {keywords}")
            
            # 检查是否有任意关键词匹配
            matched_keyword = None
            for kw in keywords:
                if kw in content:
                    matched_keyword = kw
                    _write_debug_log(f"      [规则{i}] 关键词'{kw}'匹配成功")
                    break
            
            if not matched_keyword:
                _write_debug_log(f"      [规则{i}] 关键词未匹配，继续下一个规则")
                continue
            
            keyword = keyword_str  # 使用完整的关键词字符串用于日志显示
                
            # 检查冷却时间
            diff = now - self.rule_last_t.get(i, 0)
            cooldown = rule.get('cooldown', 15)
            _write_debug_log(f"      [规则{i}] 冷却检查: diff={diff:.2f}s, cooldown={cooldown}s, "
                           f"last_t={self.rule_last_t.get(i, 0)}, now={now}")
            if diff < cooldown:
                _write_debug_log(f"      [规则{i}] 冷却中，剩余{int(cooldown-diff)}s，返回空列表")
                if self.log_callback:
                    display_keyword = keyword_str if '|' not in keyword_str else keyword_str.split('|')[0].strip() + '...'
                    self.log_callback(
                        f"<span style='color:gray;'>[冷却中] 关键词 '{display_keyword}' 剩余 {int(cooldown-diff)}s</span>"
                    )
                return []
                
            # 生成回复消息
            _write_debug_log(f"      [规则{i}] 开始生成回复消息")
            self.rule_last_t[i] = now
            start_time = time.time()
            messages = self._generate_messages(rule, user)
            response_time = time.time() - start_time
            
            _write_debug_log(f"      [规则{i}] 生成消息完成: {len(messages)}条，耗时{response_time:.3f}s")
            if messages:
                for idx, msg in enumerate(messages):
                    _write_debug_log(f"        消息{idx}: {msg[:100]}")
            
            # 记录统计（使用匹配到的关键词）
            statistics_manager.record_reply(self.account_name, matched_keyword)
            statistics_manager.record_response_time(self.account_name, response_time)
            
            if self.log_callback:
                # 如果关键词包含|，显示匹配到的那个
                display_keyword = matched_keyword if '|' in keyword_str else keyword_str
                self.log_callback(
                    f"<span style='color:#FFD700;'>【关键词命中】</span> {display_keyword} (生成 {len(messages)} 条消息)"
                )
                
            return messages
            
        _write_debug_log(f"    [关键词回复] 所有规则检查完毕，未匹配，返回空列表")
        return []
        
    def _generate_messages(self, rule, user, prefix=""):
        """
        根据规则生成消息列表
        
        Args:
            rule: 规则字典
            user: 用户名（用于替换[昵称]占位符）
            prefix: 消息前缀（特定回复使用）
            
        Returns:
            list: 消息列表
        """
        if not isinstance(rule, dict):
            _write_debug_log(f"        [生成消息] rule不是字典类型: {type(rule)}")
            return []
        
        resp = rule.get('resp', '')
        if not isinstance(resp, str):
            resp = str(resp) if resp else ''
        
        mode = rule.get('mode', '随机挑一')
        _write_debug_log(f"        [生成消息] resp长度={len(resp)}, mode={mode}, prefix={prefix}")
        
        # 解析回复池
        try:
            msgs = [p.strip() for p in resp.split('|') if p.strip()]
            _write_debug_log(f"        [生成消息] 解析后消息数: {len(msgs)}")
        except (AttributeError, TypeError) as e:
            _write_debug_log(f"        [生成消息] 解析回复池异常: {e}")
            return []
        
        if not msgs:
            _write_debug_log(f"        [生成消息] 消息列表为空，返回空列表")
            return []
            
        # 替换占位符
        msgs = [msg.replace("[昵称]", user) for msg in msgs]
        
        # 根据模式处理
        if mode == "随机挑一":
            final = [random.choice(msgs)]
            _write_debug_log(f"        [生成消息] 随机模式，选择1条")
        else:  # 顺序全发
            final = msgs
            _write_debug_log(f"        [生成消息] 顺序模式，全部{len(msgs)}条")
            
        # 添加前缀
        if prefix:
            final = [prefix + msg for msg in final]
            
        _write_debug_log(f"        [生成消息] 最终生成{len(final)}条消息")
        return final
    
    def _process_advanced_reply(self, user, content, now):
        """处理高级回复规则（使用正则表达式匹配）"""
        import re
        
        rules = self.cfg.get('advanced_reply_rules', [])
        
        # 调试日志：记录规则列表状态
        _write_debug_log(f"    [高级回复] 获取规则列表: type={type(rules)}, "
                        f"len={len(rules) if isinstance(rules, list) else 'N/A'}")
        
        # 检查规则列表是否存在且为列表类型
        if not isinstance(rules, list) or not rules:
            _write_debug_log(f"    [高级回复] 规则列表为空或类型错误，返回空列表")
            return []
        
        # 先筛选出激活的规则
        active_rules = []
        for i, rule in enumerate(rules):
            if not isinstance(rule, dict):
                _write_debug_log(f"    [高级回复] 规则{i}不是字典类型: type={type(rule)}")
                continue
            active = rule.get('active', True)
            pattern = rule.get('pattern', '')
            if active and pattern:
                active_rules.append((i, rule))
                _write_debug_log(f"    [高级回复] 规则{i}激活: pattern='{pattern}'")
            else:
                _write_debug_log(f"    [高级回复] 规则{i}未激活或pattern为空: active={active}, pattern='{pattern}'")
        
        _write_debug_log(f"    [高级回复] 激活规则数: {len(active_rules)}/{len(rules)}")
        
        if not active_rules:
            _write_debug_log(f"    [高级回复] 没有激活的规则，返回空列表")
            return []
        
        # 按规则索引顺序匹配（第一个匹配的规则生效）
        for i, rule in active_rules:
            pattern = rule.get('pattern', '')
            if not pattern:
                _write_debug_log(f"      [规则{i}] pattern为空，跳过")
                continue
            
            _write_debug_log(f"      [规则{i}] 检查正则表达式: '{pattern}'")
            
            # 尝试编译正则表达式
            try:
                regex = re.compile(pattern)
            except re.error as e:
                _write_debug_log(f"      [规则{i}] 正则表达式编译失败: {e}，跳过此规则")
                continue
            
            # 检查是否需要忽略标点符号（默认开启）
            ignore_punctuation = rule.get('ignore_punctuation', True)
            match_content = content
            
            if ignore_punctuation:
                # 移除所有标点符号（包括中英文标点）用于匹配
                # 定义所有需要移除的标点符号（英文标点 + 中文标点）
                punctuation_chars = string.punctuation + '，。！？；：""''（）【】《》、…—·'
                # 创建翻译表，将所有标点符号映射为空字符
                translator = str.maketrans('', '', punctuation_chars)
                match_content = content.translate(translator)
                _write_debug_log(f"      [规则{i}] 忽略标点模式: 原始内容: '{content}', 清理标点后: '{match_content}'")
            else:
                _write_debug_log(f"      [规则{i}] 包含标点模式: 匹配内容: '{match_content}'")
            
            # 检查是否匹配
            match = regex.search(match_content)
            if not match:
                _write_debug_log(f"      [规则{i}] 正则表达式未匹配，继续下一个规则")
                continue
            
            _write_debug_log(f"      [规则{i}] 正则表达式匹配成功: 匹配内容='{match.group()}'")
            
            # 检查冷却时间
            diff = now - self.advanced_last_t.get(i, 0)
            cooldown = rule.get('cooldown', 15)
            _write_debug_log(f"      [规则{i}] 冷却检查: diff={diff:.2f}s, cooldown={cooldown}s, "
                           f"last_t={self.advanced_last_t.get(i, 0)}, now={now}")
            if diff < cooldown:
                _write_debug_log(f"      [规则{i}] 冷却中，剩余{int(cooldown-diff)}s，返回空列表")
                if self.log_callback:
                    self.log_callback(
                        f"<span style='color:gray;'>[冷却中] 高级规则 '{pattern[:30]}...' 剩余 {int(cooldown-diff)}s</span>"
                    )
                return []
            
            # 生成回复消息
            _write_debug_log(f"      [规则{i}] 开始生成回复消息")
            self.advanced_last_t[i] = now
            start_time = time.time()
            # 检查是否需要@回复
            at_reply = rule.get('at_reply', False)
            prefix = f"@{user} " if at_reply else ""
            messages = self._generate_messages(rule, user, prefix=prefix)
            response_time = time.time() - start_time
            
            _write_debug_log(f"      [规则{i}] 生成消息完成: {len(messages)}条，耗时{response_time:.3f}s")
            if messages:
                for idx, msg in enumerate(messages):
                    _write_debug_log(f"        消息{idx}: {msg[:100]}")
            
            # 记录统计
            description = rule.get('description', pattern[:30])
            statistics_manager.record_reply(self.account_name, f"高级:{description}")
            statistics_manager.record_response_time(self.account_name, response_time)
            
            if self.log_callback:
                display_pattern = pattern[:50] + "..." if len(pattern) > 50 else pattern
                self.log_callback(
                    f"<span style='color:#9c27b0;'>【高级回复命中】</span> {display_pattern} (生成 {len(messages)} 条消息)"
                )
            
            _write_debug_log(f"      [规则{i}] 准备返回消息列表，消息数: {len(messages)}")
            return messages
        
        _write_debug_log(f"    [高级回复] 所有规则检查完毕，未匹配，返回空列表")
        return []

