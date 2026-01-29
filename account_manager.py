"""
账户管理模块 - 管理多个小号账户
"""
import os
import sys
import json

# 使用路径工具获取账户文件路径
try:
    from path_utils import get_config_path
    ACCOUNTS_FILE = get_config_path("accounts.json")
except ImportError:
    # 如果path_utils不可用（向后兼容），使用当前目录
    ACCOUNTS_FILE = "accounts.json"

def load_accounts():
    """加载账户列表"""
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []

def save_accounts(accounts):
    """保存账户列表"""
    try:
        # 确保目录存在
        file_dir = os.path.dirname(ACCOUNTS_FILE)
        if file_dir and not os.path.exists(file_dir):
            os.makedirs(file_dir, exist_ok=True)
        
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, ensure_ascii=False, indent=4)
    except Exception as e:
        # 如果保存失败，打印错误但不抛出异常（避免程序崩溃）
        try:
            print(f"警告: 保存账户文件失败: {e}", file=sys.stderr)
        except:
            pass

def add_account(account_name, nickname, url=""):
    """
    添加账户
    
    Args:
        account_name: 账户名称（用于标识）
        nickname: 小号昵称
        url: 直播间地址（可选）
    """
    accounts = load_accounts()
    
    # 检查是否已存在同名账户
    for acc in accounts:
        if acc.get('name') == account_name:
            return False
    
    new_account = {
        'name': account_name,
        'nickname': nickname,
        'url': url,
        'enabled': True,
        # 每个小号独立的回复规则配置
        'reply_rules': [],
        'specific_rules': [],
        'warmup_msgs': '欢迎来到直播间|喜欢主播点点关注',
        'auto_reply_enabled': False,
        'specific_reply_enabled': False,
        'warmup_enabled': False
    }
    accounts.append(new_account)
    save_accounts(accounts)
    return True

def remove_account(account_name):
    """删除账户"""
    accounts = load_accounts()
    accounts = [acc for acc in accounts if acc.get('name') != account_name]
    save_accounts(accounts)

def update_account(account_name, nickname=None, url=None, enabled=None, **kwargs):
    """
    更新账户信息
    
    Args:
        account_name: 账户名称
        nickname: 昵称
        url: 直播间地址
        enabled: 是否启用
        **kwargs: 其他字段（如reply_rules, specific_rules等配置字段）
    """
    accounts = load_accounts()
    for acc in accounts:
        if acc.get('name') == account_name:
            if nickname is not None:
                acc['nickname'] = nickname
            if url is not None:
                acc['url'] = url
            if enabled is not None:
                acc['enabled'] = enabled
            # 更新其他字段（用于配置更新）
            for key, value in kwargs.items():
                acc[key] = value
            save_accounts(accounts)
            return True
    return False

def get_account(account_name):
    """获取账户信息"""
    accounts = load_accounts()
    for acc in accounts:
        if acc.get('name') == account_name:
            return acc
    return None

def get_all_accounts():
    """获取所有账户"""
    return load_accounts()






