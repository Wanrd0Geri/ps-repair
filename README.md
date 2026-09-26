# ps-repair

在本机 Photoshop 里用新图层、蒙版和调整层修 AI 生成图的瑕疵，原图层和源文件不动，每处修复用导出对比验收。Claude 与 Codex 通用。

## 目录

```
SKILL.md              入口：规则与流程
references/           方法选择、检视与验收、已知失败、Higgsfield 桥接
scripts/psrun.py      用 osascript 驱动 PS 跑配方
scripts/compare.py    切块、放大、并排、区外 PSNR（走 ffmpeg）
recipes/              ExtendScript 配方，清单和参数见 CATALOG.md
tests/run_tests.py    在合成文档上逐个跑配方（会驱动 PS，别和 MCP 同时跑）
```

## 安装

```sh
ln -s ~/Documents/Codex/ps-repair ~/.claude/skills/ps-repair
ln -s ~/Documents/Codex/ps-repair ~/.codex/skills/ps-repair
```

## 前提

- macOS，Photoshop 2026（27.10.0 实测）；配方只在 8 位 RGB 文档上测过。
- 自动化权限：系统设置 → 隐私与安全性 → 自动化，允许运行 Claude 或 Codex 的应用控制 Photoshop；第一次运行会弹窗询问。
- python3 和 ffmpeg：切图、拼图、PSNR 都走 ffmpeg，不需要 PIL 或 ImageMagick。
- 可选：Higgsfield PS MCP（`higgsfield-use-photoshop`），有它时看图和导出优先走它。
- 生成式填充要 Adobe 账号里有生成积分。
