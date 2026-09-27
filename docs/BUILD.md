# 从源码构建

普通玩家请下载Release安装包，无需执行本页。

## 环境

- Windows x64，Python 3.12 x64，Windows PowerShell 5.1。
- 对应版本的游戏安装；构建严格校验原版DLL和14项资源的SHA256。
- 系统字体 Microsoft YaHei UI（粗体），以0.68比例绘制；字体文件不随源码分发。
- Capstone 5.0.9：由 requirements.txt 安装，用于校验补丁机器码。
- 自行准备可信且有权使用的64位解压DLL，必须导出 `OodleLZ_Decompress` 并兼容游戏压缩数据。使用 `--oodle` 指定完整路径。本项目不附带或自动下载此库；缺少该库不能完成源码构建，应使用现成Release。

## 完整命令

在源码根目录打开 PowerShell，替换游戏和解压库路径：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\build.py --game "D:\SteamLibrary\steamapps\common\Pro Cycling Manager 2026" --oodle "D:\Tools\oodle-data-shared.dll"
```

通常应先卸载游戏上的旧汉化。维护者如果持有经过验证的原版DLL备份，可额外传入 `--original-dll "D:\Backup\GameCyclingDLL_Master.original.dll"`。构建不会覆盖游戏文件。

构建会依次读取pak、提取所需资源、比对哈希、匹配译文源文哈希、生成字体、修改丹麦语列、生成DLL与独立pak，然后执行回读和完整性检查。产物位于 `build/payload`。不支持 Python `-O`，因为它会禁用用于完整性检查的断言。

可用磁盘空间建议预留数GB。`build`已存在时构建拒绝覆盖；将其改名保存后再重新运行。字体栅格化需要时间，终端完成后才算构建成功。

源码构建安装：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Install.ps1 -GamePath "D:\SteamLibrary\steamapps\common\Pro Cycling Manager 2026"
```

## 译文维护

编辑 `translations/zh-CN.json` 的 `zh`，保持 `idloc`、`strid`、`source_sha256`。其中只存翻译和原文哈希，不复制整份原版英文数据库。`\n`是游戏识别的换行，变量及链接标记不可丢失。两条赛事说明明确移除了显示为文字的`\t`；不能把其他格式检查一并关掉。

`resources.json`仅针对当前游戏版本；遇到新版本需要重新分析DLL补丁位置与资源结构，不能只更新哈希来绕过兼容检查。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

自动测试使用临时假游戏目录，不改真实游戏。CI只做无需游戏资源的源码和安装流程测试。实际构建与游戏画面仍由持有游戏的维护者在本机验证。
