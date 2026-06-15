; Inno Setup 脚本 — NetworkTool 安装程序
; 用法：
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" NetworkTool.iss
;   或 双击 .iss 用 Inno Setup IDE 打开 → Build → Compile

#define MyAppName "NetworkTool"
#define MyAppNameCN "网络调试工具"
; MyAppVersion 优先从命令行 /DMyAppVersion=x.y.z 传入；否则用此默认值
; build_installer.bat 会自动从 version.py 读出来传过来，保持与 main.py 同步
#ifndef MyAppVersion
#  define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "MG_Project"
#define MyAppExeName "NetworkTool.exe"
; 路径相对本 .iss 所在目录(scripts\)，用 ..\ 指回项目根
#define MyAppSourceDir "..\dist\NetworkTool"

[Setup]
; 安装程序基本信息
; AppId 是 NetworkTool 自己的独立身份(与串口版 SerialTool 不同的 GUID)，
; 这样默认装到 {autopf}\NetworkTool、独立卸载项，不会被当成 SerialTool 的升级而沿用旧目录
AppId={{F9742F8B-9C46-44ED-AB28-A5FB1035953E}
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
OutputDir=..\installer
OutputBaseFilename=NetworkTool_Setup_v{#MyAppVersion}

; 压缩
Compression=lzma2/ultra
SolidCompression=yes

; 图标
SetupIconFile=..\assets\icon.ico
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
; 把整个 dist\NetworkTool 目录搬进 {app}
Source: "{#MyAppSourceDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyAppSourceDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; 用户向使用说明 — 按安装语言条件装对应文档
; english     → USAGE.md
; chinesesimp → 使用说明.md
; chinesetrad → 使用說明.md
Source: "..\docs\USAGE.md"; DestDir: "{app}"; Flags: ignoreversion isreadme; Languages: english
Source: "..\docs\使用说明.md"; DestDir: "{app}"; Flags: ignoreversion isreadme; Languages: chinesesimp
Source: "..\docs\使用說明.md"; DestDir: "{app}"; Flags: ignoreversion isreadme; Languages: chinesetrad
; 三份文档都引用的预览图
Source: "..\assets\icon_preview.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; 开始菜单
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; 桌面快捷方式（可选）
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[INI]
; 首次安装时根据安装语言 seed settings.ini，让 NetworkTool 第一次启动就用对应语言
; - 写两份（{app} 和 {userappdata}\NetworkTool）兼容两种 settings 落地路径：
;   per-user 装 → 走 {app}；all-users 装到 Program Files + 非管理员运行 → 走 %APPDATA% fallback
; - 用 Check 函数确保只在文件还不存在时 seed，不覆盖已有用户配置
Filename: "{app}\settings.ini";                    Section: "General"; Key: "language"; String: "en";    Languages: english;     Check: ShouldSeedApp
Filename: "{app}\settings.ini";                    Section: "General"; Key: "language"; String: "zh";    Languages: chinesesimp; Check: ShouldSeedApp
Filename: "{app}\settings.ini";                    Section: "General"; Key: "language"; String: "zh_tw"; Languages: chinesetrad; Check: ShouldSeedApp
Filename: "{userappdata}\NetworkTool\settings.ini"; Section: "General"; Key: "language"; String: "en";    Languages: english;     Check: ShouldSeedAppData
Filename: "{userappdata}\NetworkTool\settings.ini"; Section: "General"; Key: "language"; String: "zh";    Languages: chinesesimp; Check: ShouldSeedAppData
Filename: "{userappdata}\NetworkTool\settings.ini"; Section: "General"; Key: "language"; String: "zh_tw"; Languages: chinesetrad; Check: ShouldSeedAppData

[Code]
function ShouldSeedApp: Boolean;
begin
  // 只在 {app}\settings.ini 不存在时 seed —— 升级安装保留用户旧偏好
  Result := not FileExists(ExpandConstant('{app}\settings.ini'));
end;

function ShouldSeedAppData: Boolean;
begin
  Result := not FileExists(ExpandConstant('{userappdata}\NetworkTool\settings.ini'));
end;

[Run]
; 安装完成后可选立即启动
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
