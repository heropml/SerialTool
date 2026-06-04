# SerialTool

iOS 风格的串口调试工具，基于 PyQt5 + pyserial。支持中英文动态切换、无边框窗口 + 自绘标题栏、QSplitter 可拖拽布局、Xshell 风格日志、10 种校验算法、关闭确认 + 系统托盘、图标固化在源码内（防替换）。

![iOS 风格 UI](./icon_preview.png)

---

## 功能总览

### 串口连接

- 自动列出可用 COM 口 + 设备描述（每 1.5 秒后台轮询，热插拔自动刷新）
- 波特率 1200–921600（可手填自定义）
- 数据位 5/6/7/8、校验 None/Even/Odd/Mark/Space、停止位 1/1.5/2

### 数据区（接收 + 发送日志）

收发数据**同框显示**，箭头区分方向、颜色区分类型：

| 标记 | 含义 | 颜色 |
|------|------|------|
| `←` | RX 接收 | 灰黑（`#1C1C1E`）|
| `→` | TX 发送 | iOS 蓝（`#007AFF`）|

**显示选项**（侧边栏 → 数据区）

- **HEX 显示** — 把字节渲染成 `AA BB CC ...`，否则按文本（UTF-8 优先，GBK 容错回退）
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

### 发送区

**发送选项**（侧边栏 → 发送区）

- **HEX 发送** — 把输入框内容当 HEX 字符解析（`AA BB`、`AABB`、`AA-BB`、`AA:BB`、`AA,BB`、带 `0x` 前缀等都接受）
- **追加换行** + **换行符模式（CRLF / LF / CR）** — 自动在尾部追加对应字节，下拉框默认 CRLF
- **定时发送** + **周期 ms** — 最小 10ms，串口未开自动关闭
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
- 发送按钮 + 实时 TX 字节数统计（B / KB / MB 自动单位）

### 界面

- **无边框窗口 + 自绘标题栏**：图标 + 标题 + 语言下拉 + 最小化/最大化/关闭按钮全在标题栏一行
  - 拖标题栏移动窗口、双击切换最大化
  - 边缘缩放走 Windows 原生 `WM_NCHITTEST`，手感和系统窗口完全一致（Aero Snap 拖边贴屏也照常工作）
- **iOS 风格控件**
  - 圆角卡片 + 柔和投影（`QGraphicsDropShadowEffect`）
  - 自绘 `IOSSwitch` 滑动开关，带缓动动画
  - 主按钮 / 幽灵按钮 / 图标按钮三套样式
  - `#007AFF` iOS 蓝、`#34C759` 绿、`#FF3B30` 红
- **左侧 sidebar + 右侧数据区**
  - 左：串口设置 / 数据区设置 / 发送区设置 三张卡片，`QGridLayout` 让所有右侧控件右对齐
  - 右：数据日志区 + 发送输入框（垂直可拖）
  - 左右用 `QSplitter` 分隔，宽度可调（侧边栏 240–360 px）
- **中英文切换**：标题栏右侧下拉，**无需重启**，所有 UI 文字（标签、按钮、占位提示、错误消息、文件对话框）瞬间切换

### 关闭程序 + 系统托盘

点窗口右上 `×` 弹出三选一对话框：

| 选项 | 行为 |
|------|------|
| 最小化到托盘（默认）| `hide()` 隐藏窗口，托盘弹气泡通知 |
| 退出程序 | 真退出 — 存配置 + 关串口 + 关日志 |
| 取消 | 关闭事件被吃掉，窗口保留 |

**系统托盘图标**（任务栏右下角通知区）：
- 单击 / 双击 → 恢复窗口
- 右键菜单 → "显示窗口" / "退出"
- 切换中英文时托盘菜单文字同步
- 系统不支持托盘时，`×` 直接退出（不弹对话框）

### 图标固化（防替换）

128×128 PNG 图标用 **base64 编码写死在独立的 `icon_data.py` 文件**里（`ICON_B64` 常量），`main.py` 通过 `from icon_data import ICON_B64 as _APP_ICON_B64` 导入，运行时由 `get_app_icon()` 解码加载。带来的好处：

