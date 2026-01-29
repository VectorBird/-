"""
抖音智能场控助手 - 主入口文件
"""
# 默认启动主控制面板（支持多小号模式）
# 如需使用单窗口模式，请直接运行 main_window.py

import sys
import traceback
import os
from datetime import datetime

# 抑制退出时的SSL错误输出（这些错误通常发生在程序退出时，不影响功能）
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + 
    " --disable-logging --log-level=3"
)

# 创建日志文件
try:
    from path_utils import get_log_dir
    log_dir = get_log_dir()
except ImportError:
    # 如果path_utils不可用（向后兼容），使用当前目录
    log_dir = "logs"
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except:
            pass

log_file = os.path.join(log_dir, f"startup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

class TeeOutput:
    """同时输出到控制台和文件"""
    def __init__(self, file_path):
        # 在GUI模式下（打包后），sys.stdout可能是None
        self.terminal = sys.stdout
        try:
            self.log_file = open(file_path, 'w', encoding='utf-8')
        except Exception as e:
            # 如果无法创建日志文件，使用None
            print(f"警告: 无法创建日志文件 {file_path}: {e}")
            self.log_file = None
        
    def write(self, message):
        # 只有在terminal不为None时才写入（打包后GUI模式下terminal为None）
        if self.terminal is not None:
            try:
                self.terminal.write(message)
                self.terminal.flush()
            except:
                pass
        
        # 写入日志文件（如果存在）
        if self.log_file:
            try:
                self.log_file.write(message)
                self.log_file.flush()
            except:
                pass
        
    def flush(self):
        try:
            if self.terminal is not None:
                self.terminal.flush()
        except:
            pass
        try:
            if self.log_file:
                self.log_file.flush()
        except:
            pass
        
    def close(self):
        if self.log_file:
            try:
                self.log_file.close()
            except:
                pass

# 设置输出重定向
tee = TeeOutput(log_file)
sys.stdout = tee
sys.stderr = tee

# 强制刷新输出缓冲区（安全刷新，处理None情况）
try:
    if sys.stdout is not None:
        sys.stdout.flush()
except:
    pass
try:
    if sys.stderr is not None:
        sys.stderr.flush()
except:
    pass

# 创建一个安全的刷新辅助函数
def safe_flush():
    """安全地刷新stdout，处理None情况"""
    try:
        if sys.stdout is not None:
            sys.stdout.flush()
    except:
        pass

# 创建一个安全的输入辅助函数（GUI模式下不使用input）
def safe_input_or_exit(prompt="", exit_code=1):
    """安全的输入处理：GUI模式下直接退出，控制台模式下使用input"""
    if getattr(sys, 'frozen', False):
        # 打包后的GUI模式，不使用input，直接退出
        # 如果需要显示错误，应该在调用前使用QMessageBox
        pass
    else:
        # 控制台模式，使用input
        try:
            input(prompt)
        except (EOFError, OSError, RuntimeError):
            # stdin不可用时静默退出
            pass
    sys.exit(exit_code)

if __name__ == "__main__":
    print("=" * 60)
    print("正在启动程序...")
    print(f"日志文件: {log_file}")
    print("=" * 60)
    safe_flush()

    try:
        print("\n[0/4] 验证服务器连接...")
        safe_flush()
        
        # 导入服务器客户端模块
        try:
            from server_client import verify_and_register, check_ban_status
        except ImportError as e:
            print(f"  ✗ 无法导入服务器客户端模块: {e}")
            print("\n错误: 缺少必要的模块，请检查安装")
            safe_flush()
            # GUI模式下直接退出，控制台模式下使用input
            safe_input_or_exit("\n按回车键退出...", 1)
        
        # 首先检查封禁状态（在连接服务器之前）
        print("  正在检查设备状态...")
        safe_flush()
        try:
            is_banned, ban_message, ban_reason = check_ban_status()
            if is_banned:
                print(f"  ✗ {ban_message}")
                print("\n" + "=" * 60)
                print("❌ 设备已被封禁！")
                print("=" * 60)
                reason_text = ban_reason if ban_reason else "未知原因"
                print(f"封禁原因：{reason_text}")
                print("\n程序无法启动。")
                print("如有疑问，请联系开发者：")
                print("  邮箱：ncomscook@qq.com")
                print("=" * 60)
                safe_flush()
                
                # GUI模式下显示弹窗
                if getattr(sys, 'frozen', False):
                    try:
                        from PyQt6.QtWidgets import QApplication, QMessageBox
                        import sys
                        app = QApplication(sys.argv)
                        QMessageBox.critical(
                            None,
                            "设备已被封禁",
                            f"您的设备已被封禁，程序将退出。\n\n"
                            f"封禁原因：{reason_text}\n\n"
                            f"如有疑问，请联系开发者：\n"
                            f"邮箱：ncomscook@qq.com\n"
                            f"微信：ppl7752752"
                        )
                    except Exception as e:
                        pass  # 如果弹窗失败，继续退出
                
                # GUI模式下直接退出，控制台模式下使用input
                safe_input_or_exit("\n按回车键退出...", 1)
        except Exception as e:
            # 检查封禁失败不影响启动（可能是网络问题），继续后续流程
            print(f"  警告: 封禁状态检查失败: {e}")
            safe_flush()
        
        # 验证服务器连接并注册（必须成功才能启动）
        print("  正在连接服务器...")
        safe_flush()
        success, message = verify_and_register()
        
        if not success:
            print(f"  ✗ {message}")
            print("\n" + "=" * 60)
            print("❌ 服务器连接失败！")
            print("=" * 60)
            print(f"错误信息: {message}")
            print("\n程序无法启动，必须连接到服务器才能使用。")
            print("请检查:")
            print("  1. 网络连接是否正常")
            print("  2. 服务器是否正常运行")
            print("  3. 防火墙设置是否正确")
            print("=" * 60)
            safe_flush()
            # GUI模式下直接退出，控制台模式下使用input
            safe_input_or_exit("\n按回车键退出...", 1)
        
        print(f"  ✓ {message}")
        safe_flush()
        
        print("\n[1/4] 导入控制面板模块...")
        safe_flush()
        
        # 先导入必要的模块
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtCore import Qt
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        
        print("  ✓ PyQt6模块导入成功")
        sys.stdout.flush()
        
        # 逐步导入依赖模块，以便定位问题
        print("\n  检查依赖模块...")
        sys.stdout.flush()
        
        try:
            print("    导入 config_manager...", end=" ")
            import config_manager
            print("✓")
            sys.stdout.flush()
        except Exception as e:
            print(f"✗ 错误: {e}")
            raise
        
        try:
            print("    导入 account_manager...", end=" ")
            import account_manager
            print("✓")
            sys.stdout.flush()
        except Exception as e:
            print(f"✗ 错误: {e}")
            raise
        
        try:
            print("    导入 global_message_queue...", end=" ")
            import global_message_queue
            print("✓")
            sys.stdout.flush()
        except Exception as e:
            print(f"✗ 错误: {e}")
            raise
        
        try:
            print("    导入 global_logger...", end=" ")
            import global_logger
            print("✓")
            sys.stdout.flush()
        except Exception as e:
            print(f"✗ 错误: {e}")
            raise
        
        try:
            print("    导入 ui_managers...", end=" ")
            import ui_managers
            print("✓")
            sys.stdout.flush()
        except Exception as e:
            print(f"✗ 错误: {e}")
            raise
        
        # 导入控制面板
        print("\n  导入 control_panel...", end=" ")
        sys.stdout.flush()
        from control_panel import ControlPanel
        print("✓")
        print("  ✓ 控制面板模块导入成功")
        sys.stdout.flush()
        
        print("\n[2/4] 创建QApplication...")
        safe_flush()
        
        # 设置高DPI
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        
        # 创建应用
        app = QApplication(sys.argv)
        print("  ✓ QApplication创建成功")
        sys.stdout.flush()
        
        # 设置User-Agent
        QWebEngineProfile.defaultProfile().setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        
        # 检查用户协议
        print("\n[2.5/4] 检查用户协议...")
        safe_flush()
        try:
            import config_manager
            cfg = config_manager.load_cfg()
            agreement_accepted = cfg.get("agreement_accepted", False)
            
            if not agreement_accepted:
                print("  显示用户协议对话框...")
                safe_flush()
                from agreement_dialog import AgreementDialog
                agreement_dialog = AgreementDialog()
                result = agreement_dialog.exec()
                
                if not agreement_dialog.accepted:
                    print("  用户未同意协议，程序退出")
                    safe_flush()
                    QMessageBox.information(None, "提示", "您必须同意用户协议才能使用本软件。")
                    sys.exit(0)
                
                # 保存协议同意状态
                cfg["agreement_accepted"] = True
                config_manager.save_cfg(cfg)
                print("  ✓ 用户已同意协议")
                safe_flush()
            else:
                print("  ✓ 用户协议已同意")
                safe_flush()
        except Exception as e:
            print(f"  ✗ 协议检查失败: {e}")
            traceback.print_exc()
            sys.stdout.flush()
            QMessageBox.critical(None, "错误", f"协议检查失败: {e}\n程序无法启动。")
            sys.exit(1)
        
        print("\n[3/4] 创建并显示控制面板...")
        safe_flush()
        
        # 创建控制面板
        try:
            panel = ControlPanel()
            print("  ✓ 控制面板创建成功")
            sys.stdout.flush()
        except Exception as e:
            print(f"  ✗ 创建控制面板失败: {e}")
            traceback.print_exc()
            sys.stdout.flush()
            raise
        
        # 显示窗口
        try:
            panel.show()
            print("  ✓ 窗口已显示")
            sys.stdout.flush()
        except Exception as e:
            print(f"  ✗ 显示窗口失败: {e}")
            traceback.print_exc()
            sys.stdout.flush()
            raise
        
        print("\n程序运行中... (关闭窗口即可退出)")
        sys.stdout.flush()
        
        # 运行应用
        exit_code = 0
        try:
            exit_code = app.exec()
        except KeyboardInterrupt:
            print("\n\n用户中断程序（Ctrl+C）")
            sys.stdout.flush()
            exit_code = 0
        except Exception as e:
            print(f"\n程序运行错误: {type(e).__name__}: {e}")
            traceback.print_exc()
            sys.stdout.flush()
            print(f"\n详细日志已保存到: {log_file}")
            sys.stdout.flush()
            exit_code = 1
        
        # 程序退出前清理资源
        try:
            print("\n[退出] 正在清理资源...")
            sys.stdout.flush()
            
            # 清理Qt应用资源
            try:
                if 'panel' in locals():
                    # 关闭控制面板（会触发closeEvent，清理所有资源）
                    panel.close()
                    panel.deleteLater()
            except:
                pass
            
            # 等待一小段时间，让资源清理完成
            import time
            time.sleep(0.5)
            
            # 关闭日志文件
            if hasattr(tee, 'log_file') and tee.log_file:
                tee.log_file.close()
            # 恢复标准输出（如果terminal不是None）
            if hasattr(sys.stdout, 'terminal'):
                if sys.stdout.terminal is not None:
                    sys.stdout = sys.stdout.terminal
                else:
                    # terminal是None（GUI模式），创建一个空对象来避免错误
                    class NullOutput:
                        def write(self, s): pass
                        def flush(self): pass
                    sys.stdout = NullOutput()
        except Exception as e:
            # 退出时的错误不影响退出流程
            pass
        
        print(f"\n程序退出，退出代码: {exit_code}")
        safe_flush()
        
        # 使用os._exit而不是sys.exit，避免等待Qt事件循环
        import os
        os._exit(exit_code)
        
    except KeyboardInterrupt:
        print("\n\n用户中断程序")
        safe_flush()
        sys.exit(0)
        
    except ImportError as e:
        print("\n" + "=" * 60)
        print("❌ 导入错误！")
        print("=" * 60)
        print(f"错误信息: {e}")
        print("\n可能的原因:")
        print("  1. 缺少PyQt6库，请运行: pip install PyQt6 PyQt6-WebEngine")
        print("  2. 缺少其他依赖库")
        print("\n详细错误:")
        traceback.print_exc()
        safe_flush()
        print(f"\n详细日志已保存到: {log_file}")
        safe_flush()
        # GUI模式下直接退出，控制台模式下使用input
        safe_input_or_exit("\n按回车键退出...", 1)
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ 程序启动失败！")
        print("=" * 60)
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {e}")
        print("\n详细错误堆栈:")
        print("-" * 60)
        traceback.print_exc()
        print("=" * 60)
        safe_flush()
        print(f"\n详细日志已保存到: {log_file}")
        safe_flush()
        # GUI模式下直接退出，控制台模式下使用input
        safe_input_or_exit("\n按回车键退出...", 1)
