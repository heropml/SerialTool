# 发版指南（CommTool）

CommTool 同时发布 **Windows** 和 **macOS** 两个安装包，代码 + Release **双托管**到
GitHub 和 Gitee 两个仓库（`heropml/SerialTool`，`CommTool` 分支），共用同一份更新清单 `latest.json`。

- Windows 发版脚本：[`scripts/release.ps1`](scripts/release.ps1)（PowerShell，一键：双包打包(folder 安装包 + onefile) + push github/gitee + GitHub/Gitee 双 Release；只有三语用户文档需手动同步）
- macOS 发版脚本：[`scripts/release_macos.sh`](scripts/release_macos.sh)（Bash）
- 版本号单点真源：[`src/version.py`](src/version.py) 的 `__version__`
- Release tag 统一用 `comm-v<版本>` 前缀（与串口版 `v1.0.x`、网络版 `net-v1.0.x` 区分）

> ⚠️ **双 remote 必须都推**：本仓库有 `github` 和 `gitee` 两个 remote，每次发版**代码和
> Release 都要推两边**，否则国内用户（走 Gitee）拿不到新版。
> ```bash
> git push github CommTool && git push gitee CommTool
> ```

## 在线更新走哪个源（重要）

`src/updater.py` 的 `UPDATE_MANIFEST_URLS` 按顺序试，第一个成功的为准：

1. **Gitee raw**（`gitee.com/.../raw/CommTool/latest.json`）— 国内优先，秒回
2. **GitHub raw**（回退）— Gitee 抽风时兜底

`latest.json` 的 `url` 字段**统一指向 Gitee Release 下载**（Gitee 全球可达，国内国外都下得到）。
所以无论清单从哪个源读到，**下载都走 Gitee**。改源顺序/下载地址 = 改 `updater.py` + `latest.json`，
**要重打包**（updater.py 编进二进制）。

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

> **先 Windows 后 macOS**。原因：`latest.json` 由 Windows 脚本统一维护。
> macOS 端只往同一个 Release 追加 `.dmg`，不动 `latest.json`。

### 1. Windows 机器上
```powershell
.\scripts\release.ps1 1.1.2 "本次更新说明"
```
自动完成：改版本号 → 改 `latest.json`(url 指 Gitee) → 打包 folder 安装包 + onefile →
git 提交 → push github + gitee → 建 GitHub Release(`--latest`，传两个 exe) →
发 Gitee Release(调 `release_gitee.py`，国内下载源)。
**只剩三语用户文档要手动补**(脚本结尾会提醒)：`docs/USAGE.md` · `使用说明.md` · `使用說明.md`
各加版本历史章节 + 目录条目 + 右下角「当前版本号」。macOS `.dmg` 仍由协作者补(见下方第 2 步)。

### 2. macOS 机器上
```bash
git pull
bash scripts/release_macos.sh 1.1.2
```
自动完成：版本号对齐 → 打包 `.dmg` → 把 `.dmg` 上传到**同一个** Release `comm-v1.1.2`。

完成后该 Release 同时挂着 `.exe` 和 `.dmg`，`latest.json` 也已是新版，
两平台用户在 app 内「帮助 → 关于 → 检查更新」都能收到提示：
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

- Windows：`.\scripts\release.ps1 1.1.1 "说明" -Local`（只本地打包+提交，跳过 push/Release）
- macOS：`bash scripts/build_macos.sh --dmg`（只打包 `.app` + `.dmg`，不碰 git/Release）

---

## 五、版本号与 tag 约定

| 项 | 值 |
|----|----|
| 版本号来源 | `src/version.py` 的 `__version__`（X.Y.Z） |
| Release tag | `comm-v<版本>`（如 `comm-v1.1.1`） |
| Windows 包名 | `CommTool_Setup_v<版本>.exe` |
| macOS 包名 | `CommTool_v<版本>.dmg` |
| 分支 | `CommTool` |

