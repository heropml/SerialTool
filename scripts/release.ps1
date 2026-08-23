#Requires -Version 7
<#
.SYNOPSIS
    CommTool 一键发版脚本（Windows 双包 + 双远程 + 双 Release）。

    一条命令完成：改版本号 → 改 latest.json(url 指 Gitee) → 打包(folder 安装包 + onefile) →
    git 提交 → push github + gitee → 建 GitHub Release(--latest) → 发 Gitee Release。
    两个 Release 的正文同用 docs/RELEASE_NOTES.md 全文，标题：CommTool vX.Y.Z。
    app「关于 → 检查更新」随后即可检测到新版本（国内走 Gitee、海外回退 GitHub）。
    macOS .dmg 仍由协作者在 Mac 上跑 release_macos.sh 补到同一 Release。

.PARAMETER Version
    新版本号，格式 X.Y.Z（如 1.1.4）。

.PARAMETER Notes
    本次更新的一句话摘要，写进 latest.json（app 升级弹窗显示）与 git 提交说明。
    建议以可检索定位开头，例如：「串口调试助手 / 网络调试工具：……」。
    注意：Release 正文不用它，而是用 docs/RELEASE_NOTES.md 全文（与 Gitee 同一真源）。

.PARAMETER GithubProxy
    访问 GitHub 用的代理，支持 http:// 与 socks5://（如 http://127.0.0.1:7897）。省略时按
    环境变量 → git config → 本机常见代理端口的顺序自动探测；显式传 none 表示直连。
    Gitee 始终直连，不走代理。

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
    [string]$GithubProxy,
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
& py -3.13 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "发布构建需要 Python 3.13（请安装后确认 py -3.13 可用）"
}
$Tag         = "comm-v$Version"
$SetupName   = "CommTool_Setup_v$Version.exe"
$SetupPath   = Join-Path $Root "installer\$SetupName"
$OnefileName = "CommTool_v$Version.exe"
$OnefilePath = Join-Path $Root "dist_onefile\$OnefileName"
$MacName     = "CommTool_v$Version.dmg"
# 下载源走 Gitee（全球可达；updater 第一源为 Gitee raw latest.json）
$DownloadUrl = "https://gitee.com/$Repo/releases/download/$Tag/$SetupName"
# Windows 发版时 DMG 尚未生成，不能提前发布死链。release_macos.sh 上传并校验
# GitHub 资产后，才会把对应 URL 写回共享清单；同版本重跑 Windows 发布时
# 保留已由 Mac 门禁写入的精确 GitHub URL。
$MacUrls     = @()
$LinuxUrls   = @()
$MacSha256   = ''
$MacSize     = 0
$LinuxSha256 = ''
$LinuxSize   = 0
$VerifiedMacUrl = "https://github.com/heropml/SerialTool/releases/download/$Tag/$MacName"
$LinuxName   = "CommTool_Setup_v${Version}_linux_x86_64.run"
$VerifiedLinuxUrl = "https://github.com/heropml/SerialTool/releases/download/$Tag/$LinuxName"
$ExistingManifest = Join-Path $Root "latest.json"
if (Test-Path $ExistingManifest) {
    try {
        $ExistingLatest = Get-Content $ExistingManifest -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$ExistingLatest.version -eq $Version -and
            @($ExistingLatest.url_mac) -contains $VerifiedMacUrl) {
            $MacUrls = @($VerifiedMacUrl)
            $MacSha256 = [string]$ExistingLatest.sha256_mac
            $MacSize = [long]$ExistingLatest.size_mac
        }
        if ([string]$ExistingLatest.version -eq $Version -and
            @($ExistingLatest.url_linux) -contains $VerifiedLinuxUrl) {
            $LinuxUrls = @($VerifiedLinuxUrl)
            $LinuxSha256 = [string]$ExistingLatest.sha256_linux
            $LinuxSize = [long]$ExistingLatest.size_linux
        }
    } catch {
        Write-Warning "latest.json 无法解析，将按无 Mac/Linux 资产处理：$($_.Exception.Message)"
    }
}

Write-Host "==== 发版 CommTool $Tag ====" -ForegroundColor Cyan

