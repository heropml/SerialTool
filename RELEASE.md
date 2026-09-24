# 发版指南（CommTool）

CommTool 同时发布 **Windows**、**macOS** 和 **Linux x86_64** 安装包，代码 + Release **双托管**到
GitHub 和 Gitee 两个仓库（`heropml/SerialTool`，`CommTool` 分支），共用同一份更新清单 `latest.json`。

- Windows 发版脚本：[`scripts/release.ps1`](scripts/release.ps1)（PowerShell，一键：双包打包(folder 安装包 + onefile；onefile 待去掉，见「零」) + push github/gitee + GitHub/Gitee 双 Release；只有三语用户文档需手动同步）
- macOS 发版脚本：[`scripts/release_macos.sh`](scripts/release_macos.sh)（Bash）
- Linux 发版脚本：[`scripts/release_linux.sh`](scripts/release_linux.sh)（Bash；在 Linux 上打包 `.run`，挂到已有 `comm-v*` Release）
- 版本号单点真源：[`src/version.py`](src/version.py) 的 `__version__`
- Release tag 统一用 `comm-v<版本>` 前缀（与串口版 `v1.0.x`、网络版 `net-v1.0.x` 区分）

## 零、上传规则速查（新会话先读这一节）

**原则：GitHub 和 Gitee 两站保持一致**——同一分支内容、同一 tag、同一 Release 标题/正文、同一套附件。
**自 v1.8.4 起不再发布免安装单文件版（`CommTool_v<版本>.exe`；v1.8.3 是最后一个带单文件版的版本，只在 GitHub）**，每个版本只发三个安装包：

| 平台 | 文件 | GitHub Release | Gitee Release | 谁来传 |
|------|------|:---:|:---:|------|
| Windows | `CommTool_Setup_v<版本>.exe` | ✅ | ✅ | Windows 机 `release.ps1`（自动传两站） |
| macOS（Apple Silicon） | `CommTool_v<版本>.dmg` | ✅ | ✅ | GitHub：云端 workflow 或 Mac 上 `release_macos.sh`；Gitee：Mac 上 `release_gitee_dmg.py` 补传 |
| Linux x86_64 | `CommTool_Setup_v<版本>_linux_x86_64.run` | ✅ | ✅ | GitHub：`release_linux.sh`；Gitee：需手动补传（见下方「脚本待对齐」） |

- 历史上 Gitee 很多版本缺 dmg / .run，是**当时漏传**，不是规则；以本表为准。
- **Gitee 附件配额 1GB**（2026-09-24 实测约用 705MB，含 v1.8.3 的 exe + dmg）。满了上传会报 HTTP 400「超出配额」，**不自动清理旧版**，满了再人工决定删哪些。
- `latest.json`：`url` 指 **Gitee** 的 Setup.exe；`url_mac` / `url_linux` **只填 GitHub 直链**（历史惯例，不改）。
- 顺序：**先 Windows**（建两站 Release + 传 Setup.exe + 写 `latest.json`）→ 再 macOS / Linux 往**同一个** `comm-v<版本>` 追加。
  ⚠️ `release_gitee.py`（非 `--notes-only`）会**删掉 Gitee 该版全部附件**再传 Setup.exe——dmg / .run 传完后**不要再跑它**，只改正文用 `--notes-only`。
- 一个版本发完后，用本文「九、两站一致性核对」确认两边一致。

### 脚本待对齐（规则已定、脚本尚未改）

- `scripts/release.ps1` 仍会打包并上传 onefile → 需去掉 onefile 的打包与上传。
- `scripts/release_gitee.py` 生成的 Gitee 正文仍带「单文件版请去 GitHub 下载」提示，并在 `--notes-only` 时也要求本地有 Setup.exe（Mac 上跑不了）。
- `scripts/release_gitee_dmg.py` 头部注释仍写「dmg 只发 GitHub」（已过时）；且只能传 dmg，Linux `.run` 暂无 Gitee 上传脚本。
- `scripts/release_macos.sh` / `release_linux.sh` / `.github/workflows/release-macos.yml` 只传 GitHub，Gitee 需另补。
- `docs/RELEASE_NOTES.md` 下载表仍有「Windows 单文件版」一行，下个版本起去掉。

