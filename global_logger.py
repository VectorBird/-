"""
全局日志管理器 - 统一管理所有小号的日志
"""
import sys
from PyQt6.QtCore import QObject, pyqtSignal
from datetime import datetime


class GlobalLogger(QObject):
    """全局日志管理器 - 单例模式"""
    
    # 信号必须在类级别定义
    log_received = pyqtSignal(str, str)  # 账户名, 日志消息
    
    _instance = None
    _qobject_initialized = False  # 跟踪QObject是否已初始化
    _custom_initialized = False  # 跟踪自定义初始化是否已完成
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalLogger, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        try:
            print("        [init] 开始初始化...", end=" ")
            sys.stdout.flush()
            
            # 必须先调用父类初始化（只在第一次调用）
            # 这是 PyQt6 的硬性要求，必须在访问任何属性之前调用
            if not GlobalLogger._qobject_initialized:
                print("调用super().__init__()...", end=" ")
                sys.stdout.flush()
                super().__init__()
                GlobalLogger._qobject_initialized = True
                print("✓", end=" ")
                sys.stdout.flush()
            
            # 如果已经完成自定义初始化，直接返回
            if GlobalLogger._custom_initialized:
                print("已初始化，返回")
                sys.stdout.flush()
                return
            
            print("进行自定义初始化...", end=" ")
            sys.stdout.flush()
            
            # 进行自定义初始化
            # 确保QApplication已创建
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                GlobalLogger._custom_initialized = True
                print("QApplication不存在")
                sys.stdout.flush()
                return
                
            # 标记为已初始化
            GlobalLogger._custom_initialized = True
            print("✓ 完成")
            sys.stdout.flush()
        except Exception as e:
            # 即使出错也标记为已初始化，避免重复尝试
            GlobalLogger._custom_initialized = True
            print(f"✗ 错误: {e}")
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
        
    def log(self, account_name, message):
        """
        记录日志
        
        Args:
            account_name: 账户名称（如果是全局日志则为"系统"）
            message: 日志消息
        """
        # 只有在QApplication存在时才发送信号
        try:
            from PyQt6.QtWidgets import QApplication
            if QApplication.instance() is not None and GlobalLogger._qobject_initialized:
                self.log_received.emit(account_name, message)
            else:
                print(f"[{account_name}] {message}")
        except:
            # 如果发送信号失败，只打印到控制台
            print(f"[{account_name}] {message}")


def _get_logger():
    """获取全局日志实例（延迟初始化，确保QApplication存在）"""
    # 如果已经创建过实例，直接返回
    if GlobalLogger._instance is not None and GlobalLogger._custom_initialized:
        return GlobalLogger._instance
    
    # 确保QApplication已创建
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication must be created before initializing GlobalLogger")
    
    # 创建GlobalLogger实例（使用单例模式）
    try:
        print("      [logger] 开始创建GlobalLogger实例...", end=" ")
        sys.stdout.flush()
        logger = GlobalLogger()
        print("✓")
        sys.stdout.flush()
        return logger
    except Exception as e:
        print(f"✗ 错误: {e}")
        sys.stdout.flush()
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        raise


# 创建一个代理对象，延迟初始化
class LoggerProxy:
    """日志代理，延迟初始化实际的logger"""
    def __getattr__(self, name):
        return getattr(_get_logger(), name)


# 全局单例实例（延迟创建）
global_logger = LoggerProxy()
