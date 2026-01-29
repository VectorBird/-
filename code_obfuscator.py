"""
代码混淆模块 - 用于保护服务器配置信息
"""
import base64

def get_server_config():
    """获取服务器配置（解密）"""
    # 服务器配置（base64编码）
    # 服务器地址：http://14.103.165.9/ （通过Nginx反向代理，默认80端口）
    encoded_host = 'MTQuMTAzLjE2NS45'  # 14.103.165.9
    encoded_port = ''  # 空字符串表示使用默认端口（80）
    
    host = base64.b64decode(encoded_host).decode('utf-8')
    port = base64.b64decode(encoded_port).decode('utf-8') if encoded_port else ''
    
    return {
        'host': host,
        'port': port
    }

def get_api_url(endpoint):
    """获取API端点URL"""
    config = get_server_config()
    # 如果端口为空，使用默认HTTP端口（80），不显示端口号
    if config['port']:
        base_url = f"http://{config['host']}:{config['port']}"
    else:
        base_url = f"http://{config['host']}"
    
    endpoints = {
        'health': f"{base_url}/api/health",
        'register': f"{base_url}/api/register",
        'submit_keywords': f"{base_url}/api/submit_keywords",
        'check_ban': f"{base_url}/api/check_ban",
        'check_features': f"{base_url}/api/check_features",
        'verify_cdk': f"{base_url}/api/verify_cdk",
        'report_cdk': f"{base_url}/api/report_cdk_activation"  # 服务端端点：/api/report_cdk_activation
    }
    
    return endpoints.get(endpoint, f"{base_url}/api/{endpoint}")
