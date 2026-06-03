@echo off
cd /d %~dp0
echo ============================================
echo  Building SerialTool.exe with PyInstaller
echo ============================================
echo.

pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name SerialTool ^
  --icon icon.ico ^
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
  main.py

echo.
if exist "%~dp0dist\SerialTool\SerialTool.exe" (
  echo ============================================
  echo  Build OK
  echo  Output: %~dp0dist\SerialTool\
  echo  Run:    dist\SerialTool\SerialTool.exe
  echo ============================================
) else (
  echo ============================================
  echo  Build FAILED
  echo ============================================
)
pause