> ⚠️ **双 remote 必须都推**：每次发版**代码和 Release 都要推两边**，否则国内用户（走 Gitee）拿不到新版。
> remote 名各机器不同：Windows 机叫 `github` / `gitee`；**Mac 上 GitHub 叫 `origin`**，Gitee 叫 `gitee`。
> 推之前先 `git fetch` 两边，确认 `git log --oneline <本地分支>..gitee/CommTool` 为空（Gitee 上没有本地缺的提交）再推。
> ```bash
> git push github CommTool && git push gitee CommTool     # Windows
> git push origin CommTool && git push gitee CommTool     # Mac
> ```

## 在线更新走哪个源（重要）

`src/updater.py` 的 `UPDATE_MANIFEST_URLS` 按顺序试，第一个成功的为准：

1. **Gitee raw**（`gitee.com/.../raw/CommTool/latest.json`）— 国内优先，秒回
2. **GitHub raw**（回退）— Gitee 抽风时兜底

`latest.json` 的 `url` 字段（Windows）**统一指向 Gitee Release 下载**（Gitee 全球可达）。
`url_mac` 在 Windows 发版阶段保持空数组；macOS 脚本上传并校验 `.dmg` 后，才写入 GitHub 直链（`.dmg` 也要补传 Gitee，但 `url_mac` 仍只填 GitHub；运行时 `mac_download_candidates` 仍兼容旧清单并把 GitHub 提前）。
`url_linux` 同样：Windows 发版保持空（或保留已校验的 GitHub `.run` 直链）；`release_linux.sh` 上传并校验后写入。`.run` 也要补传 Gitee（见「零」），`url_linux` 仍只填 GitHub。
每个平台还必须同时发布对应的 `sha256` / `size`、`sha256_mac` / `size_mac`、
`sha256_linux` / `size_linux`。三套发布脚本会调用
`scripts/update_manifest_integrity.py` 自动计算；缺失或无效摘要时客户端只打开人工下载页，绝不会自动运行安装包。
改源顺序/下载地址 = 改 `updater.py` + `latest.json` / `release.ps1`；改 `updater.py` **要重打包**。

> **`$Notes` 摘要建议**：以「串口调试助手 / 网络调试工具：…」开头写入 `latest.json` 的 `notes`（升级弹窗可见，也利于检索）。Release 正文仍用 `docs/RELEASE_NOTES.md` 全文，开头同样保留产品定位句。

---

## 一、各平台依赖

**Windows**
- PowerShell 7
- Python 3.11–3.13 + PyInstaller（发布固定 3.13；安装依赖时带 `-c constraints-runtime.txt`）
- Inno Setup 6
- GitHub CLI（`gh`，需先 `gh auth login`）

**macOS**
- Python 3.13 + PyInstaller + Pillow（发布脚本使用版本匹配的 `.venv` / `.venv-macos`）
- 系统自带 `iconutil` / `sips` / `hdiutil`
- GitHub CLI（`gh`，可选；没登录则脚本自动建 tag + 给手动上传步骤）

---

## 二、标准双平台发版（推荐顺序）

> **先 Windows 后 macOS**。原因：`latest.json` 由 Windows 脚本统一维护。
> macOS 端往同一个 Release 追加 `.dmg`，上传并校验后回写 `latest.json` 的 Mac URL、SHA-256 和大小。

### 1. Windows 机器上
```powershell
.\scripts\release.ps1 1.1.2 "本次更新说明"
```
自动完成：改版本号 → 改 `latest.json`(url 指 Gitee) → 打包 folder 安装包 + onefile →
git 提交 → push github + gitee → 建 GitHub Release(`--latest`，传两个 exe；onefile 待去掉，见「零」) →
发 Gitee Release(调 `release_gitee.py`，国内下载源)。
**只剩三语用户文档要手动补**(脚本结尾会提醒)：`docs/USAGE.md` · `使用说明.md` · `使用說明.md`
各加版本历史章节 + 目录条目 + 右下角「当前版本号」。macOS `.dmg` 仍由协作者补(见下方第 2 步)。

### 2. macOS（二选一打包，然后补 Gitee）

