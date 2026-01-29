"""
服务器客户端模块 - 处理与服务器的通信（使用标准库urllib）
"""
import urllib.request
import urllib.error
import json
import sys
import time
from device_info import get_device_info
from config_manager import load_cfg
from account_manager import get_all_accounts

# 服务器配置
SERVER_HOST = "14.103.165.9"
SERVER_PORT = 8080
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# API端点
API_HEALTH = f"{SERVER_URL}/api/health"
API_REGISTER = f"{SERVER_URL}/api/register"
API_SUBMIT_KEYWORDS = f"{SERVER_URL}/api/submit_keywords"
API_CHECK_BAN = f"{SERVER_URL}/api/check_ban"

def check_server_connection(timeout=5):
    """检查服务器连接是否可用"""
    try:
        req = urllib.request.Request(API_HEALTH)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                return True, "连接成功"
            else:
                return False, f"服务器响应错误: {response.status}"
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError) or "timed out" in str(e).lower():
            return False, "连接超时，请检查网络"
        else:
            return False, f"无法连接到服务器: {str(e)}"
    except Exception as e:
        import traceback
        error_msg = f"[异常] 验证服务器连接失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        import sys
        sys.stdout.flush()
        return False, f"连接失败: {str(e)}"

def register_device():
    """注册设备到服务器"""
    try:
        device_info = get_device_info()
        data = json.dumps(device_info).encode('utf-8')
        
        req = urllib.request.Request(
            API_REGISTER,
            data=data,
            headers={"Content-Type": "application/json"},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                result = json.loads(response.read().decode('utf-8'))
                return True, result.get("message", "注册成功")
            else:
                return False, f"注册失败: {response.status}"
    except urllib.error.URLError as e:
        return False, f"注册失败: {str(e)}"
    except Exception as e:
        return False, f"注册失败: {str(e)}"

def collect_keywords():
    """收集所有关键词和暖场消息（包括全局和账户级别的）"""
    keywords_data = {
        "global_reply_rules": [],
        "global_specific_rules": [],
        "global_warmup_rules": [],
        "account_rules": []
    }
    
    try:
        # 加载全局配置
        cfg = load_cfg()
        
        # 收集全局关键词规则
        for rule in cfg.get("reply_rules", []):
            if rule.get("active", False):
                keywords_data["global_reply_rules"].append({
                    "keyword": rule.get("kw", ""),
                    "reply": rule.get("resp", ""),  # 回复内容
                    "mode": rule.get("mode", ""),
                    "cooldown": rule.get("cooldown", 0)
                })
        
        # 收集全局特定回复规则
        for rule in cfg.get("specific_rules", []):
            if rule.get("active", False):
                keywords_data["global_specific_rules"].append({
                    "keyword": rule.get("kw", ""),
                    "reply": rule.get("resp", ""),  # 回复内容
                    "mode": rule.get("mode", ""),
                    "cooldown": rule.get("cooldown", 0)
                })
        
        # 收集全局暖场规则
        warmup_rules = cfg.get("warmup_rules", [])
        if warmup_rules:
            # 新格式：warmup_rules（多规则）
            for rule in warmup_rules:
                if rule.get("active", False):
                    keywords_data["global_warmup_rules"].append({
                        "trigger_type": rule.get("trigger_type", "无弹幕触发"),
                        "name": rule.get("name", ""),
                        "messages": rule.get("messages", ""),  # 消息池
                        "mode": rule.get("mode", "随机挑一"),
                        "min_no_danmu_time": rule.get("min_no_danmu_time", 120),
                        "max_no_danmu_time": rule.get("max_no_danmu_time", 0),
                        "cooldown": rule.get("cooldown", 60)
                    })
        elif cfg.get("warmup_msgs"):
            # 旧格式：warmup_msgs（兼容性）
            warmup_msgs = cfg.get("warmup_msgs", "")
            if warmup_msgs:
                keywords_data["global_warmup_rules"].append({
                    "trigger_type": "无弹幕触发",
                    "name": "默认暖场",
                    "messages": warmup_msgs,
                    "mode": "随机挑一",
                    "min_no_danmu_time": 120,
                    "max_no_danmu_time": 0,
                    "cooldown": 60
                })
        
        # 收集账户级别的关键词和暖场规则
        accounts = get_all_accounts()
        for account in accounts:
            account_name = account.get("name", "")
            account_keywords = {
                "account_name": account_name,
                "reply_rules": [],
                "specific_rules": [],
                "warmup_rules": []
            }
            
            # 账户级别的回复规则
            for rule in account.get("reply_rules", []):
                if rule.get("active", False):
                    account_keywords["reply_rules"].append({
                        "keyword": rule.get("kw", ""),
                        "reply": rule.get("resp", ""),  # 回复内容
                        "mode": rule.get("mode", ""),
                        "cooldown": rule.get("cooldown", 0)
                    })
            
            # 账户级别的特定回复规则
            for rule in account.get("specific_rules", []):
                if rule.get("active", False):
                    account_keywords["specific_rules"].append({
                        "keyword": rule.get("kw", ""),
                        "reply": rule.get("resp", ""),  # 回复内容
                        "mode": rule.get("mode", ""),
                        "cooldown": rule.get("cooldown", 0)
                    })
            
            # 账户级别的暖场规则
            account_warmup_rules = account.get("warmup_rules", [])
            if account_warmup_rules:
                for rule in account_warmup_rules:
                    if rule.get("active", False):
                        account_keywords["warmup_rules"].append({
                            "trigger_type": rule.get("trigger_type", "无弹幕触发"),
                            "name": rule.get("name", ""),
                            "messages": rule.get("messages", ""),
                            "mode": rule.get("mode", "随机挑一"),
                            "min_no_danmu_time": rule.get("min_no_danmu_time", 120),
                            "max_no_danmu_time": rule.get("max_no_danmu_time", 0),
                            "cooldown": rule.get("cooldown", 60)
                        })
            elif account.get("warmup_msgs"):
                # 兼容旧格式
                warmup_msgs = account.get("warmup_msgs", "")
                if warmup_msgs:
                    account_keywords["warmup_rules"].append({
                        "trigger_type": "无弹幕触发",
                        "name": "默认暖场",
                        "messages": warmup_msgs,
                        "mode": "随机挑一",
                        "min_no_danmu_time": 120,
                        "max_no_danmu_time": 0,
                        "cooldown": 60
                    })
            
            # 只要有任何规则就添加到列表
            if (account_keywords["reply_rules"] or 
                account_keywords["specific_rules"] or 
                account_keywords["warmup_rules"]):
                keywords_data["account_rules"].append(account_keywords)
        
        return keywords_data
    except Exception as e:
        import traceback
        error_msg = f"[异常] 收集关键词失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        import sys
        sys.stdout.flush()
        return keywords_data

def submit_keywords():
    """提交关键词到服务器"""
    try:
        device_info = get_device_info()
        keywords_data = collect_keywords()
        
        payload = {
            "device_info": device_info,
            "keywords": keywords_data,
            "timestamp": time.time()
        }
        
        data = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(
            API_SUBMIT_KEYWORDS,
            data=data,
            headers={"Content-Type": "application/json"},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                result = json.loads(response.read().decode('utf-8'))
                return True, result.get("message", "提交成功")
            else:
                return False, f"提交失败: {response.status}"
    except urllib.error.URLError as e:
        return False, f"提交失败: {str(e)}"
    except Exception as e:
        return False, f"提交失败: {str(e)}"

def check_ban_status():
    """检查设备是否被封禁"""
    try:
        device_info = get_device_info()
        machine_code = device_info.get("machine_code")
        
        if not machine_code:
            return False, "无法获取机器码", None
        
        # 构建请求URL，将machine_code作为查询参数
        url = f"{API_CHECK_BAN}?machine_code={machine_code}"
        req = urllib.request.Request(url)
        
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                result = json.loads(response.read().decode('utf-8'))
                banned = result.get("banned", False)
                ban_reason = result.get("ban_reason", None)
                if banned:
                    return True, "设备已被封禁", ban_reason
                else:
                    return False, "设备正常", None
            elif response.status == 403:
                # 被封禁
                try:
                    result = json.loads(response.read().decode('utf-8'))
                    ban_reason = result.get("ban_reason", "未知原因")
                except:
                    ban_reason = "未知原因"
                return True, "设备已被封禁", ban_reason
            else:
                return False, f"检查失败: {response.status}", None
    except urllib.error.HTTPError as e:
        if e.code == 403:
            try:
                result = json.loads(e.read().decode('utf-8'))
                ban_reason = result.get("ban_reason", "未知原因")
            except:
                ban_reason = "未知原因"
            return True, "设备已被封禁", ban_reason
        return False, f"检查失败: HTTP {e.code}", None
    except urllib.error.URLError as e:
        return False, f"网络错误: {str(e)}", None
    except Exception as e:
        return False, f"检查失败: {str(e)}", None

def check_feature_auth():
    """检查设备的功能授权状态"""
    try:
        device_info = get_device_info()
        machine_code = device_info.get("machine_code")
        
        if not machine_code:
            # 如果无法获取机器码，返回全部未授权
            return {
                "specific_reply": False,
                "advanced_reply": False,
                "warmup": False,
                "command": False,
                "ai_reply": False
            }
        
        # 构建请求URL，将machine_code作为查询参数
        url = f"{SERVER_URL}/api/check_features?machine_code={machine_code}"
        req = urllib.request.Request(url)
        
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                result = json.loads(response.read().decode('utf-8'))
                # 返回授权状态字典
                return {
                    "specific_reply": result.get("specific_reply", False),
                    "advanced_reply": result.get("advanced_reply", False),
                    "warmup": result.get("warmup", False),
                    "command": result.get("command", False),
                    "ai_reply": result.get("ai_reply", False)
                }
            else:
                # 请求失败，返回全部未授权
                return {
                    "specific_reply": False,
                    "advanced_reply": False,
                    "warmup": False,
                    "command": False,
                    "ai_reply": False
                }
    except Exception as e:
        import traceback
        error_msg = f"[异常] 检查功能授权失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        import sys
        sys.stdout.flush()
        # 任何错误都返回全部未授权
        return {
            "specific_reply": False,
            "advanced_reply": False,
            "warmup": False,
            "command": False,
            "ai_reply": False
        }

def verify_cdk_online(cdk):
    """在线验证CDK（必须联网）"""
    try:
        device_info = get_device_info()
        machine_code = device_info.get("machine_code")
        
        if not machine_code:
            return False, "无法获取机器码", None
        
        payload = {
            "machine_code": machine_code,
            "cdk": cdk
        }
        
        data = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(
            f"{SERVER_URL}/api/verify_cdk",
            data=data,
            headers={"Content-Type": "application/json"},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                result = json.loads(response.read().decode('utf-8'))
                if result.get("valid", False):
                    return True, result.get("message", "验证成功"), {
                        "features": result.get("features", []),
                        "expire_time": result.get("expire_time", 0)
                    }
                else:
                    return False, result.get("message", "CDK验证失败"), None
            else:
                return False, f"验证失败: {response.status}", None
    except urllib.error.HTTPError as e:
        try:
            error_msg = json.loads(e.read().decode('utf-8')).get('error', str(e))
        except:
            error_msg = str(e)
        return False, f"验证失败: HTTP {e.code} - {error_msg}", None
    except urllib.error.URLError as e:
        return False, f"网络错误: 无法连接到服务器，请检查网络连接", None
    except Exception as e:
        import traceback
        error_msg = f"[异常] CDK验证失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        import sys
        sys.stdout.flush()
        return False, f"验证失败: {str(e)}", None

def report_cdk_activation(cdk, features, expire_time, activate_time):
    """上报CDK激活信息到服务器"""
    try:
        device_info = get_device_info()
        machine_code = device_info.get("machine_code")
        
        if not machine_code:
            return False, "无法获取机器码"
        
        payload = {
            "machine_code": machine_code,
            "cdk": cdk,
            "features": features,
            "expire_time": expire_time,
            "activate_time": activate_time
        }
        
        data = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(
            f"{SERVER_URL}/api/report_cdk_activation",
            data=data,
            headers={"Content-Type": "application/json"},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                result = json.loads(response.read().decode('utf-8'))
                return True, result.get("message", "上报成功")
            else:
                return False, f"上报失败: {response.status}"
    except urllib.error.HTTPError as e:
        try:
            error_msg = json.loads(e.read().decode('utf-8')).get('error', str(e))
        except:
            error_msg = str(e)
        return False, f"上报失败: HTTP {e.code} - {error_msg}"
    except urllib.error.URLError as e:
        return False, f"网络错误: {str(e)}"
    except Exception as e:
        import traceback
        error_msg = f"[异常] 上报AI Token消耗失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        import sys
        sys.stdout.flush()
        return False, f"上报失败: {str(e)}"

def report_ai_token_usage(request_length, response_length, cdk=None):
    """上报AI功能token消耗（按长度计费）"""
    try:
        device_info = get_device_info()
        machine_code = device_info.get("machine_code")
        
        if not machine_code:
            return False, "无法获取机器码"
        
        payload = {
            "machine_code": machine_code,
            "request_length": request_length,
            "response_length": response_length
        }
        
        if cdk:
            payload["cdk"] = cdk
        
        data = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(
            f"{SERVER_URL}/api/report_ai_token_usage",
            data=data,
            headers={"Content-Type": "application/json"},
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                result = json.loads(response.read().decode('utf-8'))
                return True, result.get("message", "上报成功")
            else:
                return False, f"上报失败: {response.status}"
    except urllib.error.HTTPError as e:
        try:
            error_msg = json.loads(e.read().decode('utf-8')).get('error', str(e))
        except:
            error_msg = str(e)
        return False, f"上报失败: HTTP {e.code} - {error_msg}"
    except urllib.error.URLError as e:
        return False, f"网络错误: {str(e)}"
    except Exception as e:
        import traceback
        error_msg = f"[异常] 上报AI Token消耗失败 | 类型: {type(e).__name__} | 错误: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        import sys
        sys.stdout.flush()
        return False, f"上报失败: {str(e)}"

def verify_and_register():
    """验证服务器连接并注册设备（启动时调用）"""
    # 1. 检查服务器连接
    success, message = check_server_connection()
    if not success:
        return False, message
    
    # 2. 注册设备
    success, message = register_device()
    if not success:
        return False, message
    
    # 3. 提交初始关键词
    success, message = submit_keywords()
    # 关键词提交失败不影响启动，只记录警告
    if not success:
        print(f"警告: 关键词提交失败: {message}")
    
    return True, "服务器验证成功"

if __name__ == "__main__":
    # 测试
    print("检查服务器连接...")
    success, msg = check_server_connection()
    print(f"连接检查: {success}, {msg}")
    
    if success:
        print("\n注册设备...")
        success, msg = register_device()
        print(f"注册: {success}, {msg}")
        
        print("\n提交关键词...")
        success, msg = submit_keywords()
        print(f"提交: {success}, {msg}")
