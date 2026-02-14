# BT 下载工具（Windows + HTML 界面）

这是一个基于 Python 标准库 HTTP 服务 + aria2c 的轻量 BT 下载工具，提供 HTML 界面。

## 功能
- 支持 `magnet` 链接。
- 支持上传 `.torrent` 文件。
- 显示下载状态、进度、速度、剩余时间。
- 不在应用层主动设置下载限速（实际速度受网络与资源情况影响）。

## 环境要求
1. Python 3.10+
2. aria2（确保 `aria2c` 在系统 PATH；或设置 `ARIA2C_PATH` 环境变量）

## 安装运行
```bash
pip install -r requirements.txt
python app.py
```

浏览器访问：`http://127.0.0.1:5000`

## Windows 提示
- 下载目录可填如：`D:\Downloads`
- 若提示 aria2c 不存在，请检查 PATH 或设置：
```powershell
$env:ARIA2C_PATH="C:\tools\aria2\aria2c.exe"
```

## 免责声明
请仅下载你有合法权利获取与分发的内容，并遵守当地法律法规与网络服务条款。
