# ps-repair

在本机 Photoshop 里用新图层、蒙版和调整层修 AI 生成图的瑕疵，原图层和源文件不动，每处修复用导出对比验收。Claude 与 Codex 通用。

## 目录

```
SKILL.md              入口：规则与流程
references/           方法选择、检视与验收、已知失败、Higgsfield 桥接
scripts/psrun.py      驱动 PS 跑配方（macOS: osascript；Windows: PowerShell COM）
scripts/compare.py    切块、放大、并排、区外 PSNR（走 ffmpeg）
recipes/              ExtendScript 配方，清单和参数见 CATALOG.md
tests/run_tests.py    在合成文档上逐个跑配方（会驱动 PS，别和 MCP 同时跑）；--syntax-only 只查语法和 ES3 写法，不碰 PS
```

## 安装

统一用 skills-setup 的安装脚本。手工装时：

```sh
ln -s ~/Documents/Codex/ps-repair ~/.claude/skills/ps-repair
ln -s ~/Documents/Codex/ps-repair ~/.codex/skills/ps-repair
```

Windows 用目录联接：`cmd /c mklink /J "%USERPROFILE%\.claude\skills\ps-repair" "%USERPROFILE%\Documents\Codex\ps-repair"`。

## 前提

- macOS 或 Windows 11，Photoshop 2026（27.10.0 两个系统都实测，27.11.0 在 Windows 上实测）；配方只在 8 位 RGB 文档上测过。
- Windows：无需装任何东西，用系统自带的 `powershell`（5.1 即可）走 COM；Photoshop 没开会自动启动。注册表里 `Photoshop.Application` 只指向最后安装的版本（常是 Beta），按它新建对象会拉起 Beta（K8），所以脚本只在运行对象表里找正在运行、安装目录对得上的目标版本；找不到报 `COM_UNAVAILABLE`，只有别的版本在跑报 `COM_MISMATCH`。
- macOS 自动化权限：系统设置 → 隐私与安全性 → 自动化，允许运行 Claude 或 Codex 的应用控制 Photoshop；第一次运行会弹窗询问。
- python3（Windows 上可用 `py -3`）和 ffmpeg：切图、拼图、PSNR 都走 ffmpeg，不需要 PIL 或 ImageMagick。ffmpeg 不在 PATH 上时设环境变量 `FFMPEG_DIR` 指向它所在目录。
- node（可选）：安装自检和 --check 的语法检查要它，没装时语法检查跳过。
- 可选：Higgsfield PS MCP（`higgsfield-use-photoshop`），有它时看图和导出优先走它。
- 生成式填充要 Adobe 账号里有生成积分。

## 参考

2026-10-10 的稳定性改进（探活、暂存盘检查、错误号、防重跑叠层、一步撤销、ES3 写法扫描）参考了 [alisaitteke/photoshop-mcp](https://github.com/alisaitteke/photoshop-mcp)（MIT）的思路，代码是自己写的，没有复制。暂存盘阈值取 Adobe 官方页面的数字。

## 待办（遇到对应镜头再做，做之前先定服务哪个镜头）

- 渐变画进蒙版：远景雾、景深由远到近渐变，替代分块镜头模糊的台阶（对应 K1）。只画在「修_」层、只画在选区内。
- 新调整层：自然饱和度（过饱和、发灰）、颜色查找 LUT（多镜头统一色调）、曝光、渐变映射。
- 椭圆选区：灯笼、光晕、球形高光。
- 频率分离：修颜色脏块而保留纹理；先实测 8 位下修改区外能不能逐位一致。
- 前后滑块验收网页：按缺陷编号拖动对比，点「通过 / 打回」。
- 自动选区合理性检查：`select_sky`、`select_color_range` 之后算覆盖率、是否贴边，异常先提醒。
- 小项：多个文档打开时写配方强制给 `doc_id`；选区外扩、收缩的 Action Manager 备用写法；生成式填充的备用描述符。
