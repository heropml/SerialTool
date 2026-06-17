#Requires -Version 7
<#
.SYNOPSIS
    NetworkTool（网络版）一键发版脚本。

    一条命令完成：改版本号 → 改 latest.json → 打包(folder + 安装包) →
    git 提交 → push 到 GitHub 的 NetworkTool 分支 → 建 Release 并上传安装包。
    app 的「关于 → 检查更新」随后即可检测到新版本并升级。

.PARAMETER Version
    新版本号，格式 X.Y.Z（如 1.0.5）。

.PARAMETER Notes
    本次更新说明，会写进 latest.json 和 Release 说明。

.PARAMETER Local
    只本地打包 + 提交，跳过 push 和 GitHub Release（用于试打包）。

.EXAMPLE
    .\scripts\release.ps1 1.0.5 "修复若干问题"

.NOTES
    依赖：Python(py) + PyInstaller、Inno Setup 6、GitHub CLI(gh，需已 gh auth login)。
    NetworkTool 与串口版 SerialTool 共用同一个 GitHub 仓库，所以 Release tag 用
    「net-v 前缀」区分（net-v1.0.5），避免和串口版的 v1.0.x tag 冲突。
    版本清单 latest.json 在 NetworkTool 分支，更新源也指向 NetworkTool 分支。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)][string]$Version,
    [Parameter(Mandatory, Position = 1)][string]$Notes,
    [switch]$Local
)

$ErrorActionPreference = 'Stop'
$Repo   = 'heropml/SerialTool'
$Branch = 'NetworkTool'

# ---- 0. 定位项目根 + 校验 ----
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "版本号格式应为 X.Y.Z（如 1.0.5），你给的是 '$Version'"
}
$Tag         = "net-v$Version"                          # Release tag，net- 前缀区分串口版
$SetupName   = "NetworkTool_Setup_v$Version.exe"
$SetupPath   = Join-Path $Root "installer\$SetupName"
$DownloadUrl = "https://github.com/$Repo/releases/download/$Tag/$SetupName"
# 内网 GitLab Release 永久链接（发版时把同名安装包传到内网 GitLab 的 Release $Tag，
# 加 link 时 Direct asset path 设为 /$SetupName，即可用此固定地址下载）
$IntranetUrl = "http://192.168.50.40/pengml/SerialTool/-/releases/$Tag/downloads/$SetupName"

Write-Host "==== 发版 NetworkTool $Tag ====" -ForegroundColor Cyan

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

# ---- 2. 更新 latest.json ----
Write-Host "② 更新 latest.json → $Version（url 指向 Release $Tag）"
$manifest = [ordered]@{ version = $Version; url = $DownloadUrl; url_intranet = $IntranetUrl; notes = $Notes }
$json = $manifest | ConvertTo-Json -Depth 3
[IO.File]::WriteAllText((Join-Path $Root 'latest.json'), $json)

# ---- 3. PyInstaller 打包 folder 版（网络版无需 pyserial）----
Write-Host "③ PyInstaller 打包 folder 版（约 1 分钟）…"
$excludes = @(
    'PyQt5.QtBluetooth','PyQt5.QtDBus','PyQt5.QtDesigner','PyQt5.QtHelp','PyQt5.QtLocation',
    'PyQt5.QtMultimedia','PyQt5.QtMultimediaWidgets','PyQt5.QtNfc','PyQt5.QtOpenGL','PyQt5.QtPositioning',
    'PyQt5.QtQml','PyQt5.QtQuick','PyQt5.QtQuickWidgets','PyQt5.QtRemoteObjects','PyQt5.QtSensors',
    'PyQt5.QtSerialPort','PyQt5.QtSql','PyQt5.QtTest','PyQt5.QtWebChannel','PyQt5.QtWebEngine',
    'PyQt5.QtWebEngineCore','PyQt5.QtWebEngineWidgets','PyQt5.QtWebSockets','PyQt5.QtXmlPatterns'
)
$pyargs = @('-3','-m','PyInstaller','--noconfirm','--clean','--windowed',
            '--name','NetworkTool','--icon','assets/icon.ico')
foreach ($e in $excludes) { $pyargs += '--exclude-module'; $pyargs += $e }
$pyargs += 'src/main.py'
& py @pyargs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }

# ---- 4. Inno Setup 编译安装包 ----
Write-Host "④ Inno Setup 编译安装包…"
& $Iscc "/DMyAppVersion=$Version" "scripts\NetworkTool.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC 编译失败" }
if (-not (Test-Path $SetupPath)) { throw "未生成安装包：$SetupPath" }

# ---- 5. git 提交 ----
Write-Host "⑤ git 提交…"
git add -A
git commit -m "release: $Tag" -m $Notes | Out-Host
if ($LASTEXITCODE -ne 0) { Write-Warning "git commit 失败或无改动，继续" }

if ($Local) {
    Write-Host "已指定 -Local：跳过 push 和 Release。安装包在：$SetupPath" -ForegroundColor Yellow
    return
}

# ---- 6. push NetworkTool 分支 ----
Write-Host "⑥ push 到 github/$Branch（让 latest.json 上线）…"
git push github $Branch
if ($LASTEXITCODE -ne 0) { throw "git push 失败" }

# ---- 7. 建 Release 并上传安装包（tag 已存在则覆盖资产）----
Write-Host "⑦ 创建 / 更新 GitHub Release $Tag 并上传安装包…"
& $Gh release view $Tag --repo $Repo 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "   （Release $Tag 已存在 → 覆盖安装包资产）"
    & $Gh release upload $Tag --repo $Repo --clobber $SetupPath
} else {
    # --latest=false：网络版与串口版共用同一仓库，Release 不能抢走主产品 SerialTool 的
    # 「Latest」标记（gh 默认会把最后创建的 release 设为 latest，这里显式关掉）。
    & $Gh release create $Tag --repo $Repo --target $Branch --title "NetworkTool $Tag" --notes $Notes --latest=false $SetupPath
}
if ($LASTEXITCODE -ne 0) { throw "GitHub Release 操作失败" }

Write-Host "==== 发版完成 NetworkTool $Tag ====" -ForegroundColor Green
Write-Host "下载地址(外网)：$DownloadUrl"
Write-Host "下载地址(内网)：$IntranetUrl"
Write-Host "⚠ 内网用户要能自动更新，需两步：" -ForegroundColor Yellow
Write-Host "   1) 把 installer\$SetupName 上传到内网 GitLab 的 Release $Tag（发布资产 → 添加链接）"
Write-Host "   2) 有「直接资产路径」就填 /$SetupName（上面内网地址即可用）；没有该字段，则把上传后的真实"
Write-Host "      地址（…/uploads/<hash>/$SetupName）填进 latest.json 的 url_intranet，再 push 内网"
Write-Host "app「关于 → 检查更新」现在即可检测到 $Version 并升级。"
