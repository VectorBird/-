"""
打包脚本 - 将程序打包成EXE文件
"""
import os
import sys

def build_exe():
    """打包程序为EXE"""
    print("=" * 60)
    print("开始打包程序...")
    print("=" * 60)
    
    try:
        import PyInstaller.__main__
    except ImportError:
        print("错误: 未安装PyInstaller")
        print("请运行: pip install pyinstaller")
        sys.exit(1)
    
    # 构建数据文件列表
    datas = ['favicon.ico;.']
    # 如果存在二维码图片，也包含它（可选）
    if os.path.exists('wechat_qr.png'):
        datas.append('wechat_qr.png;.')
    if os.path.exists('wechat_qr.jpg'):
        datas.append('wechat_qr.jpg;.')
    if os.path.exists('微信二维码.png'):
        datas.append('微信二维码.png;.')
    if os.path.exists('微信二维码.jpg'):
        datas.append('微信二维码.jpg;.')
    
    # PyInstaller参数
    args = [
        'main.py',  # 主入口文件
        '--name=抖音直播中控控场工具V3.0版本',  # 生成的EXE名称
        '--onefile',  # 打包成单个EXE文件
        '--windowed',  # 无控制台窗口（GUI程序）
        '--noconsole',  # 不显示控制台
        
        # PyQt6核心模块
        '--hidden-import=PyQt6.QtCore',
        '--hidden-import=PyQt6.QtGui',
        '--hidden-import=PyQt6.QtWidgets',
        '--hidden-import=PyQt6.QtWebEngineWidgets',
        '--hidden-import=PyQt6.QtWebEngineCore',
        '--hidden-import=PyQt6.QtWebChannel',
        
        # 收集WebEngine相关资源（重要！）
        '--collect-all=PyQt6.QtWebEngineWidgets',
        '--collect-all=PyQt6.QtWebEngineCore',
        
        # 自定义模块
        '--hidden-import=config_manager',
        '--hidden-import=danmu_monitor',
        '--hidden-import=reply_handler',
        '--hidden-import=warmup_handler',
        '--hidden-import=message_sender',
        '--hidden-import=ui_managers',
        '--hidden-import=account_manager',
        '--hidden-import=global_message_queue',
        '--hidden-import=global_logger',
        '--hidden-import=statistics_manager',
        '--hidden-import=control_panel',
        '--hidden-import=main_window',
        '--hidden-import=agreement_dialog',  # 用户协议对话框
        '--hidden-import=device_info',  # 设备信息收集
        '--hidden-import=server_client',  # 服务器客户端通信
        
        # 添加数据文件（Windows格式：源文件;目标目录）
        # 设置EXE文件图标
        '--icon=favicon.ico',
        
        '--clean',  # 清理临时文件
    ]
    
    # 添加数据文件
    for data in datas:
        args.append(f'--add-data={data}')
    
    # 执行打包
    try:
        print("\n正在执行PyInstaller打包，这可能需要几分钟时间...")
        print("请耐心等待...\n")
        PyInstaller.__main__.run(args)
        print("\n" + "=" * 60)
        print("✓ 打包完成！")
        print("=" * 60)
        print(f"\nEXE文件位置: dist\\抖音直播中控控场工具V3.0版本.exe")
        print("\n注意事项:")
        print("1. EXE文件可能比较大（100MB+），这是正常的（包含Qt WebEngine）")
        print("2. 首次运行可能需要几秒钟启动时间")
        print("3. 如果遇到问题，请检查日志文件")
        print("=" * 60)
    except Exception as e:
        print(f"\n打包失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    build_exe()
