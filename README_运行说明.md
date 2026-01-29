# 运行说明

## 重要提示

由于Windows环境变量配置的问题，建议使用以下方式运行程序：

### 方法1：使用PowerShell运行（推荐）

1. 在项目目录下，右键点击空白处
2. 选择"在终端中打开"（或"Open in Terminal"）
3. 确保打开的是 PowerShell（而不是CMD）
4. 运行：
   ```powershell
   python main.py
   ```

### 方法2：使用启动脚本

双击运行 `启动程序.bat`，脚本会自动使用PowerShell启动程序。

### 方法3：直接运行（如果python命令可用）

如果命令行中 `python` 命令可用，直接运行：
```bash
python main.py
```

## 如果遇到"No module named 'requests'"错误

在PowerShell中运行：
```powershell
python -m pip install requests
```

然后再次运行程序。

## 服务器要求

程序启动前需要：
1. 服务器 `14.103.165.9:8080` 已启动并运行
2. 网络连接正常
3. 防火墙允许访问8080端口

如果服务器未运行，程序将无法启动（这是正常的安全机制）。