# ---- 工具路径 ----
$Iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) { $Iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $Iscc)) { throw "找不到 Inno Setup 的 ISCC.exe" }
$Gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $Gh) { $Gh = "C:\Program Files\GitHub CLI\gh.exe" }
if (-not (Test-Path $Gh)) { throw "找不到 GitHub CLI(gh)，请先安装并 gh auth login" }

# ---- GitHub 代理（国内直连 github.com 常被阻断；改走本机代理。Gitee 不走代理）----
function Test-LocalPort([int]$Port) {
    $c = [Net.Sockets.TcpClient]::new()
    try   { return $c.ConnectAsync('127.0.0.1', $Port).Wait(300) }
    catch { return $false }
    finally { $c.Dispose() }
}

# 端口连得上不等于协议对得上：10808/1080/7891 惯例是 SOCKS 口，套 http:// 只会握手失败。
# 所以候选表按端口惯例给协议，再用一个真实 HTTPS 请求验一遍，验不过就换下一个候选。
function Test-ProxyReachesGithub([string]$Url) {
    $client = $null
    try {
        $handler = [Net.Http.HttpClientHandler]::new()
        $handler.Proxy = [Net.WebProxy]::new($Url)
        $handler.UseProxy = $true
        $client = [Net.Http.HttpClient]::new($handler)
        $client.Timeout = [TimeSpan]::FromSeconds(8)
        $req = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Head, 'https://github.com/')
        $req.Headers.Add('User-Agent', 'CommTool-release')   # 不带 UA 时 GitHub 一律回 403
        return $client.SendAsync($req).GetAwaiter().GetResult().IsSuccessStatusCode
    } catch { return $false }
    finally { if ($client) { $client.Dispose() } }
}

function Resolve-GithubProxy([string]$Want) {
    if ($Want -eq 'none') { return '' }
    if ($Want) { return $Want }
    foreach ($u in @($env:HTTPS_PROXY, $env:HTTP_PROXY,
                     (git config --get https.proxy), (git config --get http.proxy))) {
        if ($u -and $u.Trim()) { return $u.Trim() }
    }
    $candidates = @(
        @{ Port = 7897;  Scheme = 'http'   }   # Clash Verge 混合口
        @{ Port = 7890;  Scheme = 'http'   }   # Clash 旧混合口
        @{ Port = 10809; Scheme = 'http'   }   # v2rayN HTTP 口
        @{ Port = 10808; Scheme = 'socks5' }   # v2rayN SOCKS 口
        @{ Port = 7891;  Scheme = 'socks5' }   # Clash SOCKS 口
        @{ Port = 1080;  Scheme = 'socks5' }   # 通用 SOCKS 口
    )
    foreach ($c in $candidates) {
        if (-not (Test-LocalPort $c.Port)) { continue }
        $url = '{0}://127.0.0.1:{1}' -f $c.Scheme, $c.Port
        if (Test-ProxyReachesGithub $url) { return $url }
    }
    return ''
}

$GhProxy = if ($Local) { '' } else { Resolve-GithubProxy $GithubProxy }
if (-not $Local) {
    if ($GhProxy) { Write-Host "   GitHub 走代理 $GhProxy（Gitee 直连）" }
    else          { Write-Host "   GitHub 直连：未探测到可用代理，国内可能连不上" -ForegroundColor Yellow }
}

# 只有 gh 和 push github 套代理，跑完还原环境变量，别让 Gitee 上传绕代理。
function Invoke-Gh([string[]]$GhArgs) {
    $oldHttps = $env:HTTPS_PROXY
    $oldHttp  = $env:HTTP_PROXY
    try {
        $env:HTTPS_PROXY = $GhProxy
        $env:HTTP_PROXY  = $GhProxy
        & $Gh @GhArgs
    } finally {
        $env:HTTPS_PROXY = $oldHttps
        $env:HTTP_PROXY  = $oldHttp
    }
}

