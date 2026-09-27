# 发布源码与玩家安装包

脚本提供打包和草稿上传能力。许可范围与已知分发风险见[风险核查](RIGHTS_REVIEW.md)，技术检查不代表官方授权。

## 第一次上传源码

在GitHub新建空仓库，例如 `pcm2026-zh`，然后在本项目根目录执行（替换OWNER）：

```powershell
git init -b main
git add .
git status --short
git commit -m "Initial PCM2026 Chinese localization project"
git remote add origin https://github.com/OWNER/pcm2026-zh.git
git push -u origin main
```

只上传本项目目录，不要上传外层研究工作区。`.gitignore`排除build、原版与修改后的游戏二进制、纹理、压缩包和备份。原创代码采用MIT；资源与译文权利范围见THIRD_PARTY.md。

## 一条命令生成安装包

完成本地构建和验证后：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\New-Release.ps1 -Version v0.4.2-preview
```

得到 `build/releases/PCM26-ZH-v0.4.2-preview.zip` 和同名 `.zip.sha256`。ZIP内包含用户直接运行的安装器、校验器、卸载器和补丁payload，不包含原版DLL备份、存档、解压库或Python。

发布前检查压缩包及真实安装流程（最后两项参数使用维护者本机的原版DLL和已提取的PCM/Content目录）：

```powershell
.\.venv\Scripts\python.exe tools\verify_release.py build\releases\PCM26-ZH-v0.4.2-preview.zip --original-dll "D:\Backup\GameCyclingDLL_Master.original.dll" --assets "D:\Extracted\PCM\Content"
```

该工具会检查ZIP、脚本与源码一致性、pak内容、两份数据库非目标语言列，并在临时目录执行真实payload安装和卸载，不操作正式游戏目录。

发布者也可复用已经核验的payload目录，无需重新绘制字体：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\New-Release.ps1 -Version v0.4.2-preview -PayloadPath "D:\Prepared\pcm2026-release04"
```

Payload需要 manifest.json、GameCyclingDLL_Master.dll 和 manifest指定的pak。打包脚本校验哈希且不覆盖同名已生成版本。再次发布前更新版本号、CHANGELOG.md与docs/RELEASE_NOTES.md。

## 发布到 GitHub

先把本次源码提交并推送，再创建相同版本的tag：

```powershell
git tag v0.4.2-preview
git push origin v0.4.2-preview
```

有GitHub CLI时，先运行 `gh auth login`，然后：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Publish-Release.ps1 -Repository OWNER/pcm2026-zh -Version v0.4.2-preview
```

该脚本验证ZIP校验和，上传ZIP及校验文件，创建 **Draft Release**；带后缀的版本会标为Pre-release。它要求远端tag已存在，不会自动创建tag或直接公开发布。打开GitHub草稿核对说明和附件，再点击Publish release。

不安装CLI也可以：GitHub仓库 → Releases → Draft a new release → 选择已推送tag → 粘贴docs/RELEASE_NOTES.md → 上传ZIP和SHA256 → 勾选预发布 → 发布。

不要把300MB级的未压缩pak提交到Git历史；用户安装包作为Release附件管理。[GitHub大文件说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)；[gh release create参数](https://cli.github.com/manual/gh_release_create)。

## 发布核对

- 自动测试通过；本机构建的资源哈希、非目标语言列、字库和pak回读通过。
- 在目标游戏版本实测丹麦语中文、英语原文、设置、经理模式、新闻、比赛HUD及卸载恢复。
- 未完成上述实测的版本保留preview标记，并如实列出缺口。
- 安装包中修改后的游戏资源不属于MIT原创代码；不把游戏资源、字体或第三方库标注为本项目原创。
