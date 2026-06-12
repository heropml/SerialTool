@echo off
setlocal
REM 单文件版 (onefile) 打包脚本
REM 输出 dist_onefile\SerialTool_onefile_v<版本>.exe (文件名带版本号, 与安装包一致)
REM 版本号从 src\version.py 读, 保持单点真源

cd /d %~dp0..

REM 从 src\version.py 读 __version__
set VER=1.0.0
for /f "delims=" %%v in ('py -3 -c "import sys; sys.path.insert(0,'src'); from version import __version__; print(__version__)" 2^>nul') do set VER=%%v

echo ============================================
echo  Building SerialTool onefile (PyInstaller)
echo  Version: %VER%   (from src\version.py)
echo ============================================
echo.

REM 清掉旧版本的单文件 exe, 只保留本次输出
if exist "dist_onefile\SerialTool_onefile*.exe" del /q "dist_onefile\SerialTool_onefile*.exe"

py -3 -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onefile ^
  --name SerialTool_onefile_v%VER% ^
  --icon assets\icon.ico ^
  --distpath dist_onefile ^
  --workpath build_onefile ^
  --hidden-import serial.tools.list_ports_windows ^
  --exclude-module PyQt5.QtBluetooth ^
  --exclude-module PyQt5.QtDBus ^
  --exclude-module PyQt5.QtDesigner ^
  --exclude-module PyQt5.QtHelp ^
  --exclude-module PyQt5.QtLocation ^
  --exclude-module PyQt5.QtMultimedia ^
  --exclude-module PyQt5.QtMultimediaWidgets ^
  --exclude-module PyQt5.QtNfc ^
  --exclude-module PyQt5.QtOpenGL ^
  --exclude-module PyQt5.QtPositioning ^
  --exclude-module PyQt5.QtQml ^
  --exclude-module PyQt5.QtQuick ^
  --exclude-module PyQt5.QtQuickWidgets ^
  --exclude-module PyQt5.QtRemoteObjects ^
  --exclude-module PyQt5.QtSensors ^
  --exclude-module PyQt5.QtSerialPort ^
  --exclude-module PyQt5.QtSql ^
  --exclude-module PyQt5.QtTest ^
  --exclude-module PyQt5.QtWebChannel ^
  --exclude-module PyQt5.QtWebEngine ^
  --exclude-module PyQt5.QtWebEngineCore ^
  --exclude-module PyQt5.QtWebEngineWidgets ^
  --exclude-module PyQt5.QtWebSockets ^
  --exclude-module PyQt5.QtXmlPatterns ^
  src\main.py

echo.
if exist "dist_onefile\SerialTool_onefile_v%VER%.exe" (
  echo ============================================
  echo  Onefile Build OK
  echo  Output: dist_onefile\SerialTool_onefile_v%VER%.exe
  echo ============================================
) else (
  echo ============================================
  echo  Onefile Build FAILED
  echo ============================================
)
pause
endlocal