- 别人**没法通过替换 `icon.ico`** 来改窗口/任务栏/托盘里显示的图标
- 打包出的 `dist\SerialTool\_internal\` 里**完全没有 `icon.ico` 文件**
- 资源管理器里 exe 文件的图标仍然来自 PyInstaller 的 `--icon` 嵌入资源（这是 Windows 资源段，跟运行时图标分开）

### 持久化

启动时自动从 `settings.ini` 恢复，关闭时自动保存：

- 窗口位置 + 大小（含最大化状态）
- 两个 splitter 的精确位置
- 当前语言（中文 / 英文）
- 所有开关 / 输入框 / 下拉选项
- 发送框内容
- 字号、最大行数

**位置**：`SerialTool.exe` 同级目录的 `settings.ini`，整个 `dist\SerialTool\` 文件夹可以连配置一起复制到其他机器。

---

## 三种使用方式

### 1. 独立 exe（推荐，无需 Python）

```
dist\SerialTool\SerialTool.exe
```

整个 `dist\SerialTool\` 文件夹（约 93 MB）可以复制到任意 Windows 10/11 64 位电脑直接运行，**目标机器无需安装 Python、PyQt5、pyserial**。

### 2. 静默启动源码版（已装 Python）

双击 `run.vbs` — 完全无窗口启动（优先 `pyw main.py`，回退 `pythonw main.py`），没有 cmd 闪屏。

### 3. 调试启动源码版（看 Python 报错）

双击 `run_debug.bat` — 保留 cmd 窗口，能看到 Python 异常输出，方便排查问题。

---

## 文件结构

```
SerialTool/
├── main.py                 主程序源码 (~1700 行)
├── requirements.txt        Python 依赖
├── README.md               本文件
│
├── icon_src.jpg            原始图标（用户自备，运行 icon_convert.py 时读取）
├── icon.ico                多分辨率 ICO（16/32/48/64/128/256 px，透明背景）
├── icon_preview.png        256×256 PNG 预览（icon_convert.py 输出的副产品）
├── icon_convert.py         一次性脚本：JPG/PNG → 多尺寸透明 ICO
│
├── run.vbs                 静默启动（推荐日常用）
├── run.bat                 快速启动（cmd 一闪而过）
├── run_debug.bat           调试启动（保留 cmd 看错误）
│
├── build.bat               重新打包 exe
├── SerialTool.spec         PyInstaller 配置（自动生成）
│
├── settings.ini            用户配置（运行时自动生成）
│
├── build/                  打包中间产物（可删）
└── dist/
    └── SerialTool/         【独立可执行版本 — 把这个文件夹拷走就能用】
        ├── SerialTool.exe   图标已嵌入 exe 资源段
        ├── settings.ini    （首次运行后才出现）
        └── _internal/      Python + Qt + pyserial DLL（不含 icon.ico — 图标在源码里 base64）
```

---

## 从源码运行

```powershell
# 1. 装依赖（清华镜像，国内快）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 启动
py -3 main.py
```

要求 Python ≥ 3.9（实际测试在 3.13）。

---

## 重新打包

修改 `main.py` 后，双击 `build.bat`，PyInstaller 自动重新生成 `dist\SerialTool\` 内的 exe。

构建命令（简化版）：

```powershell
pyinstaller --noconfirm --clean --windowed ^
    --name SerialTool --icon icon.ico ^
    --hidden-import serial.tools.list_ports_windows ^
    main.py
