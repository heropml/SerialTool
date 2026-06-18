@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo ============================================
echo  打包定制头像版（临时，不动正式图标/源码）
echo ============================================
echo.
if not "%~1"=="" (
    set "IMG=%~1"
    goto run
)
set /p "IMG=把图片拖到这个窗口然后回车（或粘贴路径）: "
:run
rem 去掉拖拽自动带上的引号，下面再统一加回（兼容含空格的路径）
set "IMG=%IMG:"=%"
echo.
py -3 scripts\build_custom.py "%IMG%"
echo.
echo 产物在 dist_onefile\ 下（文件名带后缀）。
pause
