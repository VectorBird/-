"""
配置管理模块
"""
import os
import sys
import json

# 使用路径工具获取配置文件路径
def _get_config_file_path():
    """获取配置文件路径（延迟计算，确保在运行时获取正确的路径）"""
    try:
        from path_utils import get_config_path
        return get_config_path("danmu_cfg.json")
    except ImportError:
        # 如果path_utils不可用，使用EXE目录或当前目录
        if getattr(sys, 'frozen', False):
            # 打包环境：使用EXE所在目录
            return os.path.join(os.path.dirname(sys.executable), "danmu_cfg.json")
        else:
            # 开发环境：使用当前目录
            return "danmu_cfg.json"

# 延迟计算CONFIG_FILE（在函数中动态获取，而不是在模块导入时）
# 这样可以在运行时获取正确的路径，而不是在模块导入时
CONFIG_FILE = None  # 将在第一次使用时初始化

def load_cfg():
    """加载配置文件"""
    global CONFIG_FILE
    if CONFIG_FILE is None:
        CONFIG_FILE = _get_config_file_path()
    
    default = {
        "use_gpu": False,
        "hide_web": False,
        "my_nickname": "机器人名字",
        "auto_reply_enabled": False,
        "warmup_enabled": False,
        "specific_reply_enabled": False,
        "advanced_reply_enabled": False,  # 高级回复模式开关（正则表达式匹配）
        "command_enabled": False,  # 指令功能开关
        "command_user": "",  # 指令用户昵称（支持多个，用逗号分隔）
        "command_silent_mode": False,  # 指令静默模式（不回复）
        "warmup_frequency": 60,
        "warmup_no_danmu_time": 120,  # 无弹幕时间（秒），超过这个时间才触发暖场
        "reply_interval": 4,
        "random_jitter": 2.0,
        "reply_rules": [
            {
                "kw": "测试",
                "resp": "测试通过~|测试成功！|功能正常",
                "mode": "随机挑一",
                "cooldown": 10,
                "active": True
            },
            {
                "kw": "你好|在吗|主播好",
                "resp": "你好，欢迎来到直播间~|在的，有什么可以帮您|主播好，欢迎新朋友",
                "mode": "随机挑一",
                "cooldown": 15,
                "active": True
            },
            {
                "kw": "怎么买|哪里买|怎么下单",
                "resp": "点击左上角粉丝群查看详情|喜欢的可以截图咨询哦|可以私信咨询购买方式",
                "mode": "随机挑一",
                "cooldown": 15,
                "active": False
            },
            {
                "kw": "怎么进群|哪里加群|群怎么进",
                "resp": "点击头像进入粉丝群|左上角粉丝群欢迎加入|头像处可以加入粉丝群",
                "mode": "随机挑一",
                "cooldown": 15,
                "active": False
            }
        ],
        "advanced_reply_rules": [
            {
                "pattern": ".*测试.*",
                "resp": "高级回复模式测试通过~|正则表达式匹配成功！|测试功能正常",
                "mode": "随机挑一",
                "cooldown": 10,
                "active": True,
                "description": "匹配包含'测试'的弹幕（示例：测试、测试一下、功能测试等）",
                "ignore_punctuation": True,
                "at_reply": False
            },
            {
                "pattern": "(你好|在吗|主播好).*",
                "resp": "你好，欢迎来到直播间~|在的，有什么可以帮您|主播好，欢迎新朋友",
                "mode": "随机挑一",
                "cooldown": 15,
                "active": False,
                "description": "匹配问候语（示例：你好、在吗、主播好等）",
                "ignore_punctuation": True,
                "at_reply": False
            },
            {
                "pattern": "(怎么|如何|怎样|哪里|在哪).*(买|下单|拍|购买)",
                "resp": "点击左上角粉丝群查看详情|喜欢的可以截图咨询哦|可以私信咨询购买方式",
                "mode": "随机挑一",
                "cooldown": 15,
                "active": False,
                "description": "匹配各种购买询问的表达方式（示例：怎么买、在哪里下单等）",
                "ignore_punctuation": True,
                "at_reply": False
            },
            {
                "pattern": "(进|加|加入).*群",
                "resp": "点击头像进入粉丝群|左上角粉丝群欢迎加入|头像处可以加入粉丝群",
                "mode": "随机挑一",
                "cooldown": 15,
                "active": False,
                "description": "匹配各种进群询问的表达方式（示例：怎么进群、加入群等）",
                "ignore_punctuation": True,
                "at_reply": False
            },
            {
                "pattern": ".*关注.*",
                "resp": "@感谢关注，欢迎常来~|@谢谢关注，记得常来看看哦|@关注成功，欢迎加入我们",
                "mode": "随机挑一",
                "cooldown": 20,
                "active": False,
                "description": "匹配包含'关注'的弹幕，并@回复用户（示例：关注了、点关注等）",
                "ignore_punctuation": True,
                "at_reply": True
            }
        ],
        "specific_rules": [
            {
                "kw": "测试@",
                "resp": "@回复测试通过~|@回复功能正常|@回复测试成功！",
                "mode": "随机挑一",
                "cooldown": 10,
                "active": True
            },
            {
                "kw": "你好|在吗|主播好",
                "resp": "@你好，欢迎来到直播间~|@在的，有什么可以帮您|@主播好，欢迎新朋友",
                "mode": "随机挑一",
                "cooldown": 15,
                "active": False
            },
            {
                "kw": "关注|点关注",
                "resp": "@感谢关注，欢迎常来~|@谢谢关注，记得常来看看哦|@关注成功，欢迎加入我们",
                "mode": "随机挑一",
                "cooldown": 20,
                "active": False
            }
        ],
        "warmup_msgs": "欢迎来到直播间|喜欢主播点点关注",  # 保留兼容性
        "warmup_rules": [
            {
                "trigger_type": "无弹幕触发",
                "name": "默认暖场",
                "messages": "欢迎来到直播间|喜欢主播点点关注|新来的朋友可以点个关注哦",
                "mode": "随机挑一",
                "min_no_danmu_time": 60,
                "max_no_danmu_time": 0,
                "cooldown": 120,
                "active": True
            }
        ],
        "agreement_accepted": False,  # 用户协议是否已同意
        # 消息队列配置
        "queue_mode": "轮询",  # 轮询、优先级、随机、第一个可用
        "queue_time_window": 5.0,  # 消息指纹时间窗口（秒）
        "queue_lock_timeout": 30.0,  # 锁超时时间（秒）
        "account_priorities": {},  # 账户优先级配置 {账户名: 优先级数字}
        "strict_single_reply": True,  # 严格单回复模式：同一条弹幕只能被一个小号回复一次
        "allow_multiple_reply": False,  # 允许多小号同时回复：True=允许所有小号回复，False=只允许一个小号回复
        "auto_cleanup_locks": True,  # 自动清理过期锁
        "deadlock_detection": True,  # 死锁检测（预留，当前通过超时机制实现）
        "max_lock_history": 1000,  # 最大锁历史记录数（防止内存泄漏）
        "random_space_insert_enabled": False  # 随机空格插入（防风控）：在发送消息时随机插入空格防止抖音官方风控
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {**default, **data}
        except Exception as e:
            # 如果加载失败，打印警告但返回默认配置（避免程序崩溃）
            try:
                print(f"警告: 加载配置文件失败: {e}", file=sys.stderr)
            except:
                pass
    return default

def save_cfg(data):
    """保存配置文件"""
    global CONFIG_FILE
    if CONFIG_FILE is None:
        CONFIG_FILE = _get_config_file_path()
    
    try:
        # 确保目录存在
        config_dir = os.path.dirname(CONFIG_FILE)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
        
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        # 如果保存失败，打印错误但不抛出异常（避免程序崩溃）
        try:
            print(f"警告: 保存配置文件失败: {e}", file=sys.stderr)
        except:
            pass

