---
name: ps-repair
description: 在本机 Photoshop 里修 AI 生成图的瑕疵，全程只加图层、不动原图层。用于：去杂物、去无意义物件、材质融化与结构错乱、远景景深或雾不对、色偏与明暗、假纹理与颗粒、接缝；把即梦局部重绘的结果合回图层；给 PS 里打开的图做可编辑的修复与调色；内容识别填充、生成式填充。不用于：写视频或图片提示词（归 aigc-video、cinema-dna-21x9x3）、角色设计（character-design-pipeline）、分镜与导演方案（director-master）、纯术语解释。
---

# ps-repair：在 Photoshop 里修 AI 生成图

把 AI 图上的具体瑕疵在用户本机 PS 里修掉。每处修复是一个新图层、蒙版或调整层，关掉就回到原样；修前定验收标准，修后用导出对比证明只改了该改的地方。脚本路径相对本 skill 目录。

## 必须守住

1. **原图层不动，只加层。** 像素类操作先复制源图层再在副本上做，调色用调整层加蒙版，图层名 `修_<配方>_<标签>`；MCP 建的层也用 `layer.rename` 改成「修_」开头，配方才认。用户关掉任一层就能对照原样。
2. **只存新路径。** 不保存、不覆盖源文件和已开文档，PSD 副本与 PNG 都写新文件名。源文件是唯一的退路。
3. **先看后改。** 切块看全图，可疑处放大 2 倍，暗部临时提亮只用于看、不进文档。缩略图看不出融化和假纹理。
4. **每处缺陷先定「类型 → 方法 → 验收标准」再动手。** 标准写成看得见的结果，如「白框消失，木板横纹接上，无浅色涂抹」。没有标准就判断不了修好没有。
5. **代表性一处先在副本上试。** 用 `duplicate_doc` 建副本文档试（自动命名「试做_…」；用 MCP `document.duplicate` 就把 name 写成「试做_…」，否则 `close_doc` 拒关），看过对比再上正式文档，副本关掉不保存。填充类结果不可预知，试错不能留在用户文档里。生成式填充例外，见第 7 条。
6. **验收靠导出对比。** 改前改后从同一个文档、同一组可见图层导出（MCP `document.export_png` 和 `export_png` 配方都逐位一致，可互换）；裁切并排看修改区；修改区外 PSNR 必须是 inf（逐位相同）。改前图在动手前导，副本上试就从副本导；合并图层建的副本会把已有调整烧进像素（K7）。
7. **生成式填充先说代价。** 每次扣 Adobe 生成积分、要 2–4 分钟，先告诉用户，同意再跑；只用于小块，空提示词优先。直接在工作文档上跑一次，不建副本、不拷回：`generative_fill` 把源图层复制成「修_genfill_src」在上面生成，产出带蒙版的智能对象层，背景层不动。结果不满意就隐藏或删掉这个「修_」层；要再跑先告诉用户会再扣一次积分。成片材质融化、整段屋檐这类大结构先回即梦局部重绘：实测大区域会长出场景里没有的金属架。
8. **同一时刻只有一个执行者驱动 PS。** MCP 调用未返回或 `~/.higgsfield-adobe/photoshop.lock` 存在时不跑 psrun；多代理时只让一个碰 PS。两路同时下命令会留下半截操作。
9. **只修范围内的缺陷。** 用户点名的照修；让修整张图时，缺陷表就是范围；范围外看到的写进报告，用户同意再修。用户认可的地方不能被顺手改掉。
10. **产出不放桌面。** 落点按用户项目规则问清，源图在桌面也一样。桌面堆积的大头就是 AI 产出的副本。
11. **报告写三栏：修了什么 / 没修什么 / 为什么。** 没修的给出下一步路线，如回即梦局部重绘，剩下的问题才有去处。

## 流程

