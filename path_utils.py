"""
路径工具模块 - 提供统一的路径处理函数，支持开发环境和PyInstaller打包环境
"""
import os
import sys

def get_base_dir():
    """
    获取程序基础目录
    - 打包环境：返回EXE文件所在目录（可写）
    - 开发环境：返回脚本所在目录
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller打包环境：EXE文件所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发环境：脚本所在目录
        return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path):
    """
    获取资源文件路径（图标、图片等只读资源）
    - 打包环境：先从临时目录查找，再从EXE目录查找
    - 开发环境：从脚本目录查找
    
    Args:
        relative_path: 相对路径，如 "favicon.ico"
    
    Returns:
        资源文件的完整路径，如果不存在则返回None
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller打包环境
        # 首先尝试从临时目录（sys._MEIPASS）查找
        base_dir = sys._MEIPASS
        resource_path = os.path.join(base_dir, relative_path)
        if os.path.exists(resource_path):
            return resource_path
        
        # 如果临时目录没有，尝试从EXE目录查找
        exe_dir = os.path.dirname(sys.executable)
        resource_path = os.path.join(exe_dir, relative_path)
        if os.path.exists(resource_path):
            return resource_path
    else:
        # 开发环境：从脚本目录查找
        base_dir = os.path.dirname(os.path.abspath(__file__))
        resource_path = os.path.join(base_dir, relative_path)
        if os.path.exists(resource_path):
            return resource_path
        
        # 也尝试当前工作目录
        resource_path = os.path.join(os.getcwd(), relative_path)
        if os.path.exists(resource_path):
            return resource_path
    
    return None

def get_data_dir():
    """
    获取数据目录（用于存储配置文件、日志等可写文件）
    始终返回EXE/脚本所在目录，确保可写
    """
    return get_base_dir()

def get_config_path(filename):
    """
    获取配置文件路径
    
    Args:
        filename: 配置文件名，如 "danmu_cfg.json"
    
    Returns:
        配置文件完整路径
    """
    return os.path.join(get_data_dir(), filename)

def get_log_dir():
    """
    获取日志目录路径
    
    Returns:
        日志目录完整路径
    """
    log_dir = os.path.join(get_data_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def get_session_dir(account_name=None):
    """
    获取会话存储目录路径
    
    Args:
        account_name: 账户名称（多账户模式时使用），如果为None则使用默认目录
    
    Returns:
        会话目录完整路径
    """
    if account_name:
        session_dir = os.path.join(get_data_dir(), "douyin_sessions", account_name)
    else:
        session_dir = os.path.join(get_data_dir(), "douyin_session")
    
    os.makedirs(session_dir, exist_ok=True)
    return session_dir