**(a) 云端打包（不需要 Mac）**：GitHub Actions → `Release macOS DMG`（`.github/workflows/release-macos.yml`）→ Run workflow（`CommTool` 分支）。
版本号取分支上的 `src/version.py`；在 `macos-14` runner 上打 dmg，挂到已有的 `comm-v<版本>` GitHub Release（已有同名 dmg 则跳过），
并在 `docs/RELEASE_NOTES.md` 已列出该 dmg 时用它同步 GitHub 正文。
`latest.json` 的 `url_mac` / `sha256_mac` / `size_mac` 仍需人工提交回写。

**(b) Mac 本机打包**：
```bash
git pull
bash scripts/release_macos.sh 1.1.2
```
自动完成：版本号对齐 → 打包 `.dmg` → 把 `.dmg` 上传到**同一个** GitHub Release `comm-v1.1.2`。

**然后在 Mac 上补传 Gitee**（两种打包方式都要做）：
```bash
# (a) 云端打包时 dist/ 里没有 dmg，先从 GitHub 下载，并核对 sha256 与 latest.json 的 sha256_mac 一致
gh release download comm-v<版本> --repo heropml/SerialTool --pattern 'CommTool_v<版本>.dmg' --dir dist --clobber
shasum -a 256 dist/CommTool_v<版本>.dmg
# 只追加 / 替换 dmg，不动 Setup.exe
GITEE_TOKEN="$(cat ~/doc/token/gitee_token.txt)" python3 scripts/release_gitee_dmg.py <版本>
```
Gitee 正文也要同步成「均已发布」的最新文案（同 `release_gitee.py --notes-only` 的效果，见「零」的待对齐项）。

完成后该 Release 同时挂着 `.exe` 和 `.dmg`，`latest.json` 也已是新版，
两平台用户在 app 内「帮助 → 关于 → 检查更新」都能收到提示：
- Windows：下载 `.exe` 自动安装
- macOS：打开该 Release 页，手动下载 `.dmg` 拖拽替换

---

## 三、只发单平台时的注意事项 ⚠️

`latest.json` 是 **Win/Mac 共用**的，它的 `version` 决定两个平台的「有新版」提示，
`url` 指向 Windows 的 `.exe`。因此：

- **只发 macOS 时**：应先确认 Windows 同版本已发布；Mac 脚本在资产校验后会更新 `latest.json` 的平台字段。
  若此时手动把 `latest.json` 版本号改新，Windows 用户会被导向**还不存在**的 `.exe`。
  所以：要么等 Windows 同版本也发布后再改 `latest.json`，要么本次先不通知用户
  （Release 里有 `.dmg`，知道的人可自取）。
- **只发 Windows 时**：`release.ps1` 会正常更新 `latest.json`，Windows 用户照常升级；
  macOS 用户检查更新时尚无本版本 `.dmg` 下载地址，需等待补包——
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
| Linux 包名 | `CommTool_Setup_v<版本>_linux_x86_64.run` |
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
>
> **Mac 上**不放 `scripts/.gitee_token`，令牌在 `~/doc/token/gitee_token.txt`，运行时经环境变量传入：
> `GITEE_TOKEN="$(cat ~/doc/token/gitee_token.txt)" python3 scripts/<脚本>.py`

### 6.1 推代码到 Gitee
```bash
git push gitee CommTool       # 走 SSH，免令牌
```

### 6.2 发 Gitee Release（一键脚本）
前置：`installer/CommTool_Setup_v<版本>.exe` 已打好（只在 Windows 机上跑；Mac 补 dmg 用 `release_gitee_dmg.py`）。
```bash
py -3 scripts/release_gitee.py            # 版本号自动从 src/version.py 读
py -3 scripts/release_gitee.py 1.1.3      # 或指定版本号
```
脚本自动：读令牌 → 建/复用 Release `comm-v<版本>` → **删掉该版全部旧附件再传 Setup.exe**（Gitee 无 clobber，
改 bug 重传同版本也能直接跑；⚠️ 会连带删掉已补传的 dmg / .run，补传后只能用 `--notes-only`）→ 打印下载链接。中文 UTF-8、multipart 都已处理好。

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
- [ ] 打包：`build.bat` → ISCC（`MSYS_NO_PATHCONV=1`，`/DMyAppVersion=`）（v1.8.4 起不再打 onefile）
- [ ] `git push github CommTool`
- [ ] `git push gitee CommTool` ← **易漏**（走 SSH，见 6.0a）
- [ ] GitHub Release：`gh release create comm-v<版本> --target CommTool --latest CommTool_Setup_v<版本>.exe`
      （重传同版本用 `gh release upload comm-v<版本> --clobber <文件>`）
