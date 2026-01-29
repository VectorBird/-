"""
用户协议对话框
"""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTextEdit, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

class AgreementDialog(QDialog):
    """用户协议对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("用户协议")
        self.setFixedSize(700, 600)
        self.setModal(True)  # 模态对话框，必须处理完才能继续
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        
        # 设置对话框背景色为白色，确保文字可见（防止深色模式下白底白字）
        self.setStyleSheet("""
            QDialog {
                background-color: white;
            }
            QLabel {
                color: #333;
                background-color: transparent;
            }
            QCheckBox {
                color: #333;
                background-color: transparent;
            }
            QCheckBox::indicator {
                border: 1px solid #999;
                background-color: white;
            }
            QCheckBox::indicator:checked {
                background-color: #28a745;
                border-color: #28a745;
            }
        """)
        
        # 布局
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title = QLabel("📋 用户协议与隐私声明")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #333; background-color: transparent;")
        layout.addWidget(title)
        
        # 协议内容
        agreement_text = QTextEdit()
        agreement_text.setReadOnly(True)
        agreement_text.setHtml(self._get_agreement_text())
        agreement_text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 10px;
                background-color: white;
                color: #333;
                font-size: 11pt;
                line-height: 1.6;
            }
        """)
        layout.addWidget(agreement_text)
        
        # 同意复选框
        self.agree_checkbox = QCheckBox("我已阅读并同意以上协议")
        self.agree_checkbox.setStyleSheet("color: #333; background-color: transparent;")
        self.agree_checkbox.stateChanged.connect(self._on_checkbox_changed)
        layout.addWidget(self.agree_checkbox)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.disagree_btn = QPushButton("不同意并退出")
        self.disagree_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        self.disagree_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.disagree_btn)
        
        self.agree_btn = QPushButton("同意并继续")
        self.agree_btn.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 12pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #ccc;
            }
        """)
        self.agree_btn.setEnabled(False)  # 初始状态禁用
        self.agree_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.agree_btn)
        
        layout.addLayout(button_layout)
        
        self.accepted = False
    
    def _on_checkbox_changed(self, state):
        """复选框状态改变"""
        self.agree_btn.setEnabled(state == Qt.CheckState.Checked.value)
    
    def _get_agreement_text(self):
        """获取协议文本"""
        return """
        <div style="font-family: 'Microsoft YaHei', Arial, sans-serif; line-height: 1.8; color: #333; background-color: white;">
            <h3 style="color: #333; margin-top: 0;">重要提示</h3>
            <p style="color: #d32f2f; font-weight: bold; background-color: #ffebee; padding: 10px; border-radius: 5px;">
                使用本软件前，请仔细阅读以下协议。点击"同意并继续"即表示您已充分理解并接受本协议的所有条款。
            </p>
            
            <h3 style="color: #333; margin-top: 20px;">一、数据收集说明</h3>
            <p>
                为了确保软件的正常运行和防止非法使用，本软件会收集以下信息并上传至服务器：
            </p>
            <ul style="margin-left: 20px;">
                <li><strong>IP地址：</strong>用于识别设备网络位置，防止滥用</li>
                <li><strong>MAC地址：</strong>用于唯一标识设备，建立设备档案</li>
                <li><strong>使用用途：</strong>记录您的关键词策略和回复内容，用于合规性检查</li>
                <li><strong>设备信息：</strong>包括主机名、操作系统、平台版本等基础信息</li>
            </ul>
            <p style="color: #666; font-size: 10pt;">
                我们承诺：收集的数据仅用于软件运行、安全防护和合规性检查，不会用于任何商业目的，不会泄露给第三方。
            </p>
            
            <h3 style="color: #333; margin-top: 20px;">二、使用规范</h3>
            <p><strong>本软件严格禁止以下行为：</strong></p>
            <ul style="margin-left: 20px;">
                <li>❌ 在他人直播间恶意带节奏、引战、传播不良信息</li>
                <li>❌ 使用本软件进行任何违法违规活动</li>
                <li>❌ 利用本软件干扰正常直播秩序</li>
                <li>❌ 将本软件用于任何商业用途或倒卖</li>
                <li>❌ 修改、逆向工程本软件</li>
            </ul>
            <p style="color: #d32f2f; font-weight: bold;">
                违规者将被立即封禁设备，且无法继续使用本软件。
            </p>
            
            <h3 style="color: #333; margin-top: 20px;">三、软件性质</h3>
            <p style="background-color: #e8f5e9; padding: 15px; border-radius: 5px; border-left: 4px solid #4caf50;">
                <strong style="font-size: 12pt; color: #2e7d32;">✓ 本软件完全免费</strong><br>
                <strong style="font-size: 12pt; color: #2e7d32;">✓ 仅供学习交流使用</strong><br>
                本软件由开发者"故里何日还"独立开发，旨在解决抖音直播控场问题，提供学习交流的平台。
                我们反对任何形式的商业化、倒卖行为。
            </p>
            
            <h3 style="color: #333; margin-top: 20px;">四、违规举报</h3>
            <p>
                如发现本软件被用于违规用途，请立即联系开发者：
            </p>
            <ul style="margin-left: 20px;">
                <li><strong>邮箱：</strong>ncomscook@qq.com</li>
            </ul>
            <p>
                我们将及时处理违规行为，并下架相关功能以维护良好的使用环境。
            </p>
            
            <h3 style="color: #333; margin-top: 20px;">五、免责声明</h3>
            <p style="color: #666; font-size: 10pt;">
                用户使用本软件所产生的一切后果由用户自行承担。开发者不对因使用本软件而产生的任何损失负责。
                用户应当遵守抖音平台的相关规定，合理合法使用本软件。
            </p>
            
            <p style="margin-top: 30px; text-align: center; color: #999; font-size: 10pt;">
                最后更新：2026年1月
            </p>
        </div>
        """
    
    def exec(self):
        """执行对话框"""
        result = super().exec()
        self.accepted = (result == QDialog.DialogCode.Accepted)
        return result

