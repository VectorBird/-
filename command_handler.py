"""
指令处理器 - 处理指定用户的弹幕指令
"""
import re
from config_manager import load_cfg, save_cfg
from account_manager import get_all_accounts, save_accounts


class CommandHandler:
    """指令处理器 - 处理指定用户的弹幕指令"""
    
    def __init__(self, cfg_ref, log_callback=None):
        """
        初始化指令处理器
        
        Args:
            cfg_ref: 配置字典引用
            log_callback: 日志回调函数
        """
        self.cfg = cfg_ref
        self.log_callback = log_callback
        self.command_users = self._parse_command_users(cfg_ref.get('command_user', ''))
        self.command_enabled = cfg_ref.get('command_enabled', False)
        self.silent_mode = cfg_ref.get('command_silent_mode', False)
        # 用于二次确认的临时状态
        self.pending_confirmations = {}  # {user: (command, action_type, action_data)}
    
    def _parse_command_users(self, user_str):
        """解析指令用户列表（支持|分隔的多个用户）"""
        if not user_str:
            return set()
        users = [u.strip() for u in user_str.split('|') if u.strip()]
        return set(users)
    
    def set_enabled(self, enabled):
        """设置指令功能是否启用"""
        self.command_enabled = enabled
    
    def set_command_user(self, user_str):
        """设置指令用户（支持多个，用|分隔）"""
        self.command_users = self._parse_command_users(user_str)
        self.cfg['command_user'] = user_str.strip() if user_str else ''
    
    def set_silent_mode(self, silent):
        """设置静默模式"""
        self.silent_mode = silent
        self.cfg['command_silent_mode'] = silent
    
    def _exact_match(self, content, patterns):
        """
        严格匹配指令（必须完全匹配）
        
        Args:
            content: 用户输入的指令
            patterns: 指令模式列表
            
        Returns:
            bool: 是否匹配
        """
        content_lower = content.lower().strip()
        for pattern in patterns:
            pattern_lower = pattern.lower().strip()
            # 严格匹配：必须完全一致
            if content_lower == pattern_lower:
                return True
        return False
    
    def _normalize_command(self, content):
        """标准化指令（去除多余空格、统一格式）"""
        return content.strip()
    
    def process_command(self, user, content):
        """
        处理弹幕指令
        
        Args:
            user: 用户名
            content: 弹幕内容
            
        Returns:
            tuple: (is_command, result_message, actions, need_confirm)
                - is_command: 是否是指令
                - result_message: 执行结果消息（如果需要回复）
                - actions: 需要执行的操作列表
                - need_confirm: 是否需要二次确认
        """
        # 检查是否启用指令功能
        if not self.command_enabled:
            return False, None, [], False
        
        # 检查是否是指定用户（支持多用户）
        if not self.command_users or user not in self.command_users:
            return False, None, [], False
        
        content = self._normalize_command(content)
        
        # 检查是否有待确认的指令
        if user in self.pending_confirmations:
            pending_cmd, action_type, action_data = self.pending_confirmations[user]
            if self._exact_match(content, ["确认", "是", "yes", "y", "ok"]):
                # 确认执行
                del self.pending_confirmations[user]
                return True, "已确认执行", [(action_type, action_data)], False
            elif self._exact_match(content, ["取消", "否", "no", "n", "取消操作"]):
                # 取消执行
                del self.pending_confirmations[user]
                return True, "已取消操作", [], False
            else:
                # 继续等待确认
                return True, f"请确认执行: {pending_cmd}（回复'确认'或'取消'）", [], True
        
        # 解析指令（严格匹配）
        result = self._parse_command(content)
        if result:
            is_command, result_msg, actions, need_confirm = result
            if need_confirm:
                # 需要二次确认，保存到待确认列表
                self.pending_confirmations[user] = (content, actions[0][0] if actions else None, actions[0][1] if actions else {})
                return True, f"⚠️ 重要操作，请确认: {content}（回复'确认'执行，'取消'放弃）", [], True
            return is_command, result_msg, actions, False
        
        # 不是已知指令
        return False, None, [], False
    
    def _parse_command(self, content):
        """解析指令内容（严格匹配，支持多个同义指令）"""
        content_lower = content.lower().strip()
        
        # 停止弹幕机（支持多个同义指令，严格匹配）
        stop_commands = ["停止弹幕机", "停止弹幕姬", "停止自动回复", "关闭弹幕机", "关闭弹幕姬", "关闭自动回复", "暂停弹幕机", "暂停弹幕姬"]
        if content_lower in stop_commands:
            return True, "已停止自动回复和暖场功能", [('stop_auto_reply', {})], False
        
        # 启动弹幕机（支持多个同义指令，严格匹配）
        start_commands = ["启动弹幕机", "启动弹幕姬", "启动自动回复", "打开弹幕机", "打开弹幕姬", "打开自动回复", "开启弹幕机", "开启弹幕姬", "开启自动回复", "开始弹幕机", "开始弹幕姬"]
        if content_lower in start_commands:
            return True, "已启动自动回复和暖场功能", [('start_auto_reply', {})], False
        
        # 单独控制@回复（支持多个同义指令，严格匹配）
        enable_specific_commands = ["启用@回复", "启用@回复功能", "开启@回复", "开启@回复功能", "打开@回复", "打开@回复功能"]
        if content_lower in enable_specific_commands:
            return True, "已启用@回复功能", [('enable_specific_reply', {})], False
        disable_specific_commands = ["禁用@回复", "禁用@回复功能", "关闭@回复", "关闭@回复功能", "停止@回复", "停止@回复功能"]
        if content_lower in disable_specific_commands:
            return True, "已禁用@回复功能", [('disable_specific_reply', {})], False
        
        # 单独控制暖场（支持多个同义指令，严格匹配）
        enable_warmup_commands = ["启用暖场", "启用暖场功能", "开启暖场", "开启暖场功能", "打开暖场", "打开暖场功能"]
        if content_lower in enable_warmup_commands:
            return True, "已启用暖场功能", [('enable_warmup', {})], False
        disable_warmup_commands = ["禁用暖场", "禁用暖场功能", "关闭暖场", "关闭暖场功能", "停止暖场", "停止暖场功能"]
        if content_lower in disable_warmup_commands:
            return True, "已禁用暖场功能", [('disable_warmup', {})], False
        
        # 获取回复数量（严格匹配）
        elif content_lower == "统计" or content_lower == "查看统计" or content_lower == "获取统计":
            try:
                from statistics_manager import statistics_manager
                stats = statistics_manager.get_all_statistics(set())
                total_replies = stats['reply']['total_replies']
                danmu_count = stats['danmu']['total_count']
                unique_users = stats['danmu']['unique_users']
                runtime_hours = int(stats['runtime'] // 3600)
                runtime_mins = int((stats['runtime'] % 3600) // 60)
                msg = (f"📊 统计信息:\n"
                      f"• 总回复数: {total_replies}\n"
                      f"• 弹幕总数: {danmu_count}\n"
                      f"• 活跃用户: {unique_users}\n"
                      f"• 运行时间: {runtime_hours}小时{runtime_mins}分钟")
                return True, msg, [], False
            except Exception as e:
                return True, f"获取统计失败: {str(e)}", [], False
        
        # 参数化指令：设置回复间隔
        elif content.startswith("设置间隔:") or content.startswith("间隔:"):
            try:
                interval_str = content.split(":", 1)[1].strip()
                interval = float(interval_str)
                if interval < 1 or interval > 30:
                    return True, "间隔时间必须在1-30秒之间", [], False
                return True, f"已设置回复间隔为 {interval} 秒", [('set_reply_interval', {'interval': interval})], False
            except (ValueError, IndexError):
                return True, "格式错误，正确格式: 设置间隔:5（1-30秒）", [], False
        
        # 添加规则
        elif content.startswith("添加规则:") or content.startswith("添加:"):
            try:
                rule_text = content.split(":", 1)[1].strip()
                parts = [p.strip() for p in rule_text.split("|")]
                
                if len(parts) < 2:
                    return True, "格式错误，正确格式: 添加规则:关键词|回复内容", [], False
                
                keyword = parts[0]
                reply = parts[1]
                mode = parts[2] if len(parts) > 2 else "随机挑一"
                cooldown = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 15
                
                if 'reply_rules' not in self.cfg:
                    self.cfg['reply_rules'] = []
                
                new_rule = {
                    "kw": keyword,
                    "resp": reply,
                    "mode": mode,
                    "cooldown": cooldown,
                    "active": True
                }
                
                self.cfg['reply_rules'].append(new_rule)
                save_cfg(self.cfg)
                
                return True, "规则添加成功", [('reload_rules', {})], False
            except Exception as e:
                return True, f"添加规则失败: {str(e)}", [], False
        
        # 删除规则
        elif content.startswith("删除规则:") or content.startswith("删除:"):
            try:
                keyword = content.split(":", 1)[1].strip()
                
                if 'reply_rules' not in self.cfg:
                    return True, "没有可删除的规则", [], False
                
                original_count = len(self.cfg['reply_rules'])
                self.cfg['reply_rules'] = [
                    rule for rule in self.cfg['reply_rules']
                    if rule.get('kw', '').strip() != keyword
                ]
                
                deleted_count = original_count - len(self.cfg['reply_rules'])
                if deleted_count > 0:
                    save_cfg(self.cfg)
                    return True, f"已删除 {deleted_count} 条规则（关键词: {keyword}）", [('reload_rules', {})], False
                else:
                    return True, f"未找到关键词为 '{keyword}' 的规则", [], False
            except Exception as e:
                return True, f"删除规则失败: {str(e)}", [], False
        
        # 重置统计（需要二次确认，严格匹配）
        elif content_lower == "重置统计" or content_lower == "清空统计":
            return True, None, [('reset_statistics', {})], True  # 需要确认
        
        # 清空队列（严格匹配）
        elif content_lower == "清空队列" or content_lower == "清空消息队列":
            return True, "已清空消息队列", [('clear_queue', {})], False
        
        return None
    
    def clear_pending_confirmation(self, user):
        """清除用户的待确认指令（超时或窗口关闭时）"""
        if user in self.pending_confirmations:
            del self.pending_confirmations[user]
