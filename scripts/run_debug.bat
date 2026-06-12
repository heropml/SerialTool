@echo off
REM 调试启动 (保留 console 看 Python 报错)
cd /d %~dp0..
REM 优先 py launcher，回退 python（避免 Microsoft Store 沙盒版的 python 命令静默失败）
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3 src\main.py
) else (
    python src\main.py
)
pause
