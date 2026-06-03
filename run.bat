@echo off
REM 静默启动 (GUI 版 Python，无 console 窗口)
REM 优先 pyw launcher，回退 pythonw（避免 Microsoft Store 沙盒版的 python 命令静默失败）
where pyw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pyw "%~dp0main.py"
) else (
    start "" pythonw "%~dp0main.py"
)
