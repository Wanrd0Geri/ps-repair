# Higgsfield PS MCP 桥接

`higgsfield-use-photoshop`：npm `@higgsfield_org/photoshop-mcp` 0.1.2，装在 `~/.higgsfield/photoshop-mcp/`，经 macOS 自动化脚本驱动 PS。Codex 端没有它时，整套走 `scripts/psrun.py`。Windows 上不用装它：`psrun.py` 直接经 PowerShell 的 COM 自动化驱动 PS，整套走 psrun。

## 工具

| 工具 | 做什么 |
|---|---|
| `ps_status` | 桥接状态（忙不忙、上次调用结果是否不明），不证明 PS 连得上 |
| `ps_document_info` | 活动文档名和顶层图层 |
| `ps_catalog` | 78 个操作的清单；带 `operation` 返回确切参数表 |
| `ps_do` | 执行一个操作：`{operation, args}` |
| `ps_preview` | 把文档缩成 PNG 直接给模型看（最长边默认 1024，最多 2048） |
| `ps_guide` | 操作守则 |
| `ps_get_skill`、`ps_get_skill_asset` | 读包内 skill 文档；取包内素材的本地路径 |

## 优先用它做的

- **看图与导出：** `ps_preview` 找位置；逐位对比用 `document.export_png`（只写新路径，重名报 OUTPUT_EXISTS）。
- **存档：** `document.save_copy` 存 PSD 副本；`document.duplicate` 建副本文档（必须给 name，写成「试做_…」，`close_doc` 才肯关），新文档 ID 要重新查。
- **图层：** `layer.list/info/duplicate/rename/opacity/visibility/blend_mode/clipping_mask/translate/move/group/copy_to_document`。MCP 建的层用 `layer.rename` 改成「修_」开头，配方的蒙版和图层操作（`mask_from_selection`、`mask_set`、`layer_ops`）才认。
- **选区与蒙版：** `selection.rectangle/polygon/feather/modify/invert/deselect`、`path.create/select`；`mask.create`（reveal_all、hide_all、selection）、`mask.set`（开关、浓度、羽化，羽化事后可改）。
- **放置：** `document.place` 嵌入为智能对象，落在画布中心，要再平移对位。
- **简单调整和滤镜：** `adjustment.create` 只有亮度/对比度、色相/饱和度；滤镜有高斯模糊、中间值、动感模糊、添加杂色、高反差保留、USM 锐化等。添加杂色、中间值、动感模糊、USM 执行前会选中 RGB 通道；高斯模糊、高反差保留、锐化不会，图层已带蒙版时可能作用到蒙版上。所以先做滤镜、再建蒙版。

## 它没有、由配方补的

内容识别填充、生成式填充；选择天空、选择主体、色彩范围；曲线、色阶、色彩平衡、可选颜色、照片滤镜；纯色和渐变填充层；智能模糊、表面模糊、镜头模糊；Camera Raw；选区存进通道再读回；关闭文档（`close_doc`）。配方也没有的：修复画笔、修补、仿制图章（用邻近贴片代替）、径向模糊、翻转。MCP 的混合模式只有正常、正片叠底、滤色、叠加、柔光、差值，没有颜色、明度；要用就走 `layer_ops`（`op:"blend"`）。

## 调用规矩

- 先 `ps_catalog({operation:"<名>"})` 查参数再 `ps_do`；文档和图层 ID 从 `document.list`、`layer.list` 取，不猜。
- `batch.run` 只收 `steps`（最多 30 步），顶层不写 documentId；每步是 `{operation, args}`，documentId 写在各步的 args 里。步与步之间不能引用前一步返回的 ID，先查好 ID 再批。遇错就停，已完成的步不回滚。
- 同一时刻只能一个调用。锁是目录 `~/.higgsfield-adobe/photoshop.lock`，调用正常结束会自动删。单次调用约 55 秒超时；超时后锁保留、桥接拒绝后续调用。这时先在 PS 里核对图层和历史记录，确认没有脚本在跑再删锁、重启 MCP，不重放那次写操作。
- 长操作（生成式填充、大图上的慢滤镜）走 psrun，给足超时。psrun 和 MCP 不同时跑：锁目录存在就先等。
- 打开后第一次导出可能接近 55 秒（3488×1480 实测 49 秒，之后 2–4 秒），第一次导出走 `export_png` 配方，之后两条路径随便用。
- 环境变量 `ADOBE_MCP_READONLY=1` 时，写操作、导出、预览全部禁用。

## 读 ps-deslop

- 索引 `ps_get_skill(name:"ps-deslop")`；单份 `ps_get_skill(name:"ps-deslop", reference:"references/<名>.md")`。没有 MCP 时直接读本机 `~/.higgsfield/photoshop-mcp/node_modules/@higgsfield_org/photoshop-mcp/dist/skills/photoshop/ps-deslop/`。
- 最有用的几份：`surface-analysis.md`（动手前的空间分析：透视、遮挡、光源、反射、远近）、`method-selection.md`（分流顺序）、`masks.md`（蒙版边界、覆盖检查、白线诊断）、`surface-completion.md`（材质毛病分五类）、`failure-atlas.md`（被否决的结果，只当反例）、`quality-contract.md`（各项独立验收）、`nature.md`（树、地形、水）、`seedream-integration.md`（外部生成补丁的对位和单蒙版合回，对应即梦局部重绘合回）、`finish.md`（景深与最终调色）。
- 它的完整流程默认带镜头模糊、径向模糊和全局调色，还指定了委派用的模型，这些不是本 skill 的默认。读它是为了方法和反例，范围仍以用户要求为准。

## 许可证

该包 0.1.2 没有 LICENSE 文件，package.json 也没有 license 字段。ps-deslop 只在运行时读，不复制、不改写进本仓库；本 skill 里的方法是用自己的话写的总结。