- [ ] Gitee Release：`py -3 scripts/release_gitee.py`（见 6.2）
- [ ] 验证两源 latest.json + Gitee 下载链接（见 6.3）
- [ ] macOS `.dmg`：GitHub（云端 workflow 或 `release_macos.sh`）+ **Gitee（`release_gitee_dmg.py`）**
- [ ] Linux `.run`：GitHub（`release_linux.sh`）+ **Gitee（手动补传）**
- [ ] `latest.json` 的 `url_mac` / `url_linux` + sha256 / size 回写并推两站
- [ ] 两站 Release 正文都同步成「均已发布」的最终文案
- [ ] 跑「九、两站一致性核对」

---

## 八、提交与发布文案规则（必须遵守）

每个版本的提交记录和 GitHub/Gitee Release 文案都要保留详细内容，不能只写一句摘要，也不能把历史版本的正文混进当前版本。

### 8.1 Git 提交

- 一个版本合并为一个最终发布提交，提交标题保持现有格式：
  `release: comm-v<版本> — <本版本功能摘要>`
- 提交正文必须详细，按功能分节说明本版本的功能、修复、兼容性、文档和测试；不要删除各项变更的具体描述。
- 正文末尾保留完整测试结果，例如：`全量测试：739 passed，3 skipped，285 subtests passed。`
- 发布前确认 `git log -1 --format='%H%n%B'` 能看到标题和完整正文；不要用只有标题的提交覆盖详细提交。
- `docs/TODO.md` 已 gitignore，不入库；发版脚本仍会 `git reset -- docs/TODO.md` 以防万一。

### 8.2 GitHub/Gitee Release

- GitHub 和 Gitee 使用同一个 tag：`comm-v<版本>`，标题只出现一次：`CommTool v<版本>`。
- 当前 Release 文案只写当前版本（例如 v1.3.6）；v1.3.5 等历史版本必须留在各自的 Release，不能追加到 v1.3.6 的正文中。
- Release 正文要保留完整的当前版本说明、分节内容、兼容性提示和下载表格；不能因为合并或整理而删掉底下各条具体文案。
- 发布前检查正文中不存在旧版本标题、旧版本下载文件名或“历史归档”段落。
- GitHub 与 Gitee 的正文格式和内容保持一致，资产名称、版本号与 tag 一致。

---

## 九、两站一致性核对（每次发完都跑）

Mac 上 GitHub remote 叫 `origin`，Windows 上叫 `github`，下面按 Mac 写。

```bash
# 1. 分支：两边的分支列表和各分支提交应完全相同；GitHub 上不应残留 claude/* 等临时分支
git fetch origin --prune && git fetch gitee --prune
git for-each-ref --format='%(refname:short) %(objectname:short)' refs/remotes/origin refs/remotes/gitee

# 2. 本版 Release 附件：两边都应是 Setup.exe + dmg + .run（Gitee 另有自动生成的源码包 zip / tar.gz）
gh release view comm-v<版本> --repo heropml/SerialTool --json assets -q '.assets[].name'
curl -s "https://gitee.com/api/v5/repos/heropml/SerialTool/releases/tags/comm-v<版本>?access_token=$(cat ~/doc/token/gitee_token.txt)" \
  | python3 -c 'import json,sys;[print(a["name"]) for a in json.load(sys.stdin)["assets"]]'

# 3. 两站 latest.json 一致且是新版本
diff <(curl -sL https://gitee.com/heropml/SerialTool/raw/CommTool/latest.json) \
     <(curl -sL https://raw.githubusercontent.com/heropml/SerialTool/CommTool/latest.json) && echo same
```

已知的历史差异（不用修）：Gitee 镜像从 `comm-v1.1.2` 起，更早的 Release 与 SerialTool `v1.0.x`、NetworkTool `net-v*` 只在 GitHub；
Gitee 上是附注 tag、GitHub 上是轻量 tag（哈希不同但指向同一提交），唯 `comm-v1.1.2`、`comm-v1.1.5` 两个老 tag 两边指向的提交不同。
