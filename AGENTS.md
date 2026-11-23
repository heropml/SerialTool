# CommTool（本仓库 `CommTool` 分支）

## 发版 / 打包 / 上传：动手前先读 [RELEASE.md](RELEASE.md) 的「零、上传规则速查」

要点（详情以 RELEASE.md 为准）：

- **GitHub 和 Gitee 两站保持一致**：分支、tag `comm-v<版本>`、Release 标题 / 正文、附件都要一样。
- 每个版本只发三个安装包：`CommTool_Setup_v<版本>.exe`、`CommTool_v<版本>.dmg`、`CommTool_Setup_v<版本>_linux_x86_64.run`。
  GitHub 上传三个包。Gitee 上传 Setup.exe 和 dmg；Linux `.run` 在 Gitee 单文件限制内时同步上传，超限时由 Gitee 正文提示到 GitHub 下载。
  **自 v1.8.4 起不再发免安装单文件版** `CommTool_v<版本>.exe`（v1.8.3 是最后一个，只在 GitHub）。Gitee 历史上缺 dmg 是漏传，不是规则。
- `latest.json`：`url` 指 Gitee 的 Setup.exe；`url_mac` / `url_linux` 只填 GitHub 直链。
- 顺序：先 Windows（`release.ps1` 建两站 Release），再往同一个 Release 追加 dmg / .run
  （`release_macos.sh` / `release_linux.sh` 会自动补传 Gitee 并同步两站正文；手动补用 `release_gitee_asset.py`）。
- 发版时，简体中文、繁体中文和英文使用说明的目录与版本更新正文都只保留最近 5 个正式版本，也就是当前版本加前四版。新增一版时同步移除超出范围的目录条目和正文，较早的历史统一链接到 GitHub Releases。
- Gitee 附件配额不足时，先核对已有附件的实际大小和本次需要的空间，列出能满足要求的旧版本，由用户明确指定要清理的版本。
- 清理以完整版本为单位。先归档 GitHub 和 Gitee 上对应的发布说明、全部安装附件及 `comm-v<版本>` 标签，并校验归档。再同步删除用户确认版本在两站的 Release、全部附件和标签，核对两站结果后继续发布。不要只删除某一站或某个平台的附件来腾空间。
- remote 名：Windows 机 `github` / `gitee`；Mac 上 GitHub 叫 `origin`。推 Gitee 前先 fetch，确认 Gitee 上没有本地缺的提交。
- 发完跑 RELEASE.md「九、两站一致性核对」；GitHub 上别残留 `claude/*` 临时分支（PR 合并后删掉）。
