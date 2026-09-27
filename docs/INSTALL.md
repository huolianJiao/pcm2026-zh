# 完整安装与恢复步骤

## 安装前

使用与发布说明匹配的 Windows Steam 版 PCM2026。保存进度，退出游戏；本补丁不修改存档。可以先自行备份存档。

如果用过旧汉化，先用旧汉化的卸载工具恢复原版。安装器遇到未知DLL、已有覆盖pak或游戏运行中会停止，不会强行替换。

## 安装

1. 在 Releases 的 Assets 中下载 `PCM26-ZH-v0.4.1-preview.zip`。`Source code`是开发源码，不是安装包。
2. 完整解压，确认有 `Install.cmd`、`Check.cmd`、`Uninstall.cmd`、`Install.ps1`、`Launcher.ps1` 和 `payload` 文件夹。
3. 双击 `Install.cmd`。自动发现一个游戏目录时确认；否则手动输入游戏根目录，不能选到 `PCM` 或 `Win64` 子目录。
4. 安装器先检查补丁哈希和游戏DLL版本，再把原版DLL备份到游戏根目录 `PCM26-ZH-Backup`。
5. 成功后启动游戏，选择 **Dansk（丹麦语）**。English 仍显示英文，这是预期行为。
6. 如语言未刷新，退出并重启游戏。双击 `Check.cmd` 验证文件是否与本包一致。

需要手动指定路径时，可在解压目录打开 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -GamePath "D:\SteamLibrary\steamapps\common\Pro Cycling Manager 2026" -PayloadPath .\payload
```

修改执行策略只作用于本次 PowerShell 进程，不更改系统永久设置。若遇到访问拒绝，关闭游戏后以管理员身份运行安装入口。

## 修改了什么

- 替换 `PCM\Binaries\Win64\GameCyclingDLL_Master.dll`，增加中文字形映射与宽度处理。
- 添加 `PCM\Content\Paks\pakchunk99-PCM2026ZH_P.pak`，覆盖两份语言数据库的丹麦语列及四档扩展字体。
- 原游戏pak保持不变。英语及其他非丹麦语LOC列与原版一致。
- 安装备份位于 `PCM26-ZH-Backup`，不要删除它。

## 失败回滚与中断恢复

v0.4.1安装器在修改游戏前校验原版备份、保存本次操作前的DLL／pak／状态，并将新文件暂存且校验。替换使用同盘临时文件与单文件原子替换；操作日志写在 `PCM26-ZH-Backup/pending.json`。

发生可捕获的写入错误时自动尝试恢复操作前状态；如果进程被结束或设备意外断电，下次操作会检测到未完成日志，停止安装，要求先运行 **Recover.cmd**。恢复会先核对当前文件与已知操作前／后哈希；遇到Steam更新或其他未知改动会停止，避免把新文件覆盖成旧版本。

恢复和卸载只需要安装脚本及游戏目录中的备份／状态，不需要原下载包的payload。请保留脚本；若只剩脚本，在PowerShell运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -GamePath "D:\SteamLibrary\steamapps\common\Pro Cycling Manager 2026" -Mode Recover
```

备份首次创建后不被覆盖；每次操作另有独立txn目录。原版备份损坏、游戏运行中、并发安装、路径指向符号链接／目录联接、空间不足时会拒绝操作。建议使用本地NTFS磁盘。

这不是对所有硬件故障的绝对保证：跨多个文件无法一次原子提交，断电、磁盘损坏、杀毒软件拦截或用户同时启动游戏仍可能要求手动恢复。日志与备份用于将这些情况变为可检测、可恢复的状态；恢复失败时不要删除备份。

## 卸载与升级

保存并退出游戏，双击同一安装包的 `Uninstall.cmd`。它会恢复经过哈希校验的原版DLL，将汉化pak移到备份目录，并保留备份。

升级补丁时：用旧版 Uninstall.cmd 卸载，再运行新版 Install.cmd。不要直接用新包覆盖旧包；当前安装器有意拒绝未知版本。

## Steam更新之后

如更新改变游戏文件，先停止使用旧补丁并等候新适配版本。若卸载提示文件发生变化，不要把旧DLL强行覆盖到新游戏：关闭游戏，把 `PCM\Content\Paks\pakchunk99-PCM2026ZH_P.pak` 移到游戏目录外，再在 Steam 中验证游戏文件完整性。Steam验证通常不会负责清理额外mod文件，所以覆盖pak应单独移出。

## 常见问题

| 提示或现象 | 处理 |
| --- | --- |
| Close PCM2026 first | 保存并彻底退出游戏后重试 |
| Unsupported / Existing mod | 版本不同或存在旧补丁；先恢复旧补丁，不要跳过检查 |
| Payload hash mismatch | 压缩包损坏或内容被修改；重新下载并完整解压 |
| Original backup missing | 不要猜测原文件；移出汉化pak后通过Steam恢复原版 |
| 选英语仍是英文 | 改选Dansk，汉化只挂丹麦语 |
| 有英文地名／提示 | 有明确未覆盖部分，见README；并非安装必然失败 |
| 空白、方框、错位、崩溃 | 记录游戏版本、分辨率、界面位置和截图；必要时卸载本预览版 |

## 当前本机旧工作区用户

此前研究阶段 release04 由旧脚本安装，没有新安装器的状态文件。若要在同一台机器改用公开安装包，先在旧工作区执行：

```powershell
& .\tools\manage_pcm2026_cjk.ps1 -Mode Restore -Stage pcm2026-release04
```

之后再运行新包 Install.cmd。本说明不会自动卸载你已经安装的测试版。