# ---- 1. 写版本号 ----
Write-Host "① 写入版本号 $Version → src/version.py"
$vp   = Join-Path $Root 'src\version.py'
$vtxt = [IO.File]::ReadAllText($vp)
$vtxt = [regex]::Replace($vtxt, '__version__\s*=\s*"[^"]*"', "__version__ = `"$Version`"")
[IO.File]::WriteAllText($vp, $vtxt)
# 示例工程带 app_version，须与 version.py 同步，否则 CI 字节比对会红
Write-Host "①b 重生 examples/*.ctproj（同步 app_version）"
& py -3.13 (Join-Path $Root 'scripts\build_example_projects.py')
if ($LASTEXITCODE -ne 0) { throw "examples 重生失败" }

# ---- 2. 更新 latest.json（url 指向 Gitee Release）----
Write-Host "② 更新 latest.json → $Version（url 指向 Gitee $Tag）"
$manifest = [ordered]@{
    version = $Version
    url = $DownloadUrl
    url_mac = $MacUrls
    url_linux = $LinuxUrls
    sha256 = ''
    size = 0
    sha256_mac = $MacSha256
    size_mac = $MacSize
    sha256_linux = $LinuxSha256
    size_linux = $LinuxSize
    notes = $Notes
}
$json = $manifest | ConvertTo-Json -Depth 3
# UTF-8 无 BOM：PowerShell 默认 WriteAllText 易写成系统编码，导致 notes 乱码
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText((Join-Path $Root 'latest.json'), $json + "`n", $utf8NoBom)

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
$pyargs = @('-3.13','-m','PyInstaller','--noconfirm','--clean','--windowed',
            '--name','CommTool','--icon','assets/icon.ico')
foreach ($e in $excludes) { $pyargs += '--exclude-module'; $pyargs += $e }
$pyargs += '--collect-all'; $pyargs += 'bleak'
$pyargs += '--add-data'; $pyargs += 'examples;examples'
$pyargs += 'src/main.py'
& py @pyargs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller(folder) 打包失败" }

# ---- 4. Inno Setup 编译安装包 ----
Write-Host "④ Inno Setup 编译安装包…"
& $Iscc "/DMyAppVersion=$Version" "scripts\CommTool.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC 编译失败" }
if (-not (Test-Path $SetupPath)) { throw "未生成安装包：$SetupPath" }
& py -3.13 (Join-Path $Root 'scripts\update_manifest_integrity.py') `
    (Join-Path $Root 'latest.json') $SetupPath windows --version $Version
if ($LASTEXITCODE -ne 0) { throw "latest.json SHA-256 写入失败" }

# ---- 5. PyInstaller 打包 onefile 版（免安装单文件，含 pyqtgraph/numpy）----
#      命令行 --onefile，与 folder 版同一套 Analysis/excludes，输出到 dist_onefile（与 .gitignore 一致）。
Write-Host "⑤ PyInstaller 打包 onefile 版（约 2 分钟）…"
$onef = @('-3.13','-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
          '--name',"CommTool_v$Version",'--icon','assets/icon.ico',
          '--distpath','dist_onefile','--workpath','build_onefile')
foreach ($e in $excludes) { $onef += '--exclude-module'; $onef += $e }
$onef += '--collect-all'; $onef += 'bleak'
$onef += '--add-data'; $onef += 'examples;examples'
$onef += 'src/main.py'
& py @onef
if ($LASTEXITCODE -ne 0) { throw "PyInstaller(onefile) 打包失败" }
if (-not (Test-Path $OnefilePath)) { throw "未生成 onefile：$OnefilePath" }

# ---- 6. git 提交 ----
Write-Host "⑥ git 提交…"
git add -A
# docs/TODO.md 与本地工具残留不进发版提交（见 RELEASE.md §8.1）
git reset -q -- docs/TODO.md 2>$null
# 提交说明统一走一个 UTF-8 文件：标题 + 可选详细正文。
# 不要同时用 -m 与 -F（部分环境下正文会被丢掉，只剩标题一行）。
$CommitTitle = "release: $Tag — $Notes"
$BodyFile = Join-Path $Root 'scripts\_release_commit_body.txt'
$MsgFile  = Join-Path $Root 'scripts\_release_commit_msg.txt'
$msgLines = [System.Collections.Generic.List[string]]::new()
$msgLines.Add($CommitTitle)
if (Test-Path $BodyFile) {
    $body = [IO.File]::ReadAllText($BodyFile).Trim()
    if ($body) {
        $msgLines.Add('')
        $msgLines.Add($body)
    }
    Remove-Item $BodyFile -Force -ErrorAction SilentlyContinue
}
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText($MsgFile, (($msgLines -join "`n") + "`n"), $utf8NoBom)
git commit -F $MsgFile | Out-Host
Remove-Item $MsgFile -Force -ErrorAction SilentlyContinue

if ($Local) {
    Write-Host "已指定 -Local：跳过 push 和 Release。" -ForegroundColor Yellow
    Write-Host "  安装包 ：$SetupPath"
    Write-Host "  onefile：$OnefilePath"
    return
}

# ---- 7. push 双远程（github 走代理、gitee 走 SSH）----
Write-Host "⑦ push 到 github + gitee 的 $Branch…"
git -c http.proxy=$GhProxy -c https.proxy=$GhProxy push github $Branch
if ($LASTEXITCODE -ne 0) {
    throw "git push github 失败（国内直连常被阻断，可显式指定 -GithubProxy http://127.0.0.1:7897 或 socks5://127.0.0.1:10808）"
}
git push gitee $Branch
if ($LASTEXITCODE -ne 0) { throw "git push gitee 失败" }

# ---- 8. GitHub Release（--latest，传 安装包 + onefile）----
#      文案沿用 v1.3.5 / v1.3.6 已发布的约定：标题 CommTool vX.Y.Z，正文用 docs/RELEASE_NOTES.md
#      全文（与 Gitee 同一真源），不是 $Notes 那句摘要，否则 Release 页上只剩一行字。
Write-Host "⑧ 创建 / 更新 GitHub Release $Tag（含两个 exe）…"
$NotesFile = Join-Path $Root 'docs\RELEASE_NOTES.md'
if (-not (Test-Path $NotesFile)) { throw "缺少 docs/RELEASE_NOTES.md，无法生成 Release 正文" }
if ([IO.File]::ReadAllText($NotesFile) -notlike "*$Version*") {
    throw "docs/RELEASE_NOTES.md 里没出现 $Version，像是上一版的旧文案，先更新再发"
}
$RelTitle = "CommTool v$Version"
Invoke-Gh @('release', 'view', $Tag, '--repo', $Repo) 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "   （Release $Tag 已存在 → 同步标题/正文 + 覆盖资产）"
    Invoke-Gh @('release', 'edit', $Tag, '--repo', $Repo,
                '--title', $RelTitle, '--notes-file', $NotesFile)
    if ($LASTEXITCODE -ne 0) { throw "GitHub Release 文案更新失败" }
    Invoke-Gh @('release', 'upload', $Tag, '--repo', $Repo, '--clobber',
                $SetupPath, $OnefilePath)
} else {
    Invoke-Gh @('release', 'create', $Tag, '--repo', $Repo, '--target', $Branch,
                '--title', $RelTitle, '--notes-file', $NotesFile, '--latest',
                $SetupPath, $OnefilePath)
}
if ($LASTEXITCODE -ne 0) { throw "GitHub Release 操作失败" }

# ---- 9. Gitee Release（国内下载源；走 release_gitee.py，令牌读 scripts/.gitee_token）----
Write-Host "⑨ 发 Gitee Release $Tag（国内下载源 + 在线升级）…"
$env:PYTHONIOENCODING = 'utf-8'
$env:HTTPS_PROXY = ''; $env:HTTP_PROXY = ''; $env:ALL_PROXY = ''   # Gitee 直连，别绕代理
& py -3.13 (Join-Path $Root 'scripts\release_gitee.py') $Version
if ($LASTEXITCODE -ne 0) { throw "Gitee Release 失败（检查 scripts/.gitee_token 与网络）" }

Write-Host "==== 发版完成 CommTool $Tag ====" -ForegroundColor Green
Write-Host "下载地址（Gitee）：$DownloadUrl"
Write-Host "app「关于 → 检查更新」现在即可检测到 $Version 并升级。"
Write-Host ""
Write-Host "⚠️ 别忘手动同步三语用户文档（脚本不动它们）：" -ForegroundColor Yellow
Write-Host "   docs/USAGE.md · docs/使用说明.md · docs/使用說明.md"
Write-Host "   各加 v$Version 版本历史章节 + 目录条目 + 右下角『当前版本号』。"
Write-Host "macOS .dmg 仍由协作者在 Mac 上跑 release_macos.sh 补到同一 Release。"