```

> ⚠️ **没有 `--add-data icon.ico`**：图标已经 base64 编码在 `icon_data.py` 里（被 `main.py` import），运行时不读取外部文件。`--icon icon.ico` 是 PyInstaller 把图标嵌入 exe 文件本身的 Windows 资源段（让资源管理器里 exe 显示图标），跟运行时窗口图标是两回事。

`build.bat` 加了 20+ 个 `--exclude-module` 排除不用的 Qt 模块（WebEngine、Multimedia、Bluetooth、Quick/QML、Sql 等），把打包体积从默认 ~150 MB 砍到 **~93 MB**。

---

## 换图标

替换图标分两个层面：

**exe 文件本身的图标**（资源管理器里看到的）：

1. 把新原图存为 `icon_src.png` 或 `icon_src.jpg`（任意分辨率，自动居中裁剪成方形）
2. 运行 `python icon_convert.py` 生成 `icon.ico`（自动抠白底背景 + 边缘羽化）
3. 双击 `build.bat` 重新打包

**程序运行时显示的图标**（窗口标题栏 / 任务栏 / 托盘）：

需要重新生成 base64 替换 `icon_data.py` 里的 `ICON_B64`：

```powershell
python -c "from PIL import Image; img = Image.open('icon_preview.png').convert('RGBA'); img.thumbnail((128, 128), Image.LANCZOS); img.save('_icon_embed.png', 'PNG', optimize=True)"
python -c "import base64, textwrap; b64 = '\n'.join(textwrap.wrap(base64.b64encode(open('_icon_embed.png','rb').read()).decode(), 76)); open('icon_data.py','w',encoding='utf-8').write(f'# -*- coding: utf-8 -*-\nICON_B64 = \"\"\"\\\n{b64}\n\"\"\"\n')"
```

第二条命令直接把新的 `icon_data.py` 写出来（约 545 行 base64）。

**抠图算法**：从四个角洪水填充识别同色背景区域，把这些像素的 alpha 设为 0，再做 1px 高斯模糊让边缘平滑。**角色内部的白色**（牙齿、眼睛高光等）因为不和四角连通，**不会被误抠**。

---

## 依赖

| 包 | 版本 | 用途 |
|----|------|------|
| PyQt5 | ≥ 5.15 | GUI 框架 |
| pyserial | ≥ 3.5 | 串口通信 |
| pyinstaller | ≥ 6.0 | 打包 exe（仅开发时需要） |
| Pillow | ≥ 10.0 | 图标转换（仅 `icon_convert.py` 用）|

---

## 已知问题与注意事项

- HEX 发送内容必须是偶数个 hex 字符（空格 / 横线 / 冒号等任意分隔符可省）
- 定时发送最小周期 10 ms，串口未打开时自动关闭
- 部分 USB 转串口驱动拔插不触发系统通知，必要时手动点 `⟳` 刷新端口列表
- macOS / Linux 字体优先级会按系统回退，UI 在 macOS PingFang SC、Linux Noto Sans CJK 下也能正常显示（主要测试环境是 Windows 11）
- 频繁切换语言时 IOSSwitch 不触发动画（按设计），其他控件文本会闪一下属正常

---

## 技术说明

### iOS 滑动开关

`IOSSwitch` 继承 `QWidget`，重写 `paintEvent` 自绘轨道 + 圆点。通过 `QPropertyAnimation` 配合 `pyqtProperty` 实现圆点位置的缓动动画（160ms `OutCubic`）。加了 `animate=False` 参数让启动恢复状态时不触发动画。

### 串口读取线程

独立 `QThread`（`SerialReader`），轮询 `in_waiting` 字节数，通过 `pyqtSignal` 把数据传回主线程的接收文本框，避免 GUI 阻塞。串口异常会通过 `error_occurred` 信号触发自动关闭。

### 编码兼容

接收 ASCII 模式时优先 UTF-8 解码，失败回退到 GBK 容错解码，适配国内大部分嵌入式设备的混合编码场景。

### 时间戳分包与换行分包的"或"逻辑

新块触发条件（满足任一即触发）：

1. 方向变了（RX↔TX）
2. **时间分包** ON 且间隔 > 超时
3. **换行分包** ON 且当前段前有换行符

两个分包开关独立，可单独用也可组合用。例如 Modbus 场景用"时间分包 + 20ms 超时"；AT 命令场景用"换行分包 + Auto 模式"。

### 跨包"待新块"标志

`_pending_line_break` 处理跨调用的边界：
- 数据以换行结尾（如 `"AT\r\n"`），最后一段是空串 → 标志置 True
- 下次收到数据强制开新块（即使方向和时间都没变）
- 这样 `"OK\r\n"` 和 `"AT+CMD\r\n"` 分两次到达也能正确切成两行

### 自定义标题栏 + Aero Snap

窗口设置 `Qt.FramelessWindowHint` 去掉系统标题栏，自绘 `TitleBar` 接管图标 + 标题 + 语言下拉 + 最小化/最大化/关闭。**关键技巧**：重载 `nativeEvent` 处理 Windows `WM_NCHITTEST` 消息，根据光标位置返回 `HTLEFT`/`HTTOP`/`HTBOTTOMRIGHT` 等命中码，**让 OS 接管边缘缩放**——手感和原生窗口一致，Aero Snap 拖边贴屏也照常工作。

### QSettings 持久化

用 `QSettings` + `IniFormat`，路径在 `exe`（打包后）或 `main.py`（开发模式）同级。`saveGeometry()` / `saveState()` 保存窗口几何和 splitter 位置，恢复时按属性一一应用。开关用 `animate=False` 静默恢复，下拉用 `findText` 或 `index` 匹配。

### CRC 算法实现

- **CRC8** (`0x07`)：每字节 XOR 进 CRC 高位，移位 + 条件 XOR poly（标准 CRC-8/CCITT）
- **MOBUS** (`0x31`)：CRC8 变体，多项式不同，国内嵌入式社区把它命名为 `crc8_ccitt`（**实际不是真正的 CCITT**，只是历史命名遗留）
- **ModbusCRC16** (`0xA001`)：每字节 XOR 进 CRC 低位，**右移**（反向多项式），输出**小端**（LSB first，Modbus 标准）
- **CCITT-CRC16** (`0x1021`, init `0xFFFF`)：CRC-16/CCITT-FALSE，每字节 XOR 进 CRC 高字节，**左移**，输出**大端**
- **CRC32**：直接调用 `zlib.crc32`（C 优化，跟 Ethernet/ZIP/PNG 标准一致），输出大端

### HEX 输入宽容化

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

## 版本历史亮点

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
