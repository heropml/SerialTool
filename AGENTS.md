# CommTool（本仓库 `CommTool` 分支）

## 发版 / 打包 / 上传：动手前先读 [RELEASE.md](RELEASE.md) 的「零、上传规则速查」

要点（详情以 RELEASE.md 为准）：

- **GitHub 和 Gitee 两站保持一致**：分支、tag `comm-v<版本>`、Release 标题 / 正文、附件都要一样。
- 每个版本只发三个安装包：`CommTool_Setup_v<版本>.exe`、`CommTool_v<版本>.dmg`、`CommTool_Setup_v<版本>_linux_x86_64.run`。
  GitHub 三个都传；Gitee 传 Setup.exe + dmg。Linux `.run` 约 124MB，超过 Gitee 单文件 100MB 上限，只放 GitHub（Gitee 正文自动提示）。
  **自 v1.8.4 起不再发免安装单文件版** `CommTool_v<版本>.exe`（v1.8.3 是最后一个，只在 GitHub）。Gitee 历史上缺 dmg 是漏传，不是规则。
- `latest.json`：`url` 指 Gitee 的 Setup.exe；`url_mac` / `url_linux` 只填 GitHub 直链。
- 顺序：先 Windows（`release.ps1` 建两站 Release），再往同一个 Release 追加 dmg / .run
  （`release_macos.sh` / `release_linux.sh` 会自动补传 Gitee 并同步两站正文；手动补用 `release_gitee_asset.py`）。
- Gitee 附件配额 1GB，不自动清理旧版，满了再人工处理。
- remote 名：Windows 机 `github` / `gitee`；Mac 上 GitHub 叫 `origin`。推 Gitee 前先 fetch，确认 Gitee 上没有本地缺的提交。
- 发完跑 RELEASE.md「九、两站一致性核对」；GitHub 上别残留 `claude/*` 临时分支（PR 合并后删掉）。
