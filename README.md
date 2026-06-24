# CommTool

iOS 风格的串口 / 网络一体调试工具，基于 PyQt5。串口（pyserial）与 TCP / UDP（QtNetwork）共用同一套数据区 / 发送 / 高亮 / 日志，「类型」下拉一键切换。支持 串口 / UDP / UDP 组播 / TCP Server / TCP Client 五种连接、中英文动态切换、无边框窗口 + 自绘标题栏、QSplitter 可拖拽布局、Xshell 风格日志、10 种校验算法、关闭确认 + 系统托盘、在线更新（关于 → 检查更新）、图标固化在源码内（防替换）。

> 本分支（CommTool）由串口版 SerialTool 与网络版 NetworkTool 合并而来：左上角连接区的「类型」下拉统一了 **串口 + 网络**（串口走 `serial_io.SerialConn`、网络走 `net_io`，对外同一套 `open()/close()/send()/is_open` + 信号接口）；数据区/发送/高亮/日志/多条发送/主题/语言等其余功能两版共用。产品（窗口标题、Python 类、打包产物 exe/安装包/`dist` 目录、`%APPDATA%` 配置目录）统一命名为 **CommTool / 通信调试工具**。

![iOS 风格 UI](./assets/icon_preview.png)

---

## 目录

- **1. [功能总览](#1-功能总览)**
  - 1.1 [连接设置（串口 / 网络）](#11-连接设置串口--网络)
  - 1.2 [数据区](#12-数据区接收--发送日志)
  - 1.3 [发送区](#13-发送区)
  - 1.4 [界面](#14-界面)
  - 1.5 [关闭程序 + 系统托盘](#15-关闭程序--系统托盘)
  - 1.6 [图标固化](#16-图标固化防替换)
  - 1.7 [持久化](#17-持久化)
  - 1.8 [在线更新](#18-在线更新)
- **2. [三种使用方式](#2-三种使用方式)**
  - 2.1 [独立 exe](#21-独立-exe推荐无需-python)
  - 2.2 [静默启动源码版](#22-静默启动源码版已装-python)
  - 2.3 [调试启动源码版](#23-调试启动源码版看-python-报错)
- **3. [文件结构](#3-文件结构)**
- **4. [从源码运行](#4-从源码运行)**
- **5. [重新打包](#5-重新打包)**
  - 5.1 [文件夹版](#51-文件夹版基础给其他两个当输入)
  - 5.2 [单文件版 (onefile)](#52-单文件版onefile)
  - 5.3 [安装版 (Inno Setup)](#53-安装版inno-setup)
  - 5.4 [Linux 版](#54-linux-版)
  - 5.5 [改版本号](#55-改版本号)
- **6. [换图标](#6-换图标)**
- **7. [依赖](#7-依赖)**
- **8. [已知问题与注意事项](#8-已知问题与注意事项)**
- **9. [技术说明](#9-技术说明)**
  - 9.1 [iOS 滑动开关](#91-ios-滑动开关)
  - 9.2 [网络连接层](#92-网络连接层)
  - 9.3 [编码兼容](#93-编码兼容)
  - 9.4 [时间戳分包 / 换行分包 逻辑](#94-时间戳分包与换行分包的或逻辑)
  - 9.5 [跨包"待新块"标志](#95-跨包待新块标志)
  - 9.6 [自定义标题栏 + Aero Snap](#96-自定义标题栏--aero-snap)
  - 9.7 [QSettings 持久化](#97-qsettings-持久化)
  - 9.8 [主题系统](#98-主题系统)
  - 9.9 [字符编码](#99-字符编码)
  - 9.10 [CRC 算法实现](#910-crc-算法实现)
  - 9.11 [HEX 输入宽容化](#911-hex-输入宽容化)
- **10. [版本历史亮点](#10-版本历史亮点)**

---

## 1. 功能总览

### 1.1 连接设置（串口 / 网络）

- **类型**下拉：**Serial（串口）/ UDP / UDP Multicast（组播）/ TCP Server / TCP Client**（新装默认 Serial）
- **串口（Serial）**：端口（下拉本机串口 + ⟳ 刷新）+ 波特率（可编辑，1200~2000000）+ 数据位（5/6/7/8）+ 校验位（None/Even/Odd/Mark/Space）+ 停止位（1/1.5/2）→「打开串口」；后台线程定时扫描串口热插拔
- 网络类型字段随协议动态显隐：
  - **UDP**：本地IP（下拉本机网卡，0.0.0.0=所有）+ 本地端口 +「指定远程」开关（关=回复最近对端，开=固定发往远程IP/端口）；关闭时收到数据自动把灰显的远程框刷成最近对端地址（显示当前对端，打开开关即预填）
  - **UDP Multicast**：本地IP（出/入网卡）+ 组播地址（224.0.0.0~239.255.255.255）+ 本地端口
  - **TCP Server**：本地IP + 本地端口 →「开始监听」；连入后「目标」下拉可选某客户端或「全部」广播
  - **TCP Client**：远程IP + 远程端口 →「连接」
- 动作按钮随协议/状态：打开/关闭、开始监听/停止监听、连接/断开；连接后整卡片锁定变灰
- 基于 Qt 自带 **QtNetwork**（QTcpServer/QTcpSocket/QUdpSocket），事件驱动、无轮询线程

### 1.2 数据区（接收 + 发送日志）

收发数据**同框显示**，箭头区分方向、颜色区分类型：

| 标记 | 含义 | 颜色 |
|------|------|------|
| `←` | RX 接收 | 灰黑（`#1C1C1E`）|
| `→` | TX 发送 | iOS 蓝（`#007AFF`）|

**显示选项**（侧边栏 → 数据区）

- **HEX 显示** — 把字节渲染成 `AA BB CC ...`，否则按文本
- **字符编码** — Auto / UTF-8 / GBK / GB2312 / GB18030 / Big5 / ASCII / Latin-1 共 8 项；Auto 走 UTF-8 优先 + GBK 容错回退，其他用 `codecs.IncrementalDecoder` 处理跨包多字节。影响 RX 解码 / TX 文本编码 / 文件加载
- **自动换行** — 控制 `QTextEdit` 的 WordWrap 模式
- **显示时间戳** — 每个新块前缀 `[2026/06/03 09:48:54 023]`（年月日补零，毫秒 3 位），**独立开关**
- **时间分包** + **超时 ms** — 两次 RX 到达间隔 > 超时则切包另起一行，**独立开关**（"显示时间戳"和"时间分包"各管各的）
- **换行分包** + **换行符模式（Auto / CRLF / LF / CR）** — 按文本换行符切包
  - `Auto`：`\r\n`、`\r`、`\n` 全识别（Windows + Linux + Classic Mac 都兼容）
  - 严格模式：只认指定终止符，其他换行符按数据字节看待
- **实时记录** — Xshell 风格连续日志写到 `.log` 文件，**显示什么写什么**（带时间戳、箭头、HEX/ASCII），会话开头/结尾自动加分隔行
- **最大行数** — 显示行上限，超出自动丢弃最老的行，避免长时间运行卡顿；**不影响日志文件**
- 字号 `A−` `A+` 可调（7–28 pt 范围）
- 保存 / 清空按钮
- **滚动锁定 / 自动跟随**（v1.0.1）— 往上翻时视图定住、数据照常接收；右下角浮动「↓ 最新」按钮回到底部并恢复自动跟随
- **单击行高亮**（v1.0.1）— 鼠标单击数据区某一行整行高亮，再点取消
- **关键字高亮**（v1.0.1）— 标题栏「关键字高亮」按钮打开配置弹窗：多条关键字，每条独立颜色、可选「背景 / 文字」着色、可限定「收 / 发 / 收发」范围；**区分大小写**子串匹配、**跳过时间戳**、规则持久化
- **只显高亮行**（v1.0.1，v1.0.2 移到数据区标题栏）— 标题栏「只显高亮行」可切换按钮（开启时高亮），只保留命中关键字的行（其余折叠隐藏，数据不丢）
- 显示格式（HEX / 文本）**只由「HEX 显示」开关决定**，收发一致（与「HEX 发送」无关）
- **关键字高亮分组**（v1.0.2）— 弹窗左侧分组列表（新建/双击改名/删除）；标题栏分组下拉选「哪个分组生效」（含「（关闭）」停用全部）；编辑分组与生效分组**相互独立**
- **实时记录按大小分包**（v1.0.2）— 实时记录开关旁下拉：不分包 / 1M~100M / 自定义（如 3M）；写满自动切到 `_001`/`_002` 新文件；当前日志路径显示在底部状态栏
- **中文右键菜单**（v1.0.2）— 数据区右键 复制 / 全选 / 清空 / 保存，**跟随程序语言**（非系统语言的 Qt 默认菜单）

### 1.3 发送区

**发送选项**（侧边栏 → 发送区）

- **HEX 发送** — 把输入框内容当 HEX 字符解析（`AA BB`、`AABB`、`AA-BB`、`AA:BB`、`AA,BB`、带 `0x` 前缀等都接受）
- **追加换行** + **换行符模式（CRLF / LF / CR）** — 自动在尾部追加对应字节，下拉框默认 CRLF
- **定时发送** + **周期 ms** — 最小 10ms，发送失败时（未连接 / 数据格式错误 / 无目标等）自动停止
- **追加校验**（10 种）

| 算法 | 长度 | 说明 |
|------|------|------|
| 无 / None | 0 | 不追加 |
| 和校验 / ADD8 | 1 | `sum & 0xFF` |
| 累加和取反 / ~ADD8 | 1 | `(~sum) & 0xFF` |
| 异或 / XOR8 | 1 | 全字节异或 |
| CRC8 | 1 | 多项式 `0x07`（标准 CRC-8/CCITT）|
| ModbusCRC16 | 2 | poly `0xA001`, init `0xFFFF`, **小端**（Modbus RTU 标准）|
| CCITT-CRC16 | 2 | CRC-16/CCITT-FALSE: poly `0x1021`, init `0xFFFF`, 大端 |
| CRC32 | 4 | Ethernet / ZIP 标准（`zlib.crc32`），大端 |
| ADD16 | 2 | 16 位累加和，大端 |
| **MOBUS** | **1** | **CRC8 with poly `0x31`** — 对应国内嵌入式社区常见 `MG_Crc8Check` / `crc8_ccitt` 实现 |

**操作**

- 读取文件 → 把文件内容塞进发送框（HEX 模式自动转 hex 字符串）
- 清空发送框
- 发送按钮 + 状态栏 **收发速率 / 包统计**（v1.1.0）— 底部状态栏 RX/TX 显示「字节 · 包数 · 实时速率(B/s)」，悬停看完整明细（含峰值速率、错误数），右键「重置统计」清零
- **多条发送**（v1.0.1）— 「多条发送」按钮打开弹窗：每行一条数据 + 复选框，**每行可独立设 HEX / 换行 / 校验**；条目持久化
- **多条发送分组 + 主界面快捷栏**（v1.0.2）— 弹窗左侧分组列表 + 每行加「名称 / 延时(ms)」；发送区上方快捷栏 `[多条发送][▶循环][分组下拉] + 命令平铺按钮`，**点按钮直接发**、不用开弹窗；循环发送**按每行各自延时**依次轮发

### 1.4 界面

- **无边框窗口 + 自绘标题栏**：图标 + 标题 + 语言下拉 + 主题下拉 + 最小化/最大化/关闭按钮全在标题栏一行
  - 语言 + 主题下拉都在标题栏**左侧**（紧挨标题）
  - 拖标题栏移动窗口、双击切换最大化
  - 边缘缩放走 Windows 原生 `WM_NCHITTEST`，手感和系统窗口完全一致（Aero Snap 拖边贴屏也照常工作）
- **iOS 风格控件**
  - 圆角卡片 + 柔和投影（`QGraphicsDropShadowEffect`）
  - 自绘 `IOSSwitch` 滑动开关，带缓动动画
  - 主按钮 / 幽灵按钮 / 图标按钮三套样式
  - 默认 Accent `#007AFF` iOS 蓝、`#34C759` 绿、`#FF3B30` 红（其他主题各自有自己的 accent / danger）
- **左侧 sidebar + 右侧数据区**
  - 左：连接设置 / 数据区设置 / 发送区设置 三张卡片，`QGridLayout` 让所有右侧控件右对齐
  - 右：数据日志区 + 发送输入框（垂直可拖）
  - 左右用 `QSplitter` 分隔，宽度可调（侧边栏 240–360 px）
- **状态栏**
  - 左下：状态点（红 = 未连接 / 绿 = 已连接·监听·已绑定）+ 连接状态文本（串口 `● COM3 @ 115200`；网络 `● TCP 监听 / ● 已连接 / ● UDP / ● 组播 地址:端口`）+ RX/TX 收发统计（字节 · 包数 · 实时速率，详见 v1.1.0）
  - 右下：版本号 `v1.1.2`（从 `version.py` 同步），左侧显示当前实时记录文件路径（📝）
- **多语言切换**：标题栏左上下拉（**简体中文 / English / 繁體中文**），**无需重启**，所有 UI 文字（标签、按钮、占位提示、错误消息、文件对话框）瞬间切换
- **主题切换**：标题栏左上紧挨语言的第二个下拉，**9 个终端风配色方案**：

  | 主题 | mode | 风格 |
  |---|---|---|
  | Default | light | iOS 默认（白卡片 + 浅灰窗口）|
  | Dark | dark | VSCode 通用暗 |
  | One Half Light / Dark | light/dark | Atom 编辑器风 |
  | Solarized Light / Dark | light/dark | 经典 Solarized |
  | Tango Dark | dark | Linux Tango 灰 |
  | Campbell | dark | Windows Terminal 默认黑 |
  | Ubuntu | dark | Ubuntu 紫 |

  主题驱动**整体配色**：窗口背景 / 卡片 / 按钮 / 输入框 / 数据区 / 状态栏 / 关闭对话框全部跟着切。算法上每个主题只定义 4 个核心色（`bg` / `fg` / `tx` / `ts`）+ `mode`，`chrome_for()` 用 `_mix()` 派生出 19 个 chrome 色（card_bg / input_bg / ghost / scrollbar / 等）。

### 1.5 关闭程序 + 系统托盘

点窗口右上 `×` 弹出三选一对话框：

| 选项 | 行为 |
|------|------|
| 最小化到托盘（默认）| `hide()` 隐藏窗口，托盘弹气泡通知 |
| 退出程序 | 真退出 — 存配置 + 断开连接 + 关日志 |
| 取消 | 关闭事件被吃掉，窗口保留 |

**系统托盘图标**（任务栏右下角通知区）：
- 单击 / 双击 → 恢复窗口
- 右键菜单 → "显示窗口" / "退出"
- 切换中英文时托盘菜单文字同步
- 系统不支持托盘时，`×` 直接退出（不弹对话框）

### 1.6 图标固化（防替换）

128×128 PNG 图标用 **base64 编码写死在独立的 `icon_data.py` 文件**里（`ICON_B64` 常量），`main.py` 通过 `from icon_data import ICON_B64 as _APP_ICON_B64` 导入，运行时由 `get_app_icon()` 解码加载。带来的好处：

- 别人**没法通过替换 `icon.ico`** 来改窗口/任务栏/托盘里显示的图标
- 打包出的 `dist\CommTool\_internal\` 里**完全没有 `icon.ico` 文件**
- 资源管理器里 exe 文件的图标仍然来自 PyInstaller 的 `--icon` 嵌入资源（这是 Windows 资源段，跟运行时图标分开）

### 1.7 持久化

启动时自动从 `settings.ini` 恢复，关闭时自动保存：

- 窗口位置 + 大小（含最大化状态）
- 两个 splitter 的精确位置
- 当前语言（中文 / 英文）
- 所有开关 / 输入框 / 下拉选项
- 发送框内容
- 字号、最大行数

**位置**：`CommTool.exe` 同级目录的 `settings.ini`，整个 `dist\CommTool\` 文件夹可以连配置一起复制到其他机器。

### 1.8 在线更新

**关于 → 检查更新**（v1.0.4）：系统托盘右键菜单新增「关于」入口，打开对话框显示图标 / 名称 / 版本 / 简介 + 「检查更新」按钮。

- 点「检查更新」自动从更新源读取版本清单（`latest.json`），与当前版本比对
  - **有新版** → 显示版本号 + 更新说明 + 「下载并更新」→ 下载（带进度）→ 下载完弹出**正常安装向导**，手动点「下一步 / 安装」完成升级（非静默）
  - **已是最新** → 提示当前已是最新版本
- 更新源**内网优先、回退公网**（GitHub 上 CommTool 分支的 `latest.json`），每个源 8 秒超时（外网不卡）
- 下载后校验文件头魔数（`MZ`）防错误页误执行；关闭对话框 / ESC 自动中止在途下载并删半成品；启动时清理 `%TEMP%` 残留安装包；版本号解析容错
- 网络类型基于 Qt 自带 **QtNetwork**（CommTool 网络侧本就用 QtNetwork），无新依赖；更新源地址在 `src/updater.py` 的 `UPDATE_MANIFEST_URLS` 配置，版本清单格式见根目录 `latest.json`

---

## 2. 三种使用方式

### 2.1 独立 exe（推荐，无需 Python）

```
dist\CommTool\CommTool.exe
```

整个 `dist\CommTool\` 文件夹（约 98 MB）可以复制到任意 Windows 10/11 64 位电脑直接运行，**目标机器无需安装 Python、PyQt5**。

### 2.2 静默启动源码版（已装 Python）

双击 `scripts\run.vbs` — 完全无窗口启动（优先 `pyw src\main.py`，回退 `pythonw src\main.py`），没有 cmd 闪屏。

### 2.3 调试启动源码版（看 Python 报错）

双击 `scripts\run_debug.bat` — 保留 cmd 窗口，能看到 Python 异常输出，方便排查问题。

---

## 3. 文件结构

> 代码已按模块拆分，并把源码 / 文档 / 脚本 / 资源分类到子目录。所有脚本内部用 `cd %~dp0..`（或 `dirname/..`）切回项目根再执行，双击即用，无需手动 cd。

```
CommTool/
├── README.md               开发者文档（本文件，留在根目录）
├── requirements.txt        Python 依赖
├── latest.json             在线更新版本清单（version / url / notes）
│
├── src/                    Python 源码（按模块拆分）
│   ├── main.py             入口：HiDPI + QApplication + 启动 CommTool
│   ├── main_window.py      主窗口 CommTool 主体类（最大模块）
│   ├── dialogs.py          多条发送 / 关键字高亮 / 关闭确认 弹窗
│   ├── widgets.py          自定义控件（IOSSwitch / TitleBar / Card）
│   ├── serial_io.py        串口连接层（SerialConn + SerialReader 读线程 + 端口扫描）
│   ├── net_io.py           网络连接层（TCP Server/Client、UDP、UDP 组播）
│   ├── theme.py            主题配色表 + 角色着色（ROLE_*）
│   ├── i18n.py             三语翻译表（简 / 英 / 繁）
│   ├── app_icon.py         运行时图标加载（resource_path / get_app_icon）
│   ├── icon_data.py        128×128 PNG base64（运行时图标，~545 行）
│   ├── updater.py          在线更新（QtNetwork 检查/下载 + 跑安装向导）
│   └── version.py          版本号单点真源 (__version__ = "1.1.2")
│
├── docs/                   文档
│   ├── USAGE.md            用户文档（英文，安装包附带）
│   ├── 使用说明.md          用户文档（简体）
│   ├── 使用說明.md          用户文档（繁体）
│   └── RELEASE_NOTES.md    版本发布说明
│
├── scripts/                构建 / 启动脚本（内部 cd 回根目录）
│   ├── run.vbs             静默启动（推荐日常用）
│   ├── run.bat             快速启动（cmd 一闪而过）
│   ├── run_debug.bat       调试启动（保留 cmd 看错误）
│   ├── build.bat           打包文件夹版 exe（py -3 -m PyInstaller）
│   ├── build_onefile.bat   打包单文件版 exe（文件名带版本号）
│   ├── build.sh            Linux 打包脚本（venv + 国内镜像）
│   ├── build_installer.bat 编译 Inno Setup 安装包（自动从 version.py 取版本号）
│   ├── release.ps1         一键发版（改版本→改 latest.json→打包→push→建 Release）
│   └── CommTool.iss      Inno Setup 脚本（多语言 EN/简/繁，路径可选）
│
├── assets/                 图标资源
│   ├── icon.ico            多分辨率 ICO（16/32/48/64/128/256 px，透明背景）
│   ├── icon_preview.png    256×256 PNG 预览（icon_convert.py 输出的副产品）
│   └── icon_convert.py     一次性脚本：JPG/PNG → 多尺寸透明 ICO
│
├── build/  build_onefile/  PyInstaller 中间产物（gitignore）
├── dist/                   PyInstaller 文件夹版输出
│   └── CommTool/         【独立可执行版本 — 把这个文件夹拷走就能用】
│       ├── CommTool.exe   图标已嵌入 exe 资源段
│       └── _internal/       Python + Qt DLL（不含 icon.ico — 图标在源码里 base64）
├── dist_onefile/           PyInstaller --onefile 输出 CommTool_onefile_v*.exe
└── installer/              Inno Setup 输出 CommTool_Setup_v*.exe
```

> 运行时用户配置 `settings.ini`：打包版落在 exe 同级（装不进 Program Files 时回退 `%APPDATA%\CommTool\`）；开发模式落在源码同级（已 gitignore）。

---

## 4. 从源码运行

```powershell
# 1. 装依赖（清华镜像，国内快）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 启动
py -3 src\main.py
```

要求 Python ≥ 3.9（实际测试在 3.13）。

---

## 5. 重新打包

三种产物的构建脚本互相独立，按需调用：

### 5.1 文件夹版（基础，给其他两个当输入）

```
scripts\build.bat
```

输出 `dist\CommTool\` (约 98 MB 整个文件夹，含 CommTool.exe + _internal/)。整个文件夹可拷贝携带使用。

构建命令（简化版，从项目根执行）：

```powershell
py -3 -m PyInstaller --noconfirm --clean --windowed ^
    --name CommTool --icon assets\icon.ico ^
    src\main.py
```

> 用 `py -3 -m PyInstaller` 而非裸 `pyinstaller`：后者可能命中 PATH 里的旧版本静默失败。

> ⚠️ **没有 `--add-data icon.ico`**：图标已经 base64 编码在 `src\icon_data.py` 里（被 `app_icon.py` import），运行时不读取外部文件。`--icon assets\icon.ico` 是 PyInstaller 把图标嵌入 exe 文件本身的 Windows 资源段（让资源管理器里 exe 显示图标），跟运行时窗口图标是两回事。

`build.bat` 加了 20+ 个 `--exclude-module` 排除不用的 Qt 模块（WebEngine、Multimedia、Bluetooth、Quick/QML、Sql 等），把打包体积从默认 ~150 MB 砍到 **~98 MB**。

### 5.2 单文件版（onefile）

```
scripts\build_onefile.bat
```

自动从 `src\version.py` 读版本号，输出 `dist_onefile\CommTool_onefile_v<版本>.exe`（~38 MB 单文件，文件名带版本号，与安装包一致）。首次启动稍慢 1~2 秒（自解压到 `%TEMP%`），之后跟文件夹版无差。

等价命令（`v%VER%` 由脚本从 version.py 注入到 `--name`）：

```powershell
py -3 -m PyInstaller --noconfirm --clean --windowed --onefile ^
    --name CommTool_onefile_v1.1.2 --icon assets\icon.ico ^
    --distpath dist_onefile --workpath build_onefile ^
    src\main.py
```

### 5.3 安装版（Inno Setup）

前置：`winget install JRSoftware.InnoSetup`（一次性）。然后：

```
scripts\build_installer.bat
```

自动从 `src\version.py` 读 `__version__`，传给 ISCC 编译 `scripts\CommTool.iss`，输出 `installer\CommTool_Setup_v<版本>.exe` (~28 MB)。

安装包特性：
- 多语言（英 / 简中 / 繁中，第一步选）
- 路径可选（默认 `%LocalAppData%\Programs\CommTool\`，可改任意盘）
- per-user 安装无需管理员；选"为所有用户"自动提权装到 Program Files
- 自动创建开始菜单 + 桌面快捷方式（可选）+ 控制面板卸载条目

### 5.4 Linux 版

```bash
bash scripts/build.sh
```

`build.sh` 用 venv 隔离 + 清华镜像 + 同样的 PyInstaller 参数（list_ports_linux 而非 _windows）。注意 PyInstaller 不支持交叉编译，必须在 Linux 上跑。

### 5.5 改版本号

只改 `src\version.py` 一处：
```python
__version__ = "1.1.2"
```
然后重新跑上面任意构建脚本。状态栏右下版本号 + 安装包文件名 `CommTool_Setup_vX.X.X.exe` 同时同步。`CommTool.iss` 通过 `#ifndef MyAppVersion #define ...` 接受 ISCC 命令行 `/DMyAppVersion=...` 覆盖。

---

## 6. 换图标

替换图标分两个层面：

**exe 文件本身的图标**（资源管理器里看到的）：

1. 把新原图存为 `assets\icon_src.png` 或 `assets\icon_src.jpg`（任意分辨率，自动居中裁剪成方形）
2. 运行 `python assets\icon_convert.py` 生成 `assets\icon.ico`（自动抠白底背景 + 边缘羽化）
3. 双击 `scripts\build.bat` 重新打包

**程序运行时显示的图标**（窗口标题栏 / 任务栏 / 托盘）：

需要重新生成 base64 替换 `src\icon_data.py` 里的 `ICON_B64`：

```powershell
python -c "from PIL import Image; img = Image.open('assets/icon_preview.png').convert('RGBA'); img.thumbnail((128, 128), Image.LANCZOS); img.save('_icon_embed.png', 'PNG', optimize=True)"
python -c "import base64, textwrap; b64 = '\n'.join(textwrap.wrap(base64.b64encode(open('_icon_embed.png','rb').read()).decode(), 76)); open('src/icon_data.py','w',encoding='utf-8').write(f'# -*- coding: utf-8 -*-\nICON_B64 = \"\"\"\\\n{b64}\n\"\"\"\n')"
```

第二条命令直接把新的 `icon_data.py` 写出来（约 545 行 base64）。

**抠图算法**：从四个角洪水填充识别同色背景区域，把这些像素的 alpha 设为 0，再做 1px 高斯模糊让边缘平滑。**角色内部的白色**（牙齿、眼睛高光等）因为不和四角连通，**不会被误抠**。

---

## 7. 依赖

| 包 | 版本 | 用途 |
|----|------|------|
| PyQt5 | ≥ 5.15 | GUI 框架 + 网络（QtNetwork，随 PyQt5 自带，无需单独装） |
| pyserial | ≥ 3.5 | 串口收发（Serial 连接类型） |
| pyinstaller | ≥ 6.0 | 打包 exe（仅开发时需要） |
| Pillow | ≥ 10.0 | 图标转换（仅 `icon_convert.py` 用）|

---

## 8. 已知问题与注意事项

- HEX 发送内容必须是偶数个 hex 字符（空格 / 横线 / 冒号等任意分隔符可省）
- 定时发送最小周期 10 ms，发送失败时（未连接 / 数据格式错误 / 无目标等）自动停止
- UDP 不指定远程且未收到过任何对端时，发送会提示「无可发送目标」；TCP Server 无客户端连入时同理
- 组播收发需防火墙放行、收发端在同一组播地址/端口且同网段
- macOS / Linux 字体优先级会按系统回退，UI 在 macOS PingFang SC、Linux Noto Sans CJK 下也能正常显示（主要测试环境是 Windows 11）
- 频繁切换语言时 IOSSwitch 不触发动画（按设计），其他控件文本会闪一下属正常

---

## 9. 技术说明

### 9.1 iOS 滑动开关

`IOSSwitch` 继承 `QWidget`，重写 `paintEvent` 自绘轨道 + 圆点。通过 `QPropertyAnimation` 配合 `pyqtProperty` 实现圆点位置的缓动动画（160ms `OutCubic`）。加了 `animate=False` 参数让启动恢复状态时不触发动画。

### 9.2 连接层（串口 + 网络）

`net_io.py` 定义统一基类 `NetConn(QObject)`，对外暴露与原串口一致的语义：`open()/close()/send(data,target)/is_open` + `data_received(bytes)/error_occurred/state_changed/clients_changed` 信号。三个实现 `TcpServerConn / TcpClientConn / UdpConn`（组播子类 `UdpGroupConn`）全部基于 **QtNetwork**（`QTcpServer/QTcpSocket/QUdpSocket`），靠 `readyRead` 等信号事件驱动，**不需要自己起轮询线程**。主窗口只认 `NetConn` 接口，因此数据区/发送/高亮/日志等上层逻辑无感。`send()` 返回写出字节数，`SEND_NO_TARGET(-1)` 表示无可发送目标（UDP 无对端 / TCP Server 无客户端）。

串口侧 `serial_io.py` 的 `SerialConn` 镜像同一套接口（内部封装后台读线程 `SerialReader`）。主窗口 `open_conn()` 按「类型」下拉构造 `SerialConn` 或某个 `NetConn`，赋给同一个 `self.conn`，上层对串口 / 网络无感；`clients_changed` / `peer_changed` 是网络专有信号，串口连接不发，主窗口按 `hasattr` 守卫连接。

### 9.3 编码兼容

接收 ASCII 模式时优先 UTF-8 解码，失败回退到 GBK 容错解码，适配国内大部分嵌入式设备的混合编码场景。

### 9.4 时间戳分包与换行分包的"或"逻辑

新块触发条件（满足任一即触发）：

1. 方向变了（RX↔TX）
2. **时间分包** ON 且间隔 > 超时
3. **换行分包** ON 且当前段前有换行符

两个分包开关独立，可单独用也可组合用。例如 Modbus 场景用"时间分包 + 20ms 超时"；AT 命令场景用"换行分包 + Auto 模式"。

### 9.5 跨包"待新块"标志

`_pending_line_break` 处理跨调用的边界：
- 数据以换行结尾（如 `"AT\r\n"`），最后一段是空串 → 标志置 True
- 下次收到数据强制开新块（即使方向和时间都没变）
- 这样 `"OK\r\n"` 和 `"AT+CMD\r\n"` 分两次到达也能正确切成两行

### 9.6 自定义标题栏 + Aero Snap

窗口设置 `Qt.FramelessWindowHint` 去掉系统标题栏，自绘 `TitleBar` 接管图标 + 标题 + 语言下拉 + 最小化/最大化/关闭。**关键技巧**：重载 `nativeEvent` 处理 Windows `WM_NCHITTEST` 消息，根据光标位置返回 `HTLEFT`/`HTTOP`/`HTBOTTOMRIGHT` 等命中码，**让 OS 接管边缘缩放**——手感和原生窗口一致，Aero Snap 拖边贴屏也照常工作。

### 9.7 QSettings 持久化

用 `QSettings` + `IniFormat`，路径在 `exe`（打包后）或 `main.py`（开发模式）同级。`saveGeometry()` / `saveState()` 保存窗口几何和 splitter 位置，恢复时按属性一一应用。开关用 `animate=False` 静默恢复，下拉用 `findText` 或 `index` 匹配。

### 9.8 主题系统

每个主题只定义 4 个核心色 + `mode`：

```python
"ubuntu": {"mode": "dark", "bg": "#300A24", "fg": "#EEEEEC", "tx": "#3465A4", "ts": "#888A85"}
```

`chrome_for(theme_id)` 用 `_mix()` 派生出 19 个 chrome 色：
- **Dark 主题**：`window_bg = bg`，cards / inputs / ghost 按 `mix(bg, white, ratio)` 逐级加亮（ghost 14% 比 card 7% 更亮，避免按钮跟卡片同色）
- **Light 主题**：`window_bg = bg`（cream / 浅灰），`card_bg = #FFFFFF` 永远纯白，让卡片在主题色窗口上突出浮起

切换主题走 `_on_theme_changed`：
1. `apply_style()` 重建全局 QSS
2. `findChildren(QLabel)` 遍历，按 `theme_color_role` 属性（primary/secondary，`make_label` 自动打的）批量刷色
3. `findChildren(QWidget)` 强制 `unpolish + polish`，避免 Qt setStyleSheet 子组件缓存
4. 启动恢复主题时用 `QTimer.singleShot(0, _on_theme_changed)` 推到 event loop 起来后再刷，规避 `__init__` 阶段 setStyleSheet propagation 不彻底的问题

`CloseDialog` 也接 `theme_id` 参数，按 `chrome_for()` 派生自己的 QSS — 关闭对话框跟主题统一。

### 9.9 字符编码

数据区下拉 8 项：Auto / UTF-8 / GBK / GB2312 / GB18030 / Big5 / ASCII / Latin-1。

- **Auto** 走原 UTF-8 优先 + 不完整缓存 + GBK 容错回退
- 其他模式走 `codecs.getincrementaldecoder(name)(errors="replace")` — Python 内置增量解码器自动处理跨包多字节
- 切换编码时 reset `_inc_decoder = None`，避免悬挂字节用错误的 codec 解析
- TX 文本发送 / 显示回显 / 文件加载都按当前 codec 处理（Auto 模式 TX 用 UTF-8）

### 9.10 CRC 算法实现

- **CRC8** (`0x07`)：每字节 XOR 进 CRC 高位，移位 + 条件 XOR poly（标准 CRC-8/CCITT）
- **MOBUS** (`0x31`)：CRC8 变体，多项式不同，国内嵌入式社区把它命名为 `crc8_ccitt`（**实际不是真正的 CCITT**，只是历史命名遗留）
- **ModbusCRC16** (`0xA001`)：每字节 XOR 进 CRC 低位，**右移**（反向多项式），输出**小端**（LSB first，Modbus 标准）
- **CCITT-CRC16** (`0x1021`, init `0xFFFF`)：CRC-16/CCITT-FALSE，每字节 XOR 进 CRC 高字节，**左移**，输出**大端**
- **CRC32**：直接调用 `zlib.crc32`（C 优化，跟 Ethernet/ZIP/PNG 标准一致），输出大端

### 9.11 HEX 输入宽容化

发送 HEX 模式下，先剥离 `/* */`、`//`、`#` 注释，再去掉 `0x` 前缀并过滤非 hex 字符，最后交给 `bytes.fromhex`；下面这些写法都能正确解析：

| 输入 | 解析结果 |
|------|----------|
| `AABBCCDD` | `AA BB CC DD` |
| `AA BB CC DD` | `AA BB CC DD` |
| `aa-bb-cc-dd` | `AA BB CC DD` |
| `AA:BB:CC:DD` | `AA BB CC DD` |
| `0xAA 0xBB 0xCC` | `AA BB CC` |
| `// 注释\nAA BB` | `AA BB` |

---

## 10. 版本历史亮点

- **v1**: 基础串口收发 + iOS 样式 + 持久化
- **v2**: 中英文双语 + 时间戳分包 + Xshell 风格日志
- **v3**: 无边框窗口 + 自绘标题栏 + 边缘原生缩放
- **v4**: 侧边栏布局（USR 风格）+ QGridLayout 右对齐
- **v5**: 换行分包 + 换行符模式选择（Auto / CRLF / LF / CR）
- **v6**: 校验算法补全到 9 种（含 CCITT-CRC16 / CRC32 / ADD16）
- **v7**: 拆分"时间戳"和"分包"为两个独立开关 + 追加换行符模式下拉 + MOBUS（CRC8 poly 0x31）→ 10 种校验
- **v8**: 主控件统一 90px 左右齐平 + 保存/清空按钮也对齐
- **v9**: 关闭确认对话框 + 系统托盘（最小化到托盘 / 退出 / 取消）
- **v10**: 图标 base64 固化在源码内（防替换），运行时不再读外部 `icon.ico`
- **v11**: 多语言扩展到繁体中文 + 鼠标悬停 tooltip + 字号 A−/A+ + 桌面文件夹/onefile/Inno Setup 安装包三种发布形式
- **v12**: 字符编码下拉（Auto/UTF-8/GBK/GB2312/GB18030/Big5/ASCII/Latin-1）+ 跨包 CRLF 修复 + HEX 严格校验非法字符 + 一次性扫描线程
- **v13**: 整体主题切换（9 个终端配色方案，全局 chrome 派生）+ 语言/主题下拉挪到标题栏左上 + 关闭对话框跟主题 + 状态点色统一 helper
- **v14 (v1.0.1)**: 高分屏 HiDPI 缩放适配 + 数据区滚动锁定（往上翻定住 / 「↓ 最新」按钮回底 + 自动跟随）+ 单击行高亮 + 切主题历史文字按角色（时间戳/收/发）重涂 + **多条发送弹窗**（每行独立 HEX/换行/校验 + 勾选循环依次发）+ **关键字高亮弹窗**（每条独立颜色 + 背景/文字 + 收/发/收发范围 + 区分大小写、跳过时间戳）+ 「只显高亮行」过滤 + 弹窗原生标题栏跟随主题深浅 + 波特率补全高速率（256000~2000000）+ 英文标签宽度自适应 + 数据区显示格式统一只看「HEX 显示」开关
- **v15 (v1.0.2)**: 整体界面紧凑化（字号/控件/开关/间距缩小）+ **关键字高亮分组**（左侧分组列表，新建/重命名/删除，标题栏下拉选生效分组含「关闭」，编辑与生效独立）+ **多条发送分组 + 每行名称/延时 + 主界面快捷栏**（[多条发送][▶循环][分组下拉] + 命令平铺直接发，循环按每行延时）+ **实时记录按文件大小分包**（不分包/1M~100M/自定义，写满切 _001/_002…）+ 状态栏显示当前日志路径 + 状态栏竖线分隔 + **数据区中文右键菜单**（复制/全选/清空/保存，跟随语言）+ 性能优化（编辑去抖、切主题大文档重涂不再卡死）+ 一批审查修复
- **v16 (v1.0.3)**: 工程结构重构（无用户可见功能变化）—— 原 ~4500 行单文件 `main.py` 按模块拆分为 `main_window / dialogs / widgets / serial_io / theme / i18n / app_icon / icon_data` 等独立文件；目录分类整理为 `src/`（源码）、`docs/`（文档）、`scripts/`（构建/启动脚本 + .iss）、`assets/`（图标资源），根目录只留 README + requirements + 打包产物；所有脚本与 .iss 路径同步更新（脚本内部 `cd` 回根目录，双击即用），打包统一改用 `py -3 -m PyInstaller`
- **NetworkTool 分支（网络版）**: 产品更名 **NetworkTool**，左上角「串口」连接区整体改为「网络」—— 支持 **UDP / UDP Multicast（组播）/ TCP Server / TCP Client** 四种协议，基于 **QtNetwork** 事件驱动（新增 `net_io.py`，移除 `serial_io.py` 与 pyserial 依赖）；UDP 可选「指定远程」开关（关=回复对端）、TCP Server 多客户端「目标」下拉（含全部广播）、组播地址校验、禁用输入框变灰；数据区/发送/高亮/日志/多条发送/主题/语言等其余功能完全复用。产品与全部打包产物（exe/安装包/`dist` 目录、`.iss`、`%APPDATA%` 配置目录）统一更名 **NetworkTool**
- **v17 (v1.0.4)**: 在线更新 —— 托盘「关于」对话框新增「检查更新」，从版本清单（内网优先、回退 GitHub 上 NetworkTool 分支 raw）比对最新版，一键下载并弹出安装向导手动升级；更新源 8 秒超时回退（外网不卡）、下载魔数（MZ）校验防错误页误执行、关闭对话框中止在途下载、启动清理 `%TEMP%` 残留安装包、版本号解析容错；基于 Qt 自带 QtNetwork 无新依赖；新增一键发版脚本 `scripts/release.ps1`
- **v18 (v1.0.5)**: 数据区搜索（Ctrl+F：高亮全部匹配 + ▲/▼ 上下跳转 + 实时「N/总数」计数）+ 多屏下状态栏/窗口拖拽/任务栏最小化修复（WM_GETMINMAXINFO 多显示器对齐）+ 深色主题搜索/高亮对比优化 + 系统托盘单击 toggle 显示/隐藏
- **v19 (v1.0.7)**: 稳定性与代码审查修复 —— TCP Client 连接新增超时保护（不可达地址不再卡约 20 秒）、UDP 断开后清理最近对端缓存（复用连接不再回复到旧地址）；搜索导航改 O(1) 着色（大文档点 ▲/▼ 不再全文重扫）、打开搜索消除双重扫描、查找栏 viewport/计数标签加守卫、_parse_version 修正预发布版本号比较；修复纯搜索（未配关键字规则）时实时新数据的搜索匹配/计数停更
- **v20 (v1.0.8)**: 修复关键字 / 搜索高亮时，底部新接收的数据会「整批闪一下高亮」的问题（高亮选区不再随末尾插入延伸）
- **CommTool 分支（统一版）**: 串口版 SerialTool 与网络版 NetworkTool 合并为一个产品 **CommTool / 通信调试工具**。「类型」下拉统一 串口 + 网络五种连接（串口 `SerialConn` 与网络 `net_io` 共用 `open()/close()/send()/is_open` + 信号接口，主窗口同一个 `self.conn`）；恢复 `serial_io.py` 与 pyserial 依赖；品牌、类名、AppUserModelID、`%APPDATA%` 配置目录、安装包 / dist / .iss 全部更名 CommTool（新独立安装 GUID，不覆盖旧版；旧 NetworkTool 配置自动回退读取）；发布走 CommTool 分支、tag 前缀 `comm-v`
- **v21 (v1.1.0)**: **收发速率 / 包统计**——底部状态栏的 RX/TX 由「纯字节数」升级为「字节 · 包数 · 实时速率(B/s)」：包计数（RX = 每次到达一块、TX = 每次成功发送）、1Hz 采样的实时速率、错误数 >0 时追加 ⚠ 标记；鼠标悬停 RX/TX 标签弹出 tooltip 看完整明细（总量 / 包数 / 当前速率 / **峰值速率** / 错误数）；状态栏**右键「重置统计」**清零计数器（不动数据区，跟随语言/主题）；速率采样常驻、断开后自然归零；三语 i18n 同步、无新依赖、无新文件
- **v22 (v1.1.1)**: **数据波形图 + 协议帧解析**两大数据分析功能（标题栏「波形图」「帧解析」）。波形图（pyqtgraph）从 RX 解析数值实时绘多通道滚动曲线，三种解析（分隔符 / 正则 / HEX 字节字段 + 帧头过滤），通道显隐配色、窗口点数、X 轴样本/时间、暂停/清空/导出 CSV、窗口可缩放。帧解析表多帧多规则（规则列表「帧头 | 字段定义」，按帧头前缀匹配），「全部」+ 分规则标签、序号列 + 原始帧列、数值 x 后缀十六进制、hexN/strN、复制/导出、滚动锁定 +「↓最新」回底。二者共用 `binproto` 字段定义。新增依赖 pyqtgraph + numpy（安装包内置）；三语 i18n
- **v23 (v1.1.2)**: **自动应答全面增强 + 命令历史 + 动态字段 + 自动重连 + 配置档导入/导出**。自动应答从 v1.1.1 实验版升级到生产可用：多帧应答（reply 用 `|` 分段顺次发，ACK+DATA 类协议）、HEX 通配 `??`、应答占位符大扩展（`{rN+K}`/`{rN^K}`/`{seq}`/`{ts}`）、四种时序控制（整包超时分帧 / 收包校验 / 应答延时 / 触发冷却）、双击按钮一键开关、`?` 帮助按钮带 6 个具体例子。发送区：**命令历史** ↑↓ 导航（FIFO 100 跨会话）+ **动态字段** `{count}/{ts}/{randN}`（发送失败回滚 count、N≤256）+ 悬停长寿命 tooltip。连接：**自动重连**按 1/2/4/8/16/30s 退避（仅对非主动断开生效）。**会话配置档导入/导出**（数据区右键 + Ctrl+Shift+S/O）一份 JSON 包含 35+ 项设置；导入立即生效，已开弹窗同步刷新。**Ctrl+F 全局快捷键**任何控件可用。波形图/帧解析顶部 `?` 按钮 + 独立说明窗（各 5 例）。**InfoDialog** 替代 QMessageBox（同主题圆角卡）。5 个子对话框统一 `parent=None` 修 Windows 主窗 resize 失效 bug。

---

## 许可证 / License

本项目以 **[GPL-3.0](LICENSE)** 开源。

> 为什么是 GPL：本工具基于 **PyQt5**，其免费版采用 GPL v3 授权（Riverbank 双授权：GPL 或商业）。
> 依赖 GPL 库分发，整个应用按 GPL 的传染性须以 GPL-3.0（或兼容协议）发布。其余依赖
> pyserial(BSD) / pyqtgraph(MIT) / numpy(BSD) 均为宽松协议，无额外约束。
> 若将来需要闭源 / 商业分发，可把 PyQt5 换成 PySide6（LGPL）后再改用宽松协议。

Copyright © 2026 heropml. Licensed under the GNU General Public License v3.0.
