"""
设备信息收集模块 - 收集IP、MAC、机器码等信息
"""
import socket
import uuid
import platform
import hashlib
import json

def get_local_ip():
    """获取本地IP地址"""
    try:
        # 连接一个远程地址来获取本机IP（不实际发送数据）
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            # 备用方法：获取主机名对应的IP
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            return ip
        except Exception:
            return "未知"

def get_mac_address():
    """获取MAC地址"""
    try:
        # 获取本机MAC地址
        mac = uuid.getnode()
        # 转换为十六进制字符串
        mac_str = ':'.join(['{:02x}'.format((mac >> ele) & 0xff) 
                           for ele in range(0, 8*6, 8)][::-1])
        return mac_str
    except Exception:
        return "未知"

def get_machine_code():
    """生成简单的机器码（基于MAC地址和主机名）"""
    try:
        # 使用MAC地址和主机名生成机器码
        mac = get_mac_address()
        hostname = platform.node()
        machine_info = f"{mac}-{hostname}"
        # 使用MD5生成简短标识
        machine_code = hashlib.md5(machine_info.encode('utf-8')).hexdigest()[:16]
        return machine_code
    except Exception:
        return "未知"

def get_device_info():
    """获取完整的设备信息"""
    return {
        "ip": get_local_ip(),
        "mac": get_mac_address(),
        "machine_code": get_machine_code(),
        "hostname": platform.node(),
        "platform": platform.system(),
        "platform_version": platform.version(),
        "architecture": platform.machine()
    }

if __name__ == "__main__":
    # 测试
    info = get_device_info()
    print(json.dumps(info, ensure_ascii=False, indent=2))










