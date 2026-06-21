# 发版指南（CommTool）

CommTool 同时发布 **Windows** 和 **macOS** 两个安装包,共用同一个 GitHub 仓库
（`heropml/SerialTool`，`CommTool` 分支）和同一份更新清单 `latest.json`。

- Windows 发版脚本：[`scripts/release.ps1`](scripts/release.ps1)（PowerShell）
- macOS 发版脚本：[`scripts/release_macos.sh`](scripts/release_macos.sh)（Bash）
- 版本号单点真源：[`src/version.py`](src/version.py) 的 `__version__`
- Release tag 统一用 `comm-v<版本>` 前缀（与串口版 `v1.0.x`、网络版 `net-v1.0.x` 区分）

---

## 一、各平台依赖

**Windows**
- PowerShell 7
- Python + PyInstaller
- Inno Setup 6
- GitHub CLI（`gh`，需先 `gh auth login`）

**macOS**
- Python 3 + PyInstaller + Pillow（`build_macos.sh` 会自动装进 `.venv`）
- 系统自带 `iconutil` / `sips` / `hdiutil`
- GitHub CLI（`gh`，可选；没登录则脚本自动建 tag + 给手动上传步骤）

---

## 二、标准双平台发版（推荐顺序）

> **先 Windows 后 macOS**。原因：`latest.json` 由 Windows 脚本统一维护（它把下载
> 链接指向 `.exe`）。macOS 端只往同一个 Release 追加 `.dmg`，不动 `latest.json`。

### 1. Windows 机器上
```powershell
.\scripts\release.ps1 1.1.0 "本次更新说明"
```
自动完成：改版本号 → 改 `latest.json` → 打包 `.exe` → git 提交 → push →
建 Release `comm-v1.1.0` 上传 `.exe`。

### 2. macOS 机器上
```bash
git pull
bash scripts/release_macos.sh 1.1.0
```
自动完成：版本号对齐 → 打包 `.dmg` → 把 `.dmg` 上传到**同一个** Release `comm-v1.1.0`。

完成后该 Release 同时挂着 `.exe` 和 `.dmg`，`latest.json` 也已是新版，
两平台用户在 app 内「关于 → 检查更新」都能收到提示：
- Windows：下载 `.exe` 自动安装
- macOS：打开该 Release 页，手动下载 `.dmg` 拖拽替换

---

## 三、只发单平台时的注意事项 ⚠️

`latest.json` 是 **Win/Mac 共用**的，它的 `version` 决定两个平台的「有新版」提示，
`url` 指向 Windows 的 `.exe`。因此：

- **只发 macOS 时**：`release_macos.sh` **故意不改** `latest.json`。
  若此时手动把 `latest.json` 版本号改新，Windows 用户会被导向**还不存在**的 `.exe`。
  所以：要么等 Windows 同版本也发布后再改 `latest.json`，要么本次先不通知用户
  （Release 里有 `.dmg`，知道的人可自取）。
- **只发 Windows 时**：`release.ps1` 会正常更新 `latest.json`，Windows 用户照常升级；
  macOS 用户点检查更新会跳到 Release 页，但页面上可能还没有该版本的 `.dmg`——
  如需 macOS 也升级，补跑一次 `release_macos.sh <同版本号>` 即可。

---

## 四、试打包（不发布）

- Windows：`.\scripts\release.ps1 1.1.0 "说明" -Local`（只本地打包+提交，跳过 push/Release）
- macOS：`bash scripts/build_macos.sh --dmg`（只打包 `.app` + `.dmg`，不碰 git/Release）

---

## 五、版本号与 tag 约定

| 项 | 值 |
|----|----|
| 版本号来源 | `src/version.py` 的 `__version__`（X.Y.Z） |
| Release tag | `comm-v<版本>`（如 `comm-v1.1.0`） |
| Windows 包名 | `CommTool_Setup_v<版本>.exe` |
| macOS 包名 | `CommTool_v<版本>.dmg` |
| 分支 | `CommTool` |

> 该仓库还托管串口版 SerialTool（主产品）。建 Release 时用 `--latest=false`，
> 避免 CommTool 的 Release 抢走 SerialTool 的「Latest」标记。