> CommTool 现为本仓库主力产品（默认分支已是 `CommTool`）。建 GitHub Release 用
> `--latest`（让最新 CommTool 持有「Latest」徽章）。**旧的 `--latest=false` 约定已作废**
> （那是串口/网络/统一三产品并存期的写法）。

---

## 六、Gitee 镜像（国内下载 / 升级，必做）

国内用户连不上 GitHub，所以代码 + Release **必须同步一份到 Gitee**
（`gitee.com/heropml/SerialTool`，公开仓，默认分支 `CommTool`）。

### 6.0 一次性配置（配好后长期免临时令牌）

**(a) SSH 推代码免令牌** —— remote `gitee` 已是 SSH（`git@gitee.com:heropml/SerialTool.git`）。
把本机公钥 `~/.ssh/id_rsa.pub` 贴到 Gitee → 设置 → SSH 公钥。验证：
```bash
ssh -T git@gitee.com      # 出现 "Hi heropml!" 即通
```

**(b) 长期令牌发 Release** —— Gitee 发 Release 只能走 Open API（必须令牌）。
Gitee → 设置 → 私人令牌 生成一个（**只勾 `projects`**，有效期设长），把令牌字符串写进
**`scripts/.gitee_token`**（单独一行；该文件已在 `.gitee_token` ignore，不会提交）：
```bash
echo '你的长期令牌' > scripts/.gitee_token
```
> 也可改用环境变量 `GITEE_TOKEN`（脚本优先读它）。令牌长期躺本地，注意别外泄、定期轮换。

### 6.1 推代码到 Gitee
```bash
git push gitee CommTool       # 走 SSH，免令牌
```

### 6.2 发 Gitee Release（一键脚本）
前置：`installer/CommTool_Setup_v<版本>.exe` + `dist_onefile/CommTool_v<版本>.exe` 已打好。
```bash
py -3 scripts/release_gitee.py            # 版本号自动从 src/version.py 读
py -3 scripts/release_gitee.py 1.1.3      # 或指定版本号
```
脚本自动：读令牌 → 建/复用 Release `comm-v<版本>` → **删旧附件再传新的**（Gitee 无 clobber，
改 bug 重传同版本也能直接跑）→ 打印下载链接。中文 UTF-8、multipart 都已处理好。

> Gitee 附件下载 URL 固定格式：
> `https://gitee.com/heropml/SerialTool/releases/download/comm-v<版本>/<文件名>`
> ——`latest.json` 的 `url` 就用这个（会 302 到 foruda.gitee.com CDN，updater 已开
> `FollowRedirectsAttribute` 会跟随）。

### 6.3 验证国内升级链路
```bash
# Gitee 清单（updater 第一源）能读到新版本
curl -sL https://gitee.com/heropml/SerialTool/raw/CommTool/latest.json
# Gitee 下载链接能解析（HTTP 200）
curl -sL -o /dev/null -w "%{http_code} %{size_download}\n" \
  https://gitee.com/heropml/SerialTool/releases/download/comm-v1.1.2/CommTool_Setup_v1.1.2.exe
```

---

## 七、发版完整清单（别漏）

- [ ] `src/version.py` 改版本号
- [ ] `latest.json` 改 version / url（url 指 Gitee）/ notes
- [ ] `docs/RELEASE_NOTES.md` + README + 三语用户文档 同步
- [ ] 打包：`build.bat` → ISCC（`MSYS_NO_PATHCONV=1`，`/DMyAppVersion=`）→ onefile（直调 PyInstaller）
- [ ] `git push github CommTool`
- [ ] `git push gitee CommTool` ← **易漏**（走 SSH，见 6.0a）
- [ ] GitHub Release：`gh release create comm-v<版本> --target CommTool --latest <两个 exe>`
      （重传同版本用 `gh release upload comm-v<版本> --clobber <两个 exe>`）
- [ ] Gitee Release：`py -3 scripts/release_gitee.py`（见 6.2）
- [ ] 验证两源 latest.json + Gitee 下载链接（见 6.3）
- [ ] （有 Mac 时）补 `.dmg` 到两个 Release
