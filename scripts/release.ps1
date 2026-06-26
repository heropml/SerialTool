#Requires -Version 7
<#
.SYNOPSIS
    CommTool 一键发版脚本（Windows 双包 + 双远程 + 双 Release）。

    一条命令完成：改版本号 → 改 latest.json(url 指 Gitee) → 打包(folder 安装包 + onefile) →
    git 提交 → push github + gitee → 建 GitHub Release(--latest) → 发 Gitee Release。
    app「关于 → 检查更新」随后即可检测到新版本（国内走 Gitee、海外回退 GitHub）。
    macOS .dmg 仍由协作者在 Mac 上跑 release_macos.sh 补到同一 Release。

.PARAMETER Version
    新版本号，格式 X.Y.Z（如 1.1.4）。

.PARAMETER Notes
    本次更新说明，会写进 latest.json 和两个 Release 的说明。

.PARAMETER Local
    只本地打包 + 提交，跳过 push 和 Release（用于试打包）。

.EXAMPLE
    .\scripts\release.ps1 1.1.4 "自动应答帧头+长度组帧 + 多条发送增强"

.NOTES
    依赖：Python(py)+PyInstaller、Inno Setup 6、GitHub CLI(gh，需 gh auth login)、
         Gitee 令牌（scripts/.gitee_token，给 release_gitee.py 用）。
    Release tag 用「comm-v 前缀」(comm-v1.1.4)，与串口版 v1.0.x、网络版 net-v1.0.x 区分。
    下载源走 Gitee：latest.json 的 url 指向 Gitee Release（updater 第一源是 Gitee raw latest.json）。
    CommTool 现为本仓库主力产品 → GitHub Release 用 --latest（持有「Latest」徽章）。
    ⚠️ 脚本不动三语用户文档：发版后需手动给 docs/USAGE.md · 使用说明.md · 使用說明.md
       各补 vN 版本历史章节 + 目录条目 + 右下角「当前版本号」（脚本结尾会再提醒）。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)][string]$Version,
    [Parameter(Mandatory, Position = 1)][string]$Notes,
    [switch]$Local
)

$ErrorActionPreference = 'Stop'
$Repo   = 'heropml/SerialTool'
$Branch = 'CommTool'

# ---- 0. 定位项目根 + 校验 ----
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "版本号格式应为 X.Y.Z（如 1.1.4），你给的是 '$Version'"
}
$Tag         = "comm-v$Version"
$SetupName   = "CommTool_Setup_v$Version.exe"
$SetupPath   = Join-Path $Root "installer\$SetupName"
$OnefileName = "CommTool_v$Version.exe"
$OnefilePath = Join-Path $Root "dist_onefile\$OnefileName"
# 下载源走 Gitee（全球可达；updater 第一源为 Gitee raw latest.json）
$DownloadUrl = "https://gitee.com/$Repo/releases/download/$Tag/$SetupName"

Write-Host "==== 发版 CommTool $Tag ====" -ForegroundColor Cyan

# ---- 工具路径 ----
$Iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) { $Iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $Iscc)) { throw "找不到 Inno Setup 的 ISCC.exe" }
$Gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $Gh) { $Gh = "C:\Program Files\GitHub CLI\gh.exe" }
if (-not (Test-Path $Gh)) { throw "找不到 GitHub CLI(gh)，请先安装并 gh auth login" }

