"""
弹幕监控模块 - 独立处理弹幕捕获和解析
"""
import json
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from statistics_manager import statistics_manager

class GlobalSignal(QObject):
    """全局信号管理器"""
    received = pyqtSignal(dict)  # 弹幕接收信号
    log_msg = pyqtSignal(str)    # 日志消息信号

global_signal = GlobalSignal()


class DanmuBridge(QObject):
    """弹幕桥接器 - 连接JavaScript和Python"""
    
    @pyqtSlot(str)
    def post_danmu(self, d):
        """接收JavaScript传递的数据（弹幕、礼物、在线人数等）"""
        try:
            data = json.loads(d)
            # 确保数据有type字段，默认为'danmu'
            if 'type' not in data:
                data['type'] = 'danmu'
            
            # 调试日志：记录接收到的数据
            print(f"[post_danmu] 接收到数据: type={data.get('type', 'unknown')}, data={data}")
            import sys
            sys.stdout.flush()
            
            global_signal.received.emit(data)
        except Exception as e:
            # 调试日志：记录错误
            print(f"[post_danmu] 处理数据失败: {e}, 原始数据: {d}")
            import sys
            sys.stdout.flush()
            pass


class DanmuMonitor:
    """弹幕监控器 - 负责监控和过滤弹幕"""
    
    def __init__(self, my_nickname=""):
        """
        初始化弹幕监控器
        
        Args:
            my_nickname: 自己的昵称，用于过滤自己的弹幕
        """
        self.my_nickname = my_nickname
        self.other_account_nicknames = set()  # 其他小号的昵称列表，用于过滤其他小号的弹幕
        self.on_danmu_callback = None  # 弹幕回调函数
        
    def set_nickname(self, nickname):
        """设置自己的昵称"""
        self.my_nickname = nickname
        
    def set_other_account_nicknames(self, nicknames):
        """
        设置其他小号的昵称列表（用于过滤其他小号的弹幕，防止循环回复）
        
        Args:
            nicknames: 其他小号昵称列表（list或set）
        """
        if nicknames:
            self.other_account_nicknames = set(nicknames) if not isinstance(nicknames, set) else nicknames
        else:
            self.other_account_nicknames = set()
        
    def set_callback(self, callback):
        """设置弹幕回调函数"""
        self.on_danmu_callback = callback
        
    def process_danmu(self, data):
        """
        处理接收到的数据（弹幕、礼物、在线人数等）
        
        Args:
            data: 数据字典，包含type字段和相应数据
                - type: 'danmu' | 'gift' | 'viewer_count' | 'other'
                - 弹幕数据: user, content
                - 礼物数据: user, gift_name, gift_count
                - 在线人数: viewer_count
        """
        data_type = data.get('type', 'danmu')
        
        # 如果是弹幕，进行过滤处理
        if data_type == 'danmu':
            user = data.get('user', '').strip()
            content = data.get('content', '').strip()
            
            # 过滤无效弹幕（先检查，避免后续处理无效数据）
            if not user or not content:
                return
            
            # 过滤自己的弹幕（精确匹配，但也要考虑可能的空格或特殊字符）
            if self.my_nickname and user == self.my_nickname.strip():
                return
            
            # 过滤其他小号的弹幕（防止循环回复）- 使用精确匹配和部分匹配
            if self.other_account_nicknames:
                # 精确匹配
                if user in self.other_account_nicknames:
                    return
                # 部分匹配（防止昵称有细微差异，如"小号1"和"小号1 "）
                for other_nickname in self.other_account_nicknames:
                    if other_nickname and (user == other_nickname.strip() or 
                                         user.startswith(other_nickname.strip()) or
                                         other_nickname.strip() in user):
                        return
            
            # 记录弹幕统计（只有通过过滤的弹幕才记录）
            statistics_manager.record_danmu(user, content)
        
        # 触发回调（所有类型的数据都传递，但弹幕类型的数据如果被过滤则不会到达这里）
        if self.on_danmu_callback:
            self.on_danmu_callback(data)