**0 连接与文档检查。** 有 Higgsfield MCP：`ps_status`，再用 `ps_do` 跑 `document.list`、`layer.list`，记下文档 ID、尺寸、图层；没有就 `python3 -X utf8 $HOME/Documents/Codex/ps-repair/scripts/psrun.py inspect`，看图导出用 `export_png` 配方。确认用户没在操作 PS、没有弹窗，问清产出落点。配方只在 8 位 RGB 文档上测过（sRGB 的，和没嵌配置文件、`inspect` 里 profile 为 null 的）；16 位、CMYK、Lab 或别的配置文件先在副本上试。

**1 检视与缺陷表。** 按 [inspection-and-verification.md](references/inspection-and-verification.md) 切块、放大、定坐标，再列表：

| 编号 | 位置坐标 | 类型 | 可见现象 | 方法 | 图层名 | 验收标准 |
|---|---|---|---|---|---|---|

坐标用原图像素 `x0,y0–x1,y1`。动手前看一眼 [known-failures.md](references/known-failures.md) 的同类案例。

**2 方法选择。** 查 [method-selection.md](references/method-selection.md)：每类缺陷的首选、备选、配方、验收要点，以及即梦局部重绘合回。透视错误和大块结构不在 PS 里硬修。

**3 执行。** MCP 有的操作优先用 MCP（看图、导出、选区、蒙版、图层），没有的走配方：

    python3 -X utf8 $HOME/Documents/Codex/ps-repair/scripts/psrun.py <配方> --args '{...}'

在 macOS 上它经 osascript 驱动 Photoshop，要求 PS 已打开；在 Windows 上经 PowerShell COM 驱动，PS 没开会自动启动 2026 正式版（Beta 只在显式 `--app "Adobe Photoshop (Beta)"` 时用）。Windows 的 PowerShell 5.1 会吃掉 `--args` 里的双引号：改成把 JSON 写进 UTF-8 文件，再传 `--args-file <文件>`（PowerShell 7.3+、Git Bash 直接用 `--args` 即可）。路径参数在两个系统上都写本机原生路径。

参数名以 `recipes/CATALOG.md` 为准，不自己编；MCP 操作先用 `ps_catalog` 查参数。每条配方都显式传 `doc_id` 和 `layer_id`（像素类是源图层，一般是背景层；调整类是新层插在哪层上方）：建过调整层后当前图层就是调整层，像素类配方不传 `layer_id` 会报 `SOURCE_NOT_PIXEL_LAYER`。配方自带保护：`mask_from_selection`、`mask_set`、`layer_ops` 只改「修_」图层（否则报 `PROTECTED_LAYER`），`close_doc` 只关「试做_」文档（否则报 `PROTECTED_DOC`）；报了先核对目标，不顺手加 `allow_any_layer`、`force`。先在副本跑代表性一处，过了验收再上正式文档。调用超时不重跑同一条写操作，先查图层和历史记录。

**4 验收。** 按 [inspection-and-verification.md](references/inspection-and-verification.md)：同一路径导出前后 → 裁切并排 → 修改区外 PSNR=inf → 沿边界放大 → 暗部提亮检查。不过就回第 2 步；同一方法两次不过就换方法或路线，不靠加羽化、加模糊去盖。

**5 交付。** `save_copy_psd`（或 MCP `document.save_copy`）存 PSD 副本、导出 PNG 到确认的落点；副本文档用 `close_doc` 关掉不保存（MCP 没有关闭操作）。中文报告三栏：修了什么（编号、图层名、对比图、区外 PSNR）/ 没修什么 / 为什么及建议路线。

## 轻量默认

一两处点名缺陷时，缺陷表只在回复里写几行，试做、验收、交付一轮完成。缺陷五处以上或用户要求时，才展开完整缺陷表并逐项回报。

## 需要深读时

Higgsfield 包里的 ps-deslop 讲场景修图方法和反例，运行时读 `ps_get_skill(name:"ps-deslop", reference:"references/<名>.md")`，只读不抄（无许可证）。该读哪几份、MCP 能做和不能做什么见 [higgsfield-bridge.md](references/higgsfield-bridge.md)。
