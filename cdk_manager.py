"""
CDK管理模块 - 支持离线CDK生成和验证
使用HMAC-SHA256进行签名验证，确保双端可离线验证
"""
import hmac
import hashlib
import json
import time
from datetime import datetime, timedelta
from device_info import get_device_info

# CDK密钥（服务端和客户端共享，用于生成和验证签名）
# 注意：实际部署时应使用环境变量或配置文件，不要硬编码
CDK_SECRET_KEY = b"d0uy1n_l1v3_c0ntr0l_cdk_s3cr3t_k3y_2026"  # 32字节密钥

# 功能标识
FEATURE_SPECIFIC_REPLY = "specific_reply"
FEATURE_ADVANCED_REPLY = "advanced_reply"
FEATURE_WARMUP = "warmup"
FEATURE_COMMAND = "command"
ALL_FEATURES = [FEATURE_SPECIFIC_REPLY, FEATURE_ADVANCED_REPLY, FEATURE_WARMUP, FEATURE_COMMAND]

def generate_cdk(features=None, days=0, hours=0, minutes=0, machine_code=None):
    """
    生成CDK（服务端使用）
    
    Args:
        features: 功能列表，None表示所有功能
        days: 有效期天数
        hours: 有效期小时数
        minutes: 有效期分钟数
        machine_code: 绑定的机器码（None表示不绑定）
    
    Returns:
        str: CDK字符串
    """
    if features is None:
        features = ALL_FEATURES
    
    # 计算到期时间戳
    now = time.time()
    duration_seconds = days * 86400 + hours * 3600 + minutes * 60
    expire_time = int(now + duration_seconds) if duration_seconds > 0 else 0  # 0表示永久
    
    # 构建CDK数据
    cdk_data = {
        "features": sorted(features),  # 排序确保一致性
        "expire_time": expire_time,
        "machine_code": machine_code,
        "create_time": int(now)
    }
    
    # 将数据转换为JSON字符串
    data_str = json.dumps(cdk_data, sort_keys=True, separators=(',', ':'))
    
    # 生成HMAC签名
    signature = hmac.new(
        CDK_SECRET_KEY,
        data_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # 组合CDK：base64编码的数据 + 分隔符 + 签名
    import base64
    encoded_data = base64.b64encode(data_str.encode('utf-8')).decode('utf-8')
    
    # CDK格式：DATA-SIGNATURE（使用短横线分隔，便于识别）
    cdk = f"{encoded_data}-{signature}"
    
    return cdk

def verify_cdk(cdk, machine_code=None):
    """
    验证CDK（客户端使用，支持离线验证）
    
    Args:
        cdk: CDK字符串
        machine_code: 当前设备的机器码（如果CDK绑定了机器码）
    
    Returns:
        tuple: (is_valid, message, cdk_data)
            is_valid: 是否有效
            message: 验证结果消息
            cdk_data: CDK数据字典（如果有效），包含features, expire_time等
    """
    try:
        # 解析CDK格式
        if '-' not in cdk:
            return False, "CDK格式错误：缺少分隔符", None
        
        parts = cdk.split('-', 1)
        if len(parts) != 2:
            return False, "CDK格式错误：格式不正确", None
        
        encoded_data, signature = parts
        
        # 解码数据
        import base64
        try:
            data_str = base64.b64decode(encoded_data.encode('utf-8')).decode('utf-8')
        except Exception as e:
            return False, f"CDK格式错误：无法解码数据 ({str(e)})", None
        
        # 验证签名
        expected_signature = hmac.new(
            CDK_SECRET_KEY,
            data_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            return False, "CDK签名验证失败：CDK无效或已被篡改", None
        
        # 解析CDK数据
        try:
            cdk_data = json.loads(data_str)
        except json.JSONDecodeError as e:
            return False, f"CDK数据解析失败：{str(e)}", None
        
        # 检查机器码绑定
        if cdk_data.get('machine_code'):
            if machine_code is None:
                machine_code = get_device_info().get("machine_code")
            if cdk_data.get('machine_code') != machine_code:
                return False, "CDK机器码不匹配：此CDK已绑定到其他设备", None
        
        # 检查是否过期
        expire_time = cdk_data.get('expire_time', 0)
        if expire_time > 0:
            now = time.time()
            if now > expire_time:
                expire_datetime = datetime.fromtimestamp(expire_time)
                return False, f"CDK已过期：有效期至 {expire_datetime.strftime('%Y-%m-%d %H:%M:%S')}", None
        
        # CDK有效
        return True, "CDK验证成功", cdk_data
        
    except Exception as e:
        return False, f"CDK验证失败：{str(e)}", None

def get_cdk_info(cdk):
    """
    获取CDK信息（不验证签名，仅用于显示）
    
    Args:
        cdk: CDK字符串
    
    Returns:
        dict: CDK信息，包含features, expire_time等
    """
    try:
        if '-' not in cdk:
            return None
        
        parts = cdk.split('-', 1)
        if len(parts) != 2:
            return None
        
        encoded_data = parts[0]
        
        import base64
        try:
            data_str = base64.b64decode(encoded_data.encode('utf-8')).decode('utf-8')
            cdk_data = json.loads(data_str)
            return cdk_data
        except:
            return None
    except:
        return None

def format_cdk_expire_time(expire_time):
    """
    格式化CDK到期时间
    
    Args:
        expire_time: 时间戳（0表示永久）
    
    Returns:
        str: 格式化的时间字符串
    """
    if expire_time == 0:
        return "永久有效"
    
    expire_datetime = datetime.fromtimestamp(expire_time)
    now = datetime.now()
    
    if expire_datetime < now:
        return f"已过期 ({expire_datetime.strftime('%Y-%m-%d %H:%M:%S')})"
    
    delta = expire_datetime - now
    if delta.days > 0:
        return f"{delta.days}天后到期 ({expire_datetime.strftime('%Y-%m-%d %H:%M:%S')})"
    elif delta.seconds >= 3600:
        hours = delta.seconds // 3600
        return f"{hours}小时后到期 ({expire_datetime.strftime('%Y-%m-%d %H:%M:%S')})"
    elif delta.seconds >= 60:
        minutes = delta.seconds // 60
        return f"{minutes}分钟后到期 ({expire_datetime.strftime('%Y-%m-%d %H:%M:%S')})"
    else:
        return f"即将到期 ({expire_datetime.strftime('%Y-%m-%d %H:%M:%S')})"
