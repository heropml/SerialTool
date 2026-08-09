@echo off
REM PC closed-loop soak: Virtual/TCP/UDP, multi-client, UDP no-remote,
REM log size-rotate, .ctrec record, drop/reopen. No hardware required.
REM Usage:
REM   scripts\soak_local.bat
REM   scripts\soak_local.bat 10
REM   scripts\soak_local.bat 10 D:\tmp\soak_metrics.json
setlocal
cd /d "%~dp0.."
set SECONDS=%~1
set METRICS=%~2
if not "%SECONDS%"=="" set COMMTOOL_SOAK=%SECONDS%
if not "%METRICS%"=="" set COMMTOOL_SOAK_METRICS=%METRICS%
if not "%SECONDS%"=="" set COMMTOOL_SOAK_DISCONNECT=1
echo Running local loopback soak (COMMTOOL_SOAK=%COMMTOOL_SOAK% DISCONNECT=%COMMTOOL_SOAK_DISCONNECT% METRICS=%COMMTOOL_SOAK_METRICS%)
py -3 -m pytest tests/test_local_loopback_soak.py -q --tb=short
if errorlevel 1 exit /b %ERRORLEVEL%
REM v1.5 multi-session concurrent Virtual tabs
py -3 -m pytest tests/test_multi_session.py -q --tb=short
if errorlevel 1 exit /b %ERRORLEVEL%
REM Companion S-3 virtual disconnect / extended RX profiles (same PC-only path).
py -3 -m pytest tests/test_soak_throughput.py -k "virtual_link_drop or virtual_disconnect or extended_rx_soak or extended_virtual_disconnect" -q --tb=short
exit /b %ERRORLEVEL%
