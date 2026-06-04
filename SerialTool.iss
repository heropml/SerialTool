; Inno Setup 脚本 — SerialTool 安装程序
; 用法：
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" SerialTool.iss
;   或 双击 .iss 用 Inno Setup IDE 打开 → Build → Compile

#define MyAppName "SerialTool"
#define MyAppNameCN "串口工具"
; MyAppVersion 优先从命令行 /DMyAppVersion=x.y.z 传入；否则用此默认值
; build_installer.bat 会自动从 version.py 读出来传过来，保持与 main.py 同步
#ifndef MyAppVersion
#  define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "MG_Project"
#define MyAppExeName "SerialTool.exe"
#define MyAppSourceDir "dist\SerialTool"

[Setup]
; 安装程序基本信息
AppId={{8F6A7C90-2B41-4E7D-A1D2-9F4E3B8A5C12}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=no
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}

; 输出目录和文件名
OutputDir=installer
OutputBaseFilename=SerialTool_Setup_v{#MyAppVersion}

; 压缩
Compression=lzma2/ultra
SolidCompression=yes

; 图标
SetupIconFile=icon.ico
WizardStyle=modern

; 仅 64 位 Windows
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; 权限策略：默认不需要管理员（per-user 安装到 %LocalAppData%）
; OverridesAllowed=dialog → 用户可主动切到 "Install for all users" 自动提权装到 Program Files
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; 显式声明路径页可选+可浏览（其实是默认行为，这里写出来更直白）
DisableDirPage=no
AllowNoIcons=yes
UsePreviousAppDir=yes

[Languages]
; 启动时弹下拉让用户选语言。Inno Setup 官方不带中文翻译，
; ChineseSimplified.isl / ChineseTraditional.isl 是社区维护的，
; 已经下载到 Inno Setup 安装目录\Languages\ 下了
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "chinesetrad"; MessagesFile: "compiler:Languages\ChineseTraditional.isl"

[Tasks]
; 用 {cm:CreateDesktopIcon} 自动套各语言内置翻译，不用手写三套
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; 把整个 dist\SerialTool 目录搬进 {app}
Source: "{#MyAppSourceDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyAppSourceDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; 用户向使用说明（区别于源码仓库里的 README.md 开发文档）
Source: "使用说明.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
; 使用说明里引用的图，少了它 Typora 显示破图
Source: "icon_preview.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; 开始菜单
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; 桌面快捷方式（可选）
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; 安装完成后可选立即启动
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
