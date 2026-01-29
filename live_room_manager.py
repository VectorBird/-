"""
直播间历史记录管理模块
"""
import os
import json
import sys

# 使用路径工具获取配置文件路径
try:
    from path_utils import get_config_path
    LIVE_ROOMS_FILE = get_config_path("live_rooms.json")
except ImportError:
    # 如果path_utils不可用（向后兼容），使用当前目录
    LIVE_ROOMS_FILE = "live_rooms.json"

def load_live_rooms():
    """加载直播间历史记录"""
    if os.path.exists(LIVE_ROOMS_FILE):
        try:
            with open(LIVE_ROOMS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []

def save_live_rooms(rooms):
    """保存直播间历史记录"""
    try:
        # 确保目录存在
        file_dir = os.path.dirname(LIVE_ROOMS_FILE)
        if file_dir and not os.path.exists(file_dir):
            os.makedirs(file_dir, exist_ok=True)
        
        with open(LIVE_ROOMS_FILE, "w", encoding="utf-8") as f:
            json.dump(rooms, f, ensure_ascii=False, indent=4)
    except Exception as e:
        # 如果保存失败，打印错误但不抛出异常（避免程序崩溃）
        try:
            print(f"警告: 保存直播间记录失败: {e}", file=sys.stderr)
        except:
            pass

def add_live_room(name, url):
    """
    添加直播间到历史记录
    
    Args:
        name: 直播间名称
        url: 直播间地址
    """
    rooms = load_live_rooms()
    
    # 检查是否已存在相同URL的直播间
    for room in rooms:
        if room.get('url') == url:
            # 如果URL已存在，更新名称
            room['name'] = name
            save_live_rooms(rooms)
            return True
    
    # 添加新直播间
    new_room = {
        'name': name,
        'url': url
    }
    rooms.append(new_room)
    save_live_rooms(rooms)
    return True

def remove_live_room(url):
    """删除直播间记录"""
    rooms = load_live_rooms()
    rooms = [room for room in rooms if room.get('url') != url]
    save_live_rooms(rooms)

def get_all_live_rooms():
    """获取所有直播间记录"""
    return load_live_rooms()

