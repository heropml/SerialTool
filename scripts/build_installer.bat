@echo off
setlocal
REM Inno Setup 安装包构建脚本
REM 前置: 安装 Inno Setup 6 (winget install JRSoftware.InnoSetup)
REM 前置: dist\CommTool\ 已经由 build.bat 打好

cd /d %~dp0..

REM 找 ISCC.exe (winget 默认装在 user 目录)
set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo ============================================
    echo  Inno Setup not found, install via:
    echo    winget install JRSoftware.InnoSetup
    echo ============================================
    pause
    exit /b 1
)

if not exist "dist\CommTool\CommTool.exe" (
    echo ============================================
    echo  dist\CommTool\CommTool.exe NOT FOUND
    echo  Run build.bat first to build the app folder.
    echo ============================================
    pause
    exit /b 1
)

REM 从 src\version.py 读 __version__ 保持与 main.py 同步
set VER=1.0.0
for /f "delims=" %%v in ('py -3 -c "import sys; sys.path.insert(0,'src'); from version import __version__; print(__version__)" 2^>nul') do set VER=%%v

echo ============================================
echo  Building installer with Inno Setup...
echo  Version: %VER%   (from version.py)
echo ============================================
%ISCC% /DMyAppVersion=%VER% scripts\CommTool.iss

if exist "installer\CommTool_Setup_v%VER%.exe" (
    echo.
    echo ============================================
    echo  Installer Build OK
    echo  Output: installer\CommTool_Setup_v%VER%.exe
    echo ============================================
) else (
    echo.
    echo ============================================
    echo  Installer Build FAILED
    echo ============================================
)
pause
endlocal
