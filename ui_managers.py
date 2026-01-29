"""
UI窗口管理模块 - 配置窗口管理器
"""
import os
import sys
import json
import threading
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QCheckBox, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QSpinBox, QComboBox, QTextEdit, QLabel,
                             QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from config_manager import save_cfg

class BaseRuleManager(QWidget):
    """规则管理器基类 - 用于管理关键词回复和特定回复规则"""
    
    def __init__(self, cfg_ref, title, cfg_key, account_name=None, save_callback=None):
        """
        初始化规则管理器
        
        Args:
            cfg_ref: 配置字典引用
            title: 窗口标题
            cfg_key: 配置键名（reply_rules 或 specific_rules）
            account_name: 账户名称（可选，用于账户级别配置）
            save_callback: 保存回调函数（可选，如果提供则使用此回调保存，否则使用全局save_cfg）
        """
        super().__init__()
        self.cfg = cfg_ref
        self.cfg_key = cfg_key
        self.account_name = account_name
        self.save_callback = save_callback
        title_suffix = " | 开发者: 故里何日还 | 仅供学习交流，禁止倒卖"
        self.setWindowTitle(f"{title}{title_suffix}")
        self.setFixedSize(900, 500)
        
        # 设置窗口图标
        try:
            from path_utils import get_resource_path
            icon_path = get_resource_path("favicon.ico")
            if icon_path and os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except (ImportError, Exception):
            # 如果path_utils不可用或出错，使用旧逻辑（向后兼容）
            try:
                if getattr(sys, 'frozen', False):
                    base_dir = sys._MEIPASS
                else:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                icon_path = os.path.join(base_dir, "favicon.ico")
                if not os.path.exists(icon_path):
                    icon_path = os.path.join(os.getcwd(), "favicon.ico")
                if os.path.exists(icon_path):
                    self.setWindowIcon(QIcon(icon_path))
            except:
                pass
        
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["启用", "关键词 (|分隔)", "回复池 (|分隔)", "模式", "冷却(秒)"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # 关键词列也可以拉伸
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        
        # 加载现有规则
        for rule in self.cfg.get(self.cfg_key, []):
            self.add_row(rule)
            
        # 按钮行
        btn_row = QHBoxLayout()
        b_add = QPushButton("+ 添加")
        b_add.clicked.connect(lambda: self.add_row({}))
        btn_row.addWidget(b_add)
        
        b_delete = QPushButton("🗑️ 删除选中")
        b_delete.setStyleSheet("background:#dc3545; color:white;")
        b_delete.clicked.connect(self.delete_selected_row)
        btn_row.addWidget(b_delete)
        
        b_export = QPushButton("📤 导出配置")
        b_export.setStyleSheet("background:#17a2b8; color:white;")
        b_export.clicked.connect(self.export_config)
        btn_row.addWidget(b_export)
        
        b_import = QPushButton("📥 导入配置")
        b_import.setStyleSheet("background:#ffc107; color:#333;")
        b_import.clicked.connect(self.import_config)
        btn_row.addWidget(b_import)
        
        btn_row.addStretch()
        
        b_save = QPushButton("💾 保存配置")
        b_save.setStyleSheet("background:#28a745; color:white; font-weight:bold;")
        b_save.clicked.connect(self.save_data)
        btn_row.addWidget(b_save)
        layout.addLayout(btn_row)
        
    def delete_selected_row(self):
        """删除选中的行"""
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的行！")
            return
        
        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除选中的这一行规则吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.table.removeRow(current_row)
        
    def add_row(self, rule):
        """添加一行规则"""
        r = self.table.rowCount()
        self.table.insertRow(r)
        
        # 启用复选框
        chk = QCheckBox()
        chk.setChecked(rule.get('active', True))
        cw = QWidget()
        cl = QHBoxLayout(cw)
        cl.addWidget(chk)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(r, 0, cw)
        
        # 关键词
        self.table.setItem(r, 1, QTableWidgetItem(rule.get('kw', '')))
        
        # 回复池
        self.table.setItem(r, 2, QTableWidgetItem(rule.get('resp', '')))
        
        # 模式
        cb = QComboBox()
        cb.addItems(["随机挑一", "顺序全发"])
        cb.setCurrentText(rule.get('mode', '随机挑一'))
        self.table.setCellWidget(r, 3, cb)
        
        # 冷却时间
        sb = QSpinBox()
        sb.setRange(0, 600)
        sb.setValue(rule.get('cooldown', 15))
        self.table.setCellWidget(r, 4, sb)
        
    def save_data(self):
        """保存配置数据"""
        new = []
        for r in range(self.table.rowCount()):
            kw = self.table.item(r, 1).text().strip()
            resp = self.table.item(r, 2).text().strip()
            if not kw or not resp:
                continue
                
            active = self.table.cellWidget(r, 0).findChild(QCheckBox).isChecked()
            mode = self.table.cellWidget(r, 3).currentText()
            cd = self.table.cellWidget(r, 4).value()
            
            new.append({
                "kw": kw,
                "resp": resp,
                "mode": mode,
                "cooldown": cd,
                "active": active
            })
            
        self.cfg[self.cfg_key] = new
        
        # 如果提供了保存回调，使用回调保存（账户级别配置）
        if self.save_callback:
            self.save_callback(self.cfg_key, new)
        else:
            # 否则使用全局配置保存（全局配置）
            save_cfg(self.cfg)
        
        # 先关闭窗口，确保UI操作完成
        self.close()
        
        # 保存后自动上传关键词到服务器（静默运行，异步执行，不阻塞UI）
        # 使用独立线程，确保即使上传失败也不影响程序运行
        def submit_keywords_async():
            try:
                from server_client import submit_keywords
                submit_keywords()
            except Exception:
                # 静默失败，完全不影响UI和程序运行
                pass
        
        # 在独立线程中异步执行，避免阻塞
        try:
            thread = threading.Thread(target=submit_keywords_async, daemon=True)
            thread.start()
        except Exception:
            # 即使线程创建失败也不影响程序运行
            pass
    
    def export_config(self):
        """导出配置到JSON文件"""
        try:
            # 收集当前表格中的所有规则
            rules = []
            for r in range(self.table.rowCount()):
                kw_item = self.table.item(r, 1)
                resp_item = self.table.item(r, 2)
                if not kw_item or not resp_item:
                    continue
                kw = kw_item.text().strip()
                resp = resp_item.text().strip()
                if not kw or not resp:
                    continue
                
                active = self.table.cellWidget(r, 0).findChild(QCheckBox).isChecked()
                mode = self.table.cellWidget(r, 3).currentText()
                cd = self.table.cellWidget(r, 4).value()
                
                rules.append({
                    "kw": kw,
                    "resp": resp,
                    "mode": mode,
                    "cooldown": cd,
                    "active": active
                })
            
            if not rules:
                QMessageBox.warning(self, "导出失败", "没有可导出的规则配置！")
                return
            
            # 选择保存文件路径
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出配置",
                f"{self.cfg_key}_config.json",
                "JSON文件 (*.json);;所有文件 (*)"
            )
            
            if not file_path:
                return
            
            # 保存为JSON文件
            export_data = {
                "type": self.cfg_key,
                "version": "1.0",
                "rules": rules
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            QMessageBox.information(self, "导出成功", f"配置已成功导出到：\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出配置时发生错误：\n{str(e)}")
    
    def import_config(self):
        """从JSON文件导入配置"""
        try:
            # 选择要导入的文件
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "导入配置",
                "",
                "JSON文件 (*.json);;所有文件 (*)"
            )
            
            if not file_path:
                return
            
            # 读取JSON文件
            with open(file_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # 验证数据格式
            if not isinstance(import_data, dict):
                QMessageBox.warning(self, "导入失败", "文件格式不正确！")
                return
            
            # 检查类型是否匹配
            if import_data.get('type') != self.cfg_key:
                QMessageBox.warning(
                    self, 
                    "导入失败", 
                    f"文件类型不匹配！\n当前类型：{self.cfg_key}\n文件类型：{import_data.get('type', '未知')}"
                )
                return
            
            rules = import_data.get('rules', [])
            if not rules:
                QMessageBox.warning(self, "导入失败", "文件中没有规则数据！")
                return
            
            # 确认导入
            reply = QMessageBox.question(
                self,
                "确认导入",
                f"将要导入 {len(rules)} 条规则，这会覆盖当前的所有规则。\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # 清空当前表格
            self.table.setRowCount(0)
            
            # 导入规则到表格
            for rule in rules:
                self.add_row(rule)
            
            QMessageBox.information(self, "导入成功", f"已成功导入 {len(rules)} 条规则！")
        except json.JSONDecodeError:
            QMessageBox.critical(self, "导入失败", "JSON文件格式错误，无法解析！")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"导入配置时发生错误：\n{str(e)}")


class WarmupManager(QWidget):
    """暖场管理器 - 用于管理多场景暖场规则"""
    
    def __init__(self, cfg_ref, account_name=None, save_callback=None):
        """
        初始化暖场管理器
        
        Args:
            cfg_ref: 配置字典引用
            account_name: 账户名称（可选，用于账户级别配置）
            save_callback: 保存回调函数（可选，如果提供则使用此回调保存，否则使用全局save_cfg）
        """
        super().__init__()
        self.cfg = cfg_ref
        self.account_name = account_name
        self.save_callback = save_callback
        title_suffix = " | 开发者: 故里何日还 | 仅供学习交流，禁止倒卖"
        self.setWindowTitle(f"暖场规则设置{title_suffix}")
        self.setFixedSize(1200, 600)
        self.setWindowFlags(Qt.WindowType.Window)  # 确保是独立窗口
        
        # 设置窗口图标
        try:
            from path_utils import get_resource_path
            icon_path = get_resource_path("favicon.ico")
            if icon_path and os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except (ImportError, Exception):
            # 如果path_utils不可用或出错，使用旧逻辑（向后兼容）
            try:
                if getattr(sys, 'frozen', False):
                    base_dir = sys._MEIPASS
                else:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                icon_path = os.path.join(base_dir, "favicon.ico")
                if not os.path.exists(icon_path):
                    icon_path = os.path.join(os.getcwd(), "favicon.ico")
                if os.path.exists(icon_path):
                    self.setWindowIcon(QIcon(icon_path))
            except:
                pass
        
        layout = QVBoxLayout(self)
        
        # 添加说明标签
        info_label = QLabel("💡 暖场规则说明：\n"
                           "• 触发类型：\n"
                           "  - 无弹幕触发：基于无弹幕时间触发，需要设置最小/最大无弹幕时间\n"
                           "  - 定时触发：按设定的时间间隔定期发送（无论是否有弹幕），只需设置定时间隔\n"
                           "• 规则名称：描述场景（如：长时间无弹幕、冷场后、定时1分钟等）\n"
                           "• 消息池：用 | 分隔多条消息\n"
                           "• 无弹幕触发：需要设置最小/最大无弹幕时间（秒）\n"
                           "• 定时触发：只需设置定时间隔（秒），最小/最大无弹幕时间字段无效")
        info_label.setWordWrap(True)
        # 明确设置背景色和文字颜色，确保在深色模式下可见
        info_label.setStyleSheet("""
            QLabel {
                background-color: white;
                color: #333;
                padding: 8px;
                border-radius: 4px;
            }
        """)
        layout.addWidget(info_label)
        
        # 表格
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "启用", "触发类型", "规则名称", "消息池 (|分隔)", "模式", 
            "最小无弹幕时间(秒)", "最大无弹幕时间(秒)", "冷却/间隔(秒)"
        ])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 140)
        self.table.setColumnWidth(6, 140)
        self.table.setColumnWidth(7, 110)
        layout.addWidget(self.table)
        
        # 加载现有规则
        rules = self.cfg.get('warmup_rules', [])
        # 如果没有新规则但有旧格式warmup_msgs，转换一条默认规则
        if not rules and self.cfg.get('warmup_msgs'):
            old_msgs = self.cfg.get('warmup_msgs', '')
            if old_msgs:
                rules = [{
                    "trigger_type": "无弹幕触发",
                    "name": "默认暖场",
                    "messages": old_msgs,
                    "mode": "随机挑一",
                    "min_no_danmu_time": 120,
                    "max_no_danmu_time": 0,
                    "cooldown": 60,
                    "active": True
                }]
        
        for rule in rules:
            self.add_row(rule)
        
        # 初始化表头（根据所有行的触发类型）
        if self.table.rowCount() > 0:
            # 触发一次更新，初始化表头状态
            self._update_header_for_trigger_type(0, None)
        
        # 按钮行
        btn_row = QHBoxLayout()
        b_add = QPushButton("+ 添加规则")
        b_add.clicked.connect(lambda: self.add_row({}))
        btn_row.addWidget(b_add)
        
        b_delete = QPushButton("🗑️ 删除选中")
        b_delete.setStyleSheet("background:#dc3545; color:white;")
        b_delete.clicked.connect(self.delete_selected_row)
        btn_row.addWidget(b_delete)
        
        b_export = QPushButton("📤 导出配置")
        b_export.setStyleSheet("background:#17a2b8; color:white;")
        b_export.clicked.connect(self.export_config)
        btn_row.addWidget(b_export)
        
        b_import = QPushButton("📥 导入配置")
        b_import.setStyleSheet("background:#ffc107; color:#333;")
        b_import.clicked.connect(self.import_config)
        btn_row.addWidget(b_import)
        
        btn_row.addStretch()
        
        b_save = QPushButton("💾 保存配置")
        b_save.setStyleSheet("background:#28a745; color:white; font-weight:bold;")
        b_save.clicked.connect(self.save)
        btn_row.addWidget(b_save)
        layout.addLayout(btn_row)
        
    def delete_selected_row(self):
        """删除选中的行"""
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的行！")
            return
        
        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除选中的这一行规则吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.table.removeRow(current_row)
            # 更新表头（根据剩余行的触发类型）
            if self.table.rowCount() > 0:
                self._update_header_for_trigger_type(0, None)
        
    def add_row(self, rule):
        """添加一行规则"""
        r = self.table.rowCount()
        self.table.insertRow(r)
        
        # 启用复选框
        chk = QCheckBox()
        chk.setChecked(rule.get('active', True))
        cw = QWidget()
        cl = QHBoxLayout(cw)
        cl.addWidget(chk)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(r, 0, cw)
        
        # 触发类型
        cb_trigger = QComboBox()
        cb_trigger.addItems(["无弹幕触发", "定时触发"])
        trigger_type = rule.get('trigger_type', '无弹幕触发')
        cb_trigger.setCurrentText(trigger_type)
        # 连接信号，当触发类型改变时更新表头标签
        cb_trigger.currentTextChanged.connect(lambda text, row=r: self._update_header_for_trigger_type(row, text))
        self.table.setCellWidget(r, 1, cb_trigger)
        
        # 初始化表头标签（根据当前触发类型）
        self._update_header_for_trigger_type(r, trigger_type)
        
        # 规则名称
        self.table.setItem(r, 2, QTableWidgetItem(rule.get('name', '')))
        
        # 消息池
        self.table.setItem(r, 3, QTableWidgetItem(rule.get('messages', '')))
        
        # 模式
        cb = QComboBox()
        cb.addItems(["随机挑一", "顺序全发"])
        cb.setCurrentText(rule.get('mode', '随机挑一'))
        self.table.setCellWidget(r, 4, cb)
        
        # 最小无弹幕时间
        sb_min = QSpinBox()
        sb_min.setRange(0, 3600)
        sb_min.setValue(rule.get('min_no_danmu_time', 120))
        self.table.setCellWidget(r, 5, sb_min)
        
        # 最大无弹幕时间（0表示无上限）
        sb_max = QSpinBox()
        sb_max.setRange(0, 3600)
        sb_max.setValue(rule.get('max_no_danmu_time', 0))
        self.table.setCellWidget(r, 6, sb_max)
        
        # 冷却时间/时间间隔
        sb_cooldown = QSpinBox()
        sb_cooldown.setRange(0, 3600)  # 增加范围以支持更长的定时间隔
        sb_cooldown.setValue(rule.get('cooldown', 60))
        self.table.setCellWidget(r, 7, sb_cooldown)
    
    def _update_header_for_trigger_type(self, row, trigger_type):
        """根据触发类型更新表头标签和列的可见性"""
        # 检查所有行的触发类型
        has_timed = False
        has_no_danmu = False
        
        for r in range(self.table.rowCount()):
            cb = self.table.cellWidget(r, 1)
            if cb:
                current_type = cb.currentText()
                if current_type == "定时触发":
                    has_timed = True
                else:
                    has_no_danmu = True
        
        # 更新表头标签和列的可见性
        if has_timed and not has_no_danmu:
            # 全部是定时触发
            self.table.setHorizontalHeaderLabels([
                "启用", "触发类型", "规则名称", "消息池 (|分隔)", "模式", 
                "-", "-", "定时间隔(秒)"
            ])
            # 隐藏第5、6列（最小/最大无弹幕时间）
            self.table.setColumnHidden(5, True)
            self.table.setColumnHidden(6, True)
        elif has_no_danmu and not has_timed:
            # 全部是无弹幕触发
            self.table.setHorizontalHeaderLabels([
                "启用", "触发类型", "规则名称", "消息池 (|分隔)", "模式", 
                "最小无弹幕时间(秒)", "最大无弹幕时间(秒)", "冷却(秒)"
            ])
            # 显示第5、6列
            self.table.setColumnHidden(5, False)
            self.table.setColumnHidden(6, False)
        else:
            # 混合类型：显示所有列，使用通用标签
            self.table.setHorizontalHeaderLabels([
                "启用", "触发类型", "规则名称", "消息池 (|分隔)", "模式", 
                "最小无弹幕时间(秒)", "最大无弹幕时间(秒)", "定时间隔(秒)"
            ])
            # 显示所有列（不隐藏）
            self.table.setColumnHidden(5, False)
            self.table.setColumnHidden(6, False)
            self.table.setColumnHidden(7, False)
        
        # 为所有行的控件添加工具提示和启用/禁用状态
        for r in range(self.table.rowCount()):
            cb = self.table.cellWidget(r, 1)
            if cb:
                current_trigger = cb.currentText()
                min_widget = self.table.cellWidget(r, 5)
                max_widget = self.table.cellWidget(r, 6)
                cooldown_widget = self.table.cellWidget(r, 7)
                
                if current_trigger == "定时触发":
                    # 定时触发：禁用最小/最大无弹幕时间字段
                    if min_widget:
                        min_widget.setEnabled(False)
                        min_widget.setToolTip("定时触发模式下此字段无效，将被忽略")
                    if max_widget:
                        max_widget.setEnabled(False)
                        max_widget.setToolTip("定时触发模式下此字段无效，将被忽略")
                    # 定时间隔字段启用
                    if cooldown_widget:
                        cooldown_widget.setEnabled(True)
                        cooldown_widget.setToolTip("定时间隔：每隔多少秒发送一次消息（无论是否有弹幕）")
                else:
                    # 无弹幕触发：启用最小/最大无弹幕时间字段，禁用冷却间隔字段
                    if min_widget:
                        min_widget.setEnabled(True)
                        min_widget.setToolTip("最小无弹幕时间：触发暖场的最小无弹幕时长（秒）")
                    if max_widget:
                        max_widget.setEnabled(True)
                        max_widget.setToolTip("最大无弹幕时间：触发暖场的最大无弹幕时长（秒），0表示无上限")
                    # 冷却间隔字段禁用（无弹幕触发模式下此字段无效）
                    if cooldown_widget:
                        cooldown_widget.setEnabled(False)
                        cooldown_widget.setToolTip("无弹幕触发模式下此字段无效，将被忽略")
        
    def save(self):
        """保存暖场规则"""
        new = []
        for r in range(self.table.rowCount()):
            trigger_type = self.table.cellWidget(r, 1).currentText()
            name_item = self.table.item(r, 2)
            messages_item = self.table.item(r, 3)
            if not name_item or not messages_item:
                continue
            name = name_item.text().strip()
            messages = messages_item.text().strip()
            if not name or not messages:
                continue
            
            active = self.table.cellWidget(r, 0).findChild(QCheckBox).isChecked()
            mode = self.table.cellWidget(r, 4).currentText()
            min_time = self.table.cellWidget(r, 5).value()
            max_time = self.table.cellWidget(r, 6).value()
            cooldown = self.table.cellWidget(r, 7).value()
            
            new.append({
                "trigger_type": trigger_type,
                "name": name,
                "messages": messages,
                "mode": mode,
                "min_no_danmu_time": min_time,
                "max_no_danmu_time": max_time,
                "cooldown": cooldown,
                "active": active
            })
        
        self.cfg['warmup_rules'] = new
        
        # 如果提供了保存回调，使用回调保存（账户级别配置）
        if self.save_callback:
            self.save_callback('warmup_rules', new)
        else:
            # 否则使用全局配置保存（全局配置）
            save_cfg(self.cfg)
        
        # 先关闭窗口，确保UI操作完成
        self.close()
        
        # 保存后自动上传关键词到服务器（静默运行，异步执行，不阻塞UI）
        def submit_keywords_async():
            try:
                from server_client import submit_keywords
                submit_keywords()
            except Exception:
                # 静默失败，完全不影响UI和程序运行
                pass
        
        # 在独立线程中异步执行，避免阻塞
        try:
            thread = threading.Thread(target=submit_keywords_async, daemon=True)
            thread.start()
        except Exception:
            # 即使线程创建失败也不影响程序运行
            pass
    
    def export_config(self):
        """导出暖场规则配置到JSON文件"""
        try:
            # 收集当前表格中的所有规则
            rules = []
            for r in range(self.table.rowCount()):
                name_item = self.table.item(r, 2)
                messages_item = self.table.item(r, 3)
                if not name_item or not messages_item:
                    continue
                name = name_item.text().strip()
                messages = messages_item.text().strip()
                if not name or not messages:
                    continue
                
                trigger_type = self.table.cellWidget(r, 1).currentText()
                active = self.table.cellWidget(r, 0).findChild(QCheckBox).isChecked()
                mode = self.table.cellWidget(r, 4).currentText()
                min_time = self.table.cellWidget(r, 5).value()
                max_time = self.table.cellWidget(r, 6).value()
                cooldown = self.table.cellWidget(r, 7).value()
                
                rules.append({
                    "trigger_type": trigger_type,
                    "name": name,
                    "messages": messages,
                    "mode": mode,
                    "min_no_danmu_time": min_time,
                    "max_no_danmu_time": max_time,
                    "cooldown": cooldown,
                    "active": active
                })
            
            if not rules:
                QMessageBox.warning(self, "导出失败", "没有可导出的暖场规则配置！")
                return
            
            # 选择保存文件路径
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出暖场配置",
                "warmup_rules_config.json",
                "JSON文件 (*.json);;所有文件 (*)"
            )
            
            if not file_path:
                return
            
            # 保存为JSON文件
            export_data = {
                "type": "warmup_rules",
                "version": "1.0",
                "rules": rules
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            QMessageBox.information(self, "导出成功", f"暖场配置已成功导出到：\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出配置时发生错误：\n{str(e)}")
    
    def import_config(self):
        """从JSON文件导入暖场规则配置"""
        try:
            # 选择要导入的文件
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "导入暖场配置",
                "",
                "JSON文件 (*.json);;所有文件 (*)"
            )
            
            if not file_path:
                return
            
            # 读取JSON文件
            with open(file_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # 验证数据格式
            if not isinstance(import_data, dict):
                QMessageBox.warning(self, "导入失败", "文件格式不正确！")
                return
            
            # 检查类型是否匹配
            if import_data.get('type') != 'warmup_rules':
                QMessageBox.warning(
                    self, 
                    "导入失败", 
                    f"文件类型不匹配！\n当前类型：warmup_rules\n文件类型：{import_data.get('type', '未知')}"
                )
                return
            
            rules = import_data.get('rules', [])
            if not rules:
                QMessageBox.warning(self, "导入失败", "文件中没有暖场规则数据！")
                return
            
            # 确认导入
            reply = QMessageBox.question(
                self,
                "确认导入",
                f"将要导入 {len(rules)} 条暖场规则，这会覆盖当前的所有规则。\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # 清空当前表格
            self.table.setRowCount(0)
            
            # 导入规则到表格
            for rule in rules:
                self.add_row(rule)
            
            # 更新表头（根据导入的规则类型）
            if self.table.rowCount() > 0:
                self._update_header_for_trigger_type(0, None)
            
            QMessageBox.information(self, "导入成功", f"已成功导入 {len(rules)} 条暖场规则！")
        except json.JSONDecodeError:
            QMessageBox.critical(self, "导入失败", "JSON文件格式错误，无法解析！")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"导入配置时发生错误：\n{str(e)}")


class AdvancedReplyManager(QWidget):
    """高级回复管理器 - 使用正则表达式匹配同义弹幕"""
    
    def __init__(self, cfg_ref, account_name=None, save_callback=None):
        """
        初始化高级回复管理器
        
        Args:
            cfg_ref: 配置字典引用
            account_name: 账户名称（可选，用于账户级别配置）
            save_callback: 保存回调函数（可选，如果提供则使用此回调保存，否则使用全局save_cfg）
        """
        super().__init__()
        self.cfg = cfg_ref
        self.account_name = account_name
        self.save_callback = save_callback
        title_suffix = " | 开发者: 故里何日还 | 仅供学习交流，禁止倒卖"
        self.setWindowTitle(f"高级回复模式设置{title_suffix}")
        self.setFixedSize(1100, 600)
        self.setWindowFlags(Qt.WindowType.Window)  # 确保是独立窗口
        
        # 设置窗口图标
        try:
            from path_utils import get_resource_path
            icon_path = get_resource_path("favicon.ico")
            if icon_path and os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except (ImportError, Exception):
            try:
                if getattr(sys, 'frozen', False):
                    base_dir = sys._MEIPASS
                else:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                icon_path = os.path.join(base_dir, "favicon.ico")
                if not os.path.exists(icon_path):
                    icon_path = os.path.join(os.getcwd(), "favicon.ico")
                if os.path.exists(icon_path):
                    self.setWindowIcon(QIcon(icon_path))
            except:
                pass
        
        layout = QVBoxLayout(self)
        
        # 添加说明标签
        info_label = QLabel("💡 高级回复模式说明：\n"
                           "⚠️ 使用门槛：需要了解正则表达式语法，建议先学习基础后再使用\n"
                           "• 使用正则表达式匹配相同意思的不同话语，将\"同一意图的N种说法\"压缩为1个模式\n"
                           "• 正则表达式示例：\n"
                           "  - (怎么|如何|怎样|哪里|在哪).*(买|下单|拍|购买)  → 匹配各种购买询问\n"
                           "  - (进|加|加入).*群  → 匹配各种进群询问\n"
                           "  - (价格|多少钱|多少米|价位)  → 匹配价格询问\n"
                           "• 提示：使用括号()分组，使用|表示或，使用.*表示任意字符\n"
                           "• 建议：先用简单模式测试，确认匹配正确后再使用复杂模式\n"
                           "• @回复：可选择是否在回复前添加@用户名，类似@回复规则\n"
                           "• 忽略标点：用于匹配正则表达式时是否忽略标点符号。启用后，匹配时会自动移除所有标点符号（中英文）后再进行正则匹配，提高匹配准确率（默认开启）")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("""
            QLabel {
                background-color: white;
                color: #333;
                padding: 10px;
                border-radius: 4px;
                font-size: 11px;
            }
        """)
        layout.addWidget(info_label)
        
        # 表格
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["启用", "正则表达式", "说明", "回复池 (|分隔)", "模式", "@回复", "忽略标点", "冷却(秒)"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # 正则表达式列拉伸
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # 说明列拉伸
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # 回复池列拉伸
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 80)
        self.table.setColumnWidth(7, 100)
        layout.addWidget(self.table)
        
        # 加载现有规则
        for rule in self.cfg.get('advanced_reply_rules', []):
            self.add_row(rule)
            
        # 按钮行
        btn_row = QHBoxLayout()
        b_add = QPushButton("+ 添加规则")
        b_add.clicked.connect(lambda: self.add_row({}))
        btn_row.addWidget(b_add)
        
        b_delete = QPushButton("🗑️ 删除选中")
        b_delete.setStyleSheet("background:#dc3545; color:white;")
        b_delete.clicked.connect(self.delete_selected_row)
        btn_row.addWidget(b_delete)
        
        b_test = QPushButton("🧪 测试正则")
        b_test.setStyleSheet("background:#6c757d; color:white;")
        b_test.clicked.connect(self.test_regex)
        btn_row.addWidget(b_test)
        
        b_export = QPushButton("📤 导出配置")
        b_export.setStyleSheet("background:#17a2b8; color:white;")
        b_export.clicked.connect(self.export_config)
        btn_row.addWidget(b_export)
        
        b_import = QPushButton("📥 导入配置")
        b_import.setStyleSheet("background:#ffc107; color:#333;")
        b_import.clicked.connect(self.import_config)
        btn_row.addWidget(b_import)
        
        btn_row.addStretch()
        
        b_save = QPushButton("💾 保存配置")
        b_save.setStyleSheet("background:#28a745; color:white; font-weight:bold;")
        b_save.clicked.connect(self.save_data)
        btn_row.addWidget(b_save)
        layout.addLayout(btn_row)
        
    def delete_selected_row(self):
        """删除选中的行"""
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的行！")
            return
        
        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除选中的这一行规则吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.table.removeRow(current_row)
    
    def add_row(self, rule):
        """添加一行规则"""
        r = self.table.rowCount()
        self.table.insertRow(r)
        
        # 启用复选框
        chk = QCheckBox()
        chk.setChecked(rule.get('active', True))
        cw = QWidget()
        cl = QHBoxLayout(cw)
        cl.addWidget(chk)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(r, 0, cw)
        
        # 正则表达式
        pattern_item = QTableWidgetItem(rule.get('pattern', ''))
        pattern_item.setToolTip("输入正则表达式，例如：(怎么|如何).*(买|下单)")
        self.table.setItem(r, 1, pattern_item)
        
        # 说明
        desc_item = QTableWidgetItem(rule.get('description', ''))
        desc_item.setToolTip("描述这个正则表达式的用途，方便管理")
        self.table.setItem(r, 2, desc_item)
        
        # 回复池
        resp_item = QTableWidgetItem(rule.get('resp', ''))
        resp_item.setToolTip("用 | 分隔多条回复消息")
        self.table.setItem(r, 3, resp_item)
        
        # 模式
        cb = QComboBox()
        cb.addItems(["随机挑一", "顺序全发"])
        cb.setCurrentText(rule.get('mode', '随机挑一'))
        self.table.setCellWidget(r, 4, cb)
        
        # @回复复选框
        at_reply_chk = QCheckBox()
        at_reply_chk.setChecked(rule.get('at_reply', False))
        at_reply_chk.setToolTip("启用后，回复消息前会添加@用户名")
        at_reply_cw = QWidget()
        at_reply_cl = QHBoxLayout(at_reply_cw)
        at_reply_cl.addWidget(at_reply_chk)
        at_reply_cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        at_reply_cl.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(r, 5, at_reply_cw)
        
        # 忽略标点复选框
        ignore_punct_chk = QCheckBox()
        ignore_punct_chk.setChecked(rule.get('ignore_punctuation', True))  # 默认开启
        ignore_punct_chk.setToolTip("用于匹配正则表达式时是否忽略标点符号。启用后，匹配时会自动移除所有标点符号（中英文）后再进行正则匹配")
        ignore_punct_cw = QWidget()
        ignore_punct_cl = QHBoxLayout(ignore_punct_cw)
        ignore_punct_cl.addWidget(ignore_punct_chk)
        ignore_punct_cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ignore_punct_cl.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(r, 6, ignore_punct_cw)
        
        # 冷却时间
        sb = QSpinBox()
        sb.setRange(0, 600)
        sb.setValue(rule.get('cooldown', 15))
        self.table.setCellWidget(r, 7, sb)
    
    def test_regex(self):
        """测试正则表达式"""
        import re
        from PyQt6.QtWidgets import QInputDialog
        
        # 获取当前选中的行
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择一行规则进行测试！")
            return
        
        pattern_item = self.table.item(current_row, 1)
        if not pattern_item:
            QMessageBox.warning(self, "提示", "请先输入正则表达式！")
            return
        
        pattern = pattern_item.text().strip()
        if not pattern:
            QMessageBox.warning(self, "提示", "正则表达式不能为空！")
            return
        
        # 验证正则表达式是否有效
        try:
            regex = re.compile(pattern)
        except re.error as e:
            error_msg = str(e)
            # 提供更友好的错误提示
            hint = ""
            if "nothing to repeat" in error_msg.lower() or "重复" in error_msg:
                hint = "\n\n💡 提示：量词（*、+、?、{n}）不能单独使用，需要在前面有要重复的元素。\n例如：使用 '.*' 而不是 '*'\n使用 '(想看|试).*' 而不是 '*想看|试'"
            elif "unterminated" in error_msg.lower() or "未终止" in error_msg:
                hint = "\n\n💡 提示：括号、方括号等符号需要成对出现。\n例如：使用 '(xxx)' 而不是 '(xxx'\n使用 '[xxx]' 而不是 '[xxx'"
            elif "bad character range" in error_msg.lower() or "字符范围" in error_msg:
                hint = "\n\n💡 提示：字符范围需要按顺序排列。\n例如：使用 '[a-z]' 而不是 '[z-a]'"
            
            QMessageBox.critical(
                self, 
                "正则表达式错误", 
                f"正则表达式格式错误：\n\n{error_msg}{hint}\n\n请检查并修正。"
            )
            return
        
        # 输入测试文本
        test_text, ok = QInputDialog.getText(
            self, 
            "测试正则表达式", 
            f"正则表达式：{pattern}\n\n请输入要测试的文本："
        )
        
        if not ok:
            return
        
        # 测试匹配
        match = regex.search(test_text)
        if match:
            QMessageBox.information(
                self, 
                "匹配成功", 
                f"✅ 匹配成功！\n\n"
                f"正则表达式：{pattern}\n"
                f"测试文本：{test_text}\n"
                f"匹配结果：{match.group()}\n"
                f"匹配位置：{match.start()}-{match.end()}"
            )
        else:
            QMessageBox.information(
                self, 
                "未匹配", 
                f"❌ 未匹配\n\n"
                f"正则表达式：{pattern}\n"
                f"测试文本：{test_text}\n\n"
                f"提示：请检查正则表达式是否正确，或测试文本是否包含匹配的内容。"
            )
    
    def save_data(self):
        """保存配置数据"""
        import re
        
        new = []
        for r in range(self.table.rowCount()):
            pattern_item = self.table.item(r, 1)
            resp_item = self.table.item(r, 3)
            
            if not pattern_item or not resp_item:
                continue
                
            pattern = pattern_item.text().strip()
            resp = resp_item.text().strip()
            
            if not pattern or not resp:
                continue
            
            # 验证正则表达式
            try:
                re.compile(pattern)
            except re.error as e:
                error_msg = str(e)
                # 提供更友好的错误提示
                hint = ""
                if "nothing to repeat" in error_msg.lower() or "重复" in error_msg:
                    hint = "\n\n💡 提示：量词（*、+、?、{n}）不能单独使用，需要在前面有要重复的元素。\n例如：使用 '.*' 而不是 '*'\n使用 '(想看|试).*' 而不是 '*想看|试'"
                elif "unterminated" in error_msg.lower() or "未终止" in error_msg:
                    hint = "\n\n💡 提示：括号、方括号等符号需要成对出现。\n例如：使用 '(xxx)' 而不是 '(xxx'\n使用 '[xxx]' 而不是 '[xxx'"
                elif "bad character range" in error_msg.lower() or "字符范围" in error_msg:
                    hint = "\n\n💡 提示：字符范围需要按顺序排列。\n例如：使用 '[a-z]' 而不是 '[z-a]'"
                
                QMessageBox.critical(
                    self, 
                    "正则表达式错误", 
                    f"第 {r+1} 行的正则表达式格式错误：\n\n{error_msg}{hint}\n\n请修正后重试。"
                )
                return
            
            desc_item = self.table.item(r, 2)
            description = desc_item.text().strip() if desc_item else ""
            
            active = self.table.cellWidget(r, 0).findChild(QCheckBox).isChecked()
            mode = self.table.cellWidget(r, 4).currentText()
            at_reply = self.table.cellWidget(r, 5).findChild(QCheckBox).isChecked()
            ignore_punctuation = self.table.cellWidget(r, 6).findChild(QCheckBox).isChecked()
            cd = self.table.cellWidget(r, 7).value()
            
            new.append({
                "pattern": pattern,
                "description": description,
                "resp": resp,
                "mode": mode,
                "at_reply": at_reply,
                "ignore_punctuation": ignore_punctuation,
                "cooldown": cd,
                "active": active
            })
            
        self.cfg['advanced_reply_rules'] = new
        
        # 如果提供了保存回调，使用回调保存（账户级别配置）
        if self.save_callback:
            self.save_callback('advanced_reply_rules', new)
        else:
            # 否则使用全局配置保存（全局配置）
            save_cfg(self.cfg)
        
        # 先关闭窗口，确保UI操作完成
        self.close()
        
        # 保存后自动上传关键词到服务器（静默运行，异步执行，不阻塞UI）
        def submit_keywords_async():
            try:
                from server_client import submit_keywords
                submit_keywords()
            except Exception:
                pass
        
        try:
            thread = threading.Thread(target=submit_keywords_async, daemon=True)
            thread.start()
        except Exception:
            pass
    
    def export_config(self):
        """导出配置到JSON文件"""
        try:
            rules = []
            for r in range(self.table.rowCount()):
                pattern_item = self.table.item(r, 1)
                resp_item = self.table.item(r, 3)
                if not pattern_item or not resp_item:
                    continue
                pattern = pattern_item.text().strip()
                resp = resp_item.text().strip()
                if not pattern or not resp:
                    continue
                
                desc_item = self.table.item(r, 2)
                description = desc_item.text().strip() if desc_item else ""
                active = self.table.cellWidget(r, 0).findChild(QCheckBox).isChecked()
                mode = self.table.cellWidget(r, 4).currentText()
                at_reply = self.table.cellWidget(r, 5).findChild(QCheckBox).isChecked()
                ignore_punctuation = self.table.cellWidget(r, 6).findChild(QCheckBox).isChecked()
                cd = self.table.cellWidget(r, 7).value()
                
                rules.append({
                    "pattern": pattern,
                    "description": description,
                    "resp": resp,
                    "mode": mode,
                    "at_reply": at_reply,
                    "ignore_punctuation": ignore_punctuation,
                    "cooldown": cd,
                    "active": active
                })
            
            if not rules:
                QMessageBox.warning(self, "导出失败", "没有可导出的规则配置！")
                return
            
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "导出配置",
                "advanced_reply_rules_config.json",
                "JSON文件 (*.json);;所有文件 (*)"
            )
            
            if not file_path:
                return
            
            export_data = {
                "type": "advanced_reply_rules",
                "version": "1.0",
                "rules": rules
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            QMessageBox.information(self, "导出成功", f"配置已成功导出到：\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出配置时发生错误：\n{str(e)}")
    
    def import_config(self):
        """从JSON文件导入配置"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "导入配置",
                "",
                "JSON文件 (*.json);;所有文件 (*)"
            )
            
            if not file_path:
                return
            
            with open(file_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            if not isinstance(import_data, dict):
                QMessageBox.warning(self, "导入失败", "文件格式不正确！")
                return
            
            if import_data.get('type') != 'advanced_reply_rules':
                QMessageBox.warning(
                    self, 
                    "导入失败", 
                    f"文件类型不匹配！\n当前类型：advanced_reply_rules\n文件类型：{import_data.get('type', '未知')}"
                )
                return
            
            rules = import_data.get('rules', [])
            if not rules:
                QMessageBox.warning(self, "导入失败", "文件中没有规则数据！")
                return
            
            reply = QMessageBox.question(
                self,
                "确认导入",
                f"将要导入 {len(rules)} 条规则，这会覆盖当前的所有规则。\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            self.table.setRowCount(0)
            
            for rule in rules:
                self.add_row(rule)
            
            QMessageBox.information(self, "导入成功", f"已成功导入 {len(rules)} 条规则！")
        except json.JSONDecodeError:
            QMessageBox.critical(self, "导入失败", "JSON文件格式错误，无法解析！")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"导入配置时发生错误：\n{str(e)}")