# ---- 1. 写版本号 ----
Write-Host "① 写入版本号 $Version → src/version.py"
$vp   = Join-Path $Root 'src\version.py'
$vtxt = [IO.File]::ReadAllText($vp)
$vtxt = [regex]::Replace($vtxt, '__version__\s*=\s*"[^"]*"', "__version__ = `"$Version`"")
[IO.File]::WriteAllText($vp, $vtxt)

# ---- 2. 更新 latest.json（url 指向 Gitee Release）----
Write-Host "② 更新 latest.json → $Version（url 指向 Gitee $Tag）"
$manifest = [ordered]@{ version = $Version; url = $DownloadUrl; notes = $Notes }
$json = $manifest | ConvertTo-Json -Depth 3
[IO.File]::WriteAllText((Join-Path $Root 'latest.json'), $json)

# ---- PyQt5 裁剪（folder 与 onefile 共用，去掉用不到的 Qt 模块缩小体积）----
$excludes = @(
    'PyQt5.QtBluetooth','PyQt5.QtDBus','PyQt5.QtDesigner','PyQt5.QtHelp','PyQt5.QtLocation',
    'PyQt5.QtMultimedia','PyQt5.QtMultimediaWidgets','PyQt5.QtNfc','PyQt5.QtOpenGL','PyQt5.QtPositioning',
    'PyQt5.QtQml','PyQt5.QtQuick','PyQt5.QtQuickWidgets','PyQt5.QtRemoteObjects','PyQt5.QtSensors',
    'PyQt5.QtSerialPort','PyQt5.QtSql','PyQt5.QtTest','PyQt5.QtWebChannel','PyQt5.QtWebEngine',
    'PyQt5.QtWebEngineCore','PyQt5.QtWebEngineWidgets','PyQt5.QtWebSockets','PyQt5.QtXmlPatterns'
)

# ---- 3. PyInstaller 打包 folder 版（含 pyserial 串口 + pyqtgraph 波形图，靠各自 hook 自动收集）----
Write-Host "③ PyInstaller 打包 folder 版（约 1~2 分钟）…"
$pyargs = @('-3','-m','PyInstaller','--noconfirm','--clean','--windowed',
            '--name','CommTool','--icon','assets/icon.ico')
foreach ($e in $excludes) { $pyargs += '--exclude-module'; $pyargs += $e }
$pyargs += 'src/main.py'
& py @pyargs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller(folder) 打包失败" }

# ---- 4. Inno Setup 编译安装包 ----
Write-Host "④ Inno Setup 编译安装包…"
& $Iscc "/DMyAppVersion=$Version" "scripts\CommTool.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC 编译失败" }
if (-not (Test-Path $SetupPath)) { throw "未生成安装包：$SetupPath" }

# ---- 5. PyInstaller 打包 onefile 版（免安装单文件，含 pyqtgraph/numpy）----
#      命令行 --onefile，与 folder 版同一套 Analysis/excludes，输出到 dist_onefile（与 .gitignore 一致）。
Write-Host "⑤ PyInstaller 打包 onefile 版（约 2 分钟）…"
$onef = @('-3','-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
          '--name',"CommTool_v$Version",'--icon','assets/icon.ico',
          '--distpath','dist_onefile','--workpath','build_onefile')
foreach ($e in $excludes) { $onef += '--exclude-module'; $onef += $e }
$onef += 'src/main.py'
& py @onef
if ($LASTEXITCODE -ne 0) { throw "PyInstaller(onefile) 打包失败" }
if (-not (Test-Path $OnefilePath)) { throw "未生成 onefile：$OnefilePath" }

# ---- 6. git 提交 ----
Write-Host "⑥ git 提交…"
git add -A
git commit -m "release: $Tag" -m $Notes | Out-Host

if ($Local) {
    Write-Host "已指定 -Local：跳过 push 和 Release。" -ForegroundColor Yellow
    Write-Host "  安装包 ：$SetupPath"
    Write-Host "  onefile：$OnefilePath"
    return
}

# ---- 7. push 双远程（github 清代理直连、gitee 走 SSH）----
Write-Host "⑦ push 到 github + gitee 的 $Branch…"
git -c http.proxy= -c https.proxy= push github $Branch
if ($LASTEXITCODE -ne 0) { throw "git push github 失败" }
git push gitee $Branch
if ($LASTEXITCODE -ne 0) { throw "git push gitee 失败" }

# ---- 8. GitHub Release（--latest，传 安装包 + onefile）----
Write-Host "⑧ 创建 / 更新 GitHub Release $Tag（含两个 exe）…"
$env:HTTPS_PROXY = ''; $env:HTTP_PROXY = ''
& $Gh release view $Tag --repo $Repo 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "   （Release $Tag 已存在 → 覆盖资产）"
    & $Gh release upload $Tag --repo $Repo --clobber $SetupPath $OnefilePath
} else {
    & $Gh release create $Tag --repo $Repo --target $Branch --title "CommTool $Tag" `
        --notes $Notes --latest $SetupPath $OnefilePath
}
if ($LASTEXITCODE -ne 0) { throw "GitHub Release 操作失败" }

# ---- 9. Gitee Release（国内下载源；走 release_gitee.py，令牌读 scripts/.gitee_token）----
Write-Host "⑨ 发 Gitee Release $Tag（国内下载源 + 在线升级）…"
$env:PYTHONIOENCODING = 'utf-8'
& py -3 (Join-Path $Root 'scripts\release_gitee.py') $Version
if ($LASTEXITCODE -ne 0) { throw "Gitee Release 失败（检查 scripts/.gitee_token 与网络）" }

Write-Host "==== 发版完成 CommTool $Tag ====" -ForegroundColor Green
Write-Host "下载地址（Gitee）：$DownloadUrl"
Write-Host "app「关于 → 检查更新」现在即可检测到 $Version 并升级。"
Write-Host ""
Write-Host "⚠️ 别忘手动同步三语用户文档（脚本不动它们）：" -ForegroundColor Yellow
Write-Host "   docs/USAGE.md · docs/使用说明.md · docs/使用說明.md"
Write-Host "   各加 v$Version 版本历史章节 + 目录条目 + 右下角『当前版本号』。"
Write-Host "macOS .dmg 仍由协作者在 Mac 上跑 release_macos.sh 补到同一 Release。"
