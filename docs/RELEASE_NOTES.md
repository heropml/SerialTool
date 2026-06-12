# SerialTool v1.0.3

本次为**工程结构重构版**：代码拆分为多模块、目录分类整理，**功能与界面与 v1.0.2 完全一致，无用户可见变化**。日常使用者无需关注，开发/打包者请留意路径变动。

## 🧱 代码模块化

- 原 ~4500 行单文件 `main.py` 按职责拆分为独立模块，便于后期维护：
  - `main.py` — 入口（HiDPI + QApplication + 启动）
  - `main_window.py` — 主窗口 `SerialTool` 主体类
  - `dialogs.py` — 多条发送 / 关键字高亮 / 关闭确认 弹窗
  - `widgets.py` — 自定义控件（IOSSwitch / TitleBar / Card）
  - `serial_io.py` — 串口读线程 + 端口扫描线程
  - `theme.py` — 主题配色表 + 角色着色
  - `i18n.py` — 三语翻译表（简 / 英 / 繁）
  - `app_icon.py` / `icon_data.py` — 运行时图标加载与 base64 数据
  - `version.py` — 版本号单点真源
- 拆分经 pyflakes（零未定义/未使用）+ 全模块导入 + 运行冒烟校验。

## 🗂️ 目录分类整理

根目录原先几十个文件平铺，现按类型归入子目录：

| 目录 | 内容 |
|------|------|
| `src/` | 全部 Python 源码 |
| `docs/` | USAGE.md / 使用说明.md / 使用說明.md / RELEASE_NOTES.md |
| `scripts/` | run*.bat/vbs、build*.bat/sh、SerialTool.iss |
| `assets/` | icon.ico、icon_preview.png、icon_convert.py |

根目录只保留 `README.md`、`requirements.txt` 和三个打包产物目录（`dist/`、`dist_onefile/`、`installer/`）。

## 🔧 构建链同步更新

- 所有启动/构建脚本内部 `cd` 回项目根再执行，**双击即用，无需手动切目录**。
- `SerialTool.iss` 内路径全部加 `..\` 前缀指回根目录；安装包编译走 PowerShell 调 ISCC（避免 MSYS 路径转换问题）。
- 打包命令统一改用 `py -3 -m PyInstaller`（规避裸 `pyinstaller` 命中 PATH 旧版静默失败）。

## 📦 下载

| 形式 | 文件 | 说明 |
|------|------|------|
| 安装版 | `SerialTool_Setup_v1.0.3.exe` | 推荐，向导安装 + 桌面快捷方式 |
| 单文件版 | `SerialTool_onefile_v1.0.3.exe` | 免安装，双击即用（首次启动略慢 1~2 秒） |
| 文件夹版 | `dist/SerialTool/` | 解压即用，启动最快 |

> 无需安装 Python；Windows 10/11。功能同 v1.0.2。
