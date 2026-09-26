# 配方目录（CATALOG）

本文件是配方参数的唯一来源，和 `recipes/*.jsx` 文件头保持一致。验证环境：Photoshop 2026（27.10.0，中文界面，macOS Apple Silicon），2026-09-25，`tests/run_tests.py` 在 800×600 合成文档上全部通过。

## 怎么调用

```
python3 scripts/psrun.py <配方名> --args '<json>' [--timeout 900] [--app "Adobe Photoshop 2026"]
python3 scripts/psrun.py --jsx <文件.jsx> [--args '<json>']    # 任意脚本；有 run(args) 就按配方跑，没有就整段 eval
python3 scripts/psrun.py --list                               # 列出配方（不碰 PS）
python3 scripts/psrun.py <配方名> --check                     # 只做语法检查（node），不碰 PS
python3 scripts/psrun.py --poll <结果文件> --timeout 600       # 继续等一次超时运行的结果
```

- stdout 只有一个 JSON：`{"ok":bool,"recipe":str,"data":{...},"error":str|null,"elapsed_ms":int,"history":[最近3条历史记录名]}`。退出码：0 成功；1 配方失败；2 用法/环境错误（未知配方、坏 JSON、PS 没开）。
- 错误文本形如 `错误: CODE: 说明 @line N (文件:行)`（“错误:”是 PS 本地化前缀），按 `CODE` 子串判断。失败时 error 末尾附拼好的脚本路径，便于排查。
- 超时：AppleEvent 默认等 120 s（`--ae-timeout`），超时报 -1712 时脚本仍在 PS 里跑，runner 转为轮询结果文件直到 `--timeout`（默认 900 s）。仍拿不到结果时返回 `TIMEOUT`，**结果未知，不要盲目重试有副作用的配方**，先 `inspect`。
- 同一时刻只让一个工具驱动 PS。psrun 之间用文件锁排队；发现 Higgsfield MCP 锁（`~/.higgsfield-adobe/photoshop.lock`，目录）时在 stderr 警告，不会删它。
- history 是 PS 本地化名称（中文），只用于人看，不要拿来匹配。

## 通用约定

**选区参数 `selection`**：`{"rect":[l,t,r,b]}`（像素，左上原点，right/bottom 不含）｜`{"polygon":[[x,y],...]}`｜`{"channel":"通道名"}`｜`"current"`（必须已有选区）｜`"all"`｜`"none"`。不传时的含义因配方而异，见表中“默认”。

**目标**：`doc_id` 缺省 = 当前文档（配方会把它设为当前文档）；`layer_id` 缺省 = 当前图层。自动化流程里**始终显式传 `doc_id` 和 `layer_id`**（像素组的 `layer_id` 是源图层，调整组的是新层插在哪层上方）。

**非破坏**：
- 像素类（内容识别、滤镜、ACR）：复制源图层 → 显式选中 RGB 复合通道 → 在副本上做 → 建蒙版只露选区（`expand_px` 外扩）→ 命名 `修_<配方>_<label>`（label 为空时 `修_<配方>`）。滤镜只在“选区外接框 + 余量”内计算，矩形外被蒙版挡住。
- 调整/填充类：调整层或填充层 + 选区蒙版，插在 `layer_id`（缺省当前图层）上方。
- 所有建层配方：无选区时建“全显”蒙版；`feather_px` 用蒙版属性羽化（可逆）；结束后**取消选区**，新图层成为当前图层。
- 保护：`mask_from_selection`、`mask_set`、`layer_ops`（select/info 除外）只改名字以“修_”开头的图层，否则报 `PROTECTED_LAYER`（确需时传 `allow_any_layer:true`）；`close_doc` 只关名字以“试做_”开头的文档，否则报 `PROTECTED_DOC`（确需时 `force:true`），永远不保存；导出/另存只写新路径，已存在报 `OUTPUT_EXISTS`。

**参数组缩写**（表里引用）：
- 〔像素组〕`selection`（默认=沿用当前选区，无选区=整层）、`layer_id`（源图层，缺省=当前图层，必须是普通像素层，否则 `SOURCE_NOT_PIXEL_LAYER`——建过调整层后当前图层就是调整层，所以请显式传背景层等像素层的 id）、`source`="layer"（"merged"=先盖印全部可见图层再做）、`expand_px`=0、`feather_px`=0、`label`=""。执行失败时会删掉本次建的半成品“修_”图层。
- 〔调整组〕`selection`（默认=沿用当前选区，无选区=全图）、`layer_id`（新层插在其上方）、`expand_px`=0、`feather_px`=0、`clip`=false（剪贴到下层）、`label`=""

参数写法：`名`* = 必填；`名`=值 = 默认值。

## tier1（必验证，本地不扣积分）

| 名称 | 用途 | 参数 | 产出 | 验证状态 | 费用/限制 |
|---|---|---|---|---|---|
| inspect | 只读：打开的文档、图层树（id/名/类型/蒙版/边界）、Alpha 通道、选区、最近 8 条历史 | `doc_id`；`max_layers`=300 | 无（指定非当前文档时看完切回） | 已验证 | 无副作用 |
| export_png | 导出当前合成为 PNG，验收/预览用 | `doc_id`；`path`*（.png，新路径，缺目录自动建） | PNG 文件 | 已验证；**与 MCP `document.export_png` 逐位一致**（见下） | 不嵌 ICC；PS 不压缩 PNG（3488×1480 约 15 MB）；打开后第一次导出可能近一分钟（实测 49 s，之后 2–4 s） |
| duplicate_doc | 复制文档做试做 | `doc_id`；`name`="试做_<原名>"（缺前缀自动补）；`merge`=false | 新文档（成为当前），返回 id | 已验证 | `merge:true` 会把所有可见图层烧进像素 |
| save_copy_psd | 另存带图层的 PSD 副本 | `doc_id`；`path`*（.psd，新路径） | PSD 文件（图层/蒙版/通道/ICC） | 已验证 | 文档不改指向；>30000 px 或 2 GB 需 PSB（未处理） |
| close_doc | 关闭试做文档，不保存 | `doc_id`*；`force`=false | 无 | 已验证（含不给 doc_id、非试做文档的拒绝） | 丢弃未保存修改 |
| select_rect | 矩形选区 | `doc_id`；`rect`*；`mode`="replace"（replace/add/subtract/intersect）；`feather`=0 | 选区，返回 bounds | 已验证 | 不抗锯齿 |
| select_polygon | 多边形选区 | `doc_id`；`points`*（≥3）；`mode`="replace"；`feather`=0；`anti_alias`=true | 选区 | 已验证 | — |
| select_modify | 改选区 | `doc_id`；`op`（feather/expand/contract/smooth/invert/deselect/all）+`px`；或 `ops`=[{op,px},...] | 选区 | 已验证 | expand/contract 单次 ≤500 px；羽化会让 bounds 外延 |
| selection_save_channel | 选区存成 Alpha 通道 | `doc_id`；`name`*；`overwrite`=false | Alpha 通道 | 已验证 | 同名报 `CHANNEL_EXISTS` |
| selection_load_channel | 从通道载入选区 | `doc_id`；`name`*；`mode`="replace"；`invert`=false | 选区 | 已验证 | — |
| select_sky | 选择 > 天空 | `doc_id` | 选区；`found`、`bounds` | 已验证（真实夜景 0,0,3486,356，e2e 复跑 0,0,3487,357；合成图 0,0,800,293） | 本机模型；软边，树梢/屋檐交界易错 |
| select_color_range | 色彩范围 | `doc_id`；`sample_rgb`（[r,g,b] 或多个）或 `preset`（highlights/midtones/shadows/reds/yellows/greens/cyans/blues/magentas/skin_tones）；`fuzziness`=40；`invert`=false；`within_selection`=false | 选区；`found`、`bounds`、Lab 范围 | 已验证（取样、多色、highlights、within_selection）；其余 preset 未逐个测 | RGB 由 PS 转 Lab；默认先取消选区 |
| select_subject | 选择 > 主体 | `doc_id`；`sample_all_layers`=false；`processing`="device"（cloud 未验证）；`layer_id`=最底层 | 选区；`found`、`bounds` | 已验证（device） | 必须带 null=文档引用，否则“没有这种元素” |
| content_aware_fill | 内容识别填充去小瑕疵 | `doc_id`；`selection`="current"（必须有）；`layer_id`；`source`="layer"；`grow_px`=0（填充前外扩）；`expand_px`=0；`feather_px`=0；`color_adaptation`=true；`label`="" | `修_content_aware_fill_<label>`（副本+蒙版）；返回 `fill_bounds` | 已验证 | 秒级；大结构会糊/重复，回即梦局部重绘 |
| fill_layer_solid | 纯色填充层 | `rgb`*；`opacity`=100；`blend`="normal"；〔调整组〕 | `修_fill_layer_solid_<label>` | 已验证 | — |
| adj_curves | 曲线调整层 | `points`=[[in,out],...]（复合）或 `channels`={rgb,red,green,blue}；缺 0/255 端点自动补；〔调整组〕 | `修_adj_curves_<label>`；返回曲线点 | 已验证（读回曲线点一致） | — |
| adj_levels | 色阶调整层 | `input_black`=0；`input_white`=255；`gamma`=1.0；`output_black`=0；`output_white`=255；`channel`="rgb"；〔调整组〕 | `修_adj_levels_<label>` | 已验证（读回一致） | 抬 `output_black` 可做灰雾 |
| adj_color_balance | 色彩平衡调整层 | `shadows`/`midtones`/`highlights`=[0,0,0]（青红/洋红绿/黄蓝，-100..100）；`preserve_luminosity`=true；〔调整组〕 | `修_adj_color_balance_<label>` | 已验证 | — |
| adj_hue_sat | 色相/饱和度调整层 | `hue`=0；`saturation`=0；`lightness`=0；`colorize`=false；〔调整组〕 | `修_adj_hue_sat_<label>` | 已验证（含 colorize） | 只调主通道 |
| adj_brightness_contrast | 亮度/对比度调整层 | `brightness`=0（-150..150）；`contrast`=0（-50..100）；`legacy`=false；〔调整组〕 | `修_adj_brightness_contrast_<label>` | 已验证 | — |
| filter_smart_blur | 特殊模糊（保边去碎噪） | `radius`=3；`threshold`=25；`quality`="high"；`mode`="normal"（edge_only/overlay_edge）；〔像素组〕 | `修_filter_smart_blur_<label>` | 已验证 | — |
| filter_surface_blur | 表面模糊（磨平色带/斑驳） | `radius`=5（1-100）；`threshold`=15（2-255）；〔像素组〕 | `修_filter_surface_blur_<label>` | 已验证 | 半径大时慢 |
| filter_gaussian_blur | 高斯模糊 | `radius`=2；〔像素组〕 | `修_filter_gaussian_blur_<label>` | 已验证 | — |
| filter_add_noise | 添加杂色（补颗粒） | `amount`=2；`distribution`="gaussian"；`monochromatic`=true；〔像素组〕 | `修_filter_add_noise_<label>` | 已验证 | 每次随机 |
| filter_high_pass | 高反差保留锐化 | `radius`=2；`blend`="overlay"；`opacity`=100；`desaturate`=true；〔像素组〕 | `修_filter_high_pass_<label>`（混合模式已设） | 已验证 | 会放大 AI 伪纹理 |
| mask_from_selection | 给“修_”图层按选区建/重建蒙版 | `layer_id`；`selection`="current"；`mode`="reveal"（hide）；`expand_px`=0；`feather_px`=0；`replace`=false；`allow_any_layer`=false | 该图层新蒙版 | 已验证（含 MASK_EXISTS、PROTECTED_LAYER） | 背景层不能加蒙版 |
| mask_set | 改蒙版属性 | `layer_id`；`feather_px`；`density`（0-100）；`enabled`；`invert`；`allow_any_layer`=false | 返回读回的蒙版状态（density 为 %） | 已验证（可逆，读回一致） | 图层须已有蒙版；invert 改蒙版像素 |
| layer_ops | 图层小操作 | `op`（rename/opacity/blend/visible/move/delete/select/info）；`layer_id`；`name`（自动补“修_”）；`value`；`mode`；`to`（top/bottom/above/below）+`ref_layer_id`；或 `ops` 列表；`allow_any_layer`=false | 改后图层信息 | 已验证（全部 op 与保护） | 不透明度按 0-255 存，30 读回 30.2 |
| place_image | 置入外部图片为嵌入智能对象并对位 | `path`*；`x`*、`y`*（左上角文档像素）；`width`、`height`（只给一个按比例；都不给=原图 1:1）；`layer_id`；`selection`=不用（全显蒙版）；`expand_px`=0；`feather_px`=0；`linked`=false；`label`="" | `修_place_image_<label>`；返回 `bounds`、`corners`、`native_size` | 已验证（1:1、缩放、选区蒙版、大图复原）；linked 未验证 | PS 会先把大图缩进画布，本配方按原始尺寸还原 |

## tier2（尽力）

| 名称 | 用途 | 参数 | 产出 | 验证状态 | 费用/限制 |
|---|---|---|---|---|---|
| filter_lens_blur | 旧版镜头模糊（Bokh） | `radius`=10（0-100）；`blade_curvature`=0；`rotation`=0；`iris`="hexagon"；`specular_brightness`=0；`specular_threshold`=255；`noise`=0；〔像素组〕 | `修_filter_lens_blur_<label>` | 已验证（区内变、区外不变）；形状参数未逐个测 | 无深度图，均匀模糊 |
| fill_layer_gradient | 渐变填充层（天空过渡、远景雾） | `from_rgb`*；`to_rgb`=from_rgb；`from_opacity`=100；`to_opacity`=0；`angle`=90；`type`="linear"（radial 未验证）；`scale`=100；`dither`=true；`opacity`=100；`blend`="normal"；〔调整组〕 | `修_fill_layer_gradient_<label>` | 已验证（linear） | 与图层对齐 |
| adj_selective_color | 可选颜色调整层 | `colors`*={reds/yellows/greens/cyans/blues/magentas/whites/neutrals/blacks: [c,m,y,k]}；`method`="relative"；〔调整组〕 | `修_adj_selective_color_<label>` | 已验证（读回一致） | — |
| adj_photo_filter | 照片滤镜调整层 | `rgb`=[236,138,0]；`density`=25；`preserve_luminosity`=true；〔调整组〕 | `修_adj_photo_filter_<label>` | 已验证（读回一致） | — |
| camera_raw | Camera Raw 滤镜（去朦胧/清晰度/曝光…） | `exposure`（-5..5）；`contrast`/`highlights`/`shadows`/`whites`/`blacks`/`texture`/`clarity`/`dehaze`/`vibrance`/`saturation`（-100..100），至少给一个；〔像素组〕 | `修_camera_raw_<label>` | 已验证（exposure ±1 方向正确，dehaze/clarity 生效）；其余键未逐个测 | 只在选区外接框+余量内算，全局类效果与整图略有差异 |
| generative_fill | 生成式填充（Firefly，云端） | `selection`="current"（必须有，越小越好）；`prompt`=""；`expand_px`=0；`layer_id`=背景层；`source`="layer"；`keep_src_visible`=false；`label`=""；`dry_run`=false；`to_top`=true | `修_genfill_src`（源副本，默认隐藏）+ `修_generative_fill_<label>`（带蒙版智能对象） | 已验证 2026-09-25：新路径（背景副本「修_genfill_src」上生成）在 3488×1480 实图 e2e 跑通，106 s，产出带蒙版智能对象，bounds = 选区四边各外扩 11 px，背景层不动；描述符最早来自 genfill_test2（229 s）；dry_run 已验证；tests 不跑它 | **扣 Adobe 生成积分**；1.5–4 分钟，用 `--timeout 900`；「修_genfill_src」插在源图层正上方并隐藏；产出层默认移到最顶层（`to_top`=true，移层逻辑同 layer_ops move，未单独实跑；`to_top:false` 则留在源图层正上方、会被上面的修复层盖住）；大结构会乱长东西 |

## 导出一致性结论（export_png）

- `doc.saveAs(PNGSaveOptions, asCopy=true, Extension.LOWERCASE)` 与 Higgsfield MCP `document.export_png` 是同一调用；sRGB 与 Adobe RGB 文档上两者解码后 RGBA 像素 MD5 相同，文件字节只差 XMP 元数据。
- 在 `duplicate`（保留图层或合并）上导出，像素与原文档导出相同。
- Save for Web PNG-24：sRGB 文档一致；非 sRGB 文档会被转成 sRGB（Adobe RGB 文档 PSNR 31 dB）——不要用于验收。
- Export As / 快速导出（`exportDocumentAsFileTypePressed`）：报“命令‘快速导出文档’当前不可用”；`exportSelectionAsFileTypePressed` 只导出选中图层（裁到图层边界）——都不能用于验收。
- FINDINGS 里的“44 dB 漂移”是误判：那次对比的是 `duplicate(名, true)` 合并副本，把当时的远山雾化修改一起烧进了像素（差异外接框 x519–924, y648–952）；同一路径导出的未改文档与源 PNG 像素 MD5 相同。

## 实测坑（写配方/排错时注意）

- 一次 `set` 里放多个蒙版属性只生效一个（27.10.0）；`setMaskProps` 已逐个设置。
- 蒙版浓度读回是 0-255（设 50% 读回 128），`inspect`/`mask_set` 已换算成百分比。
- ExtendScript 访问不存在的枚举成员会直接抛“无效枚举值”（如 `BlendMode.SATURATIONBLEND` 不存在，应为 `SATURATION`）。
- 新建蒙版后 PS 把编辑目标切到蒙版，滤镜会作用在蒙版上；像素类配方在滤镜前显式选中 RGB 复合通道。
- `autoCutout`（选择主体）必须带 `null`=文档引用；本机处理用 choice override `imageProcessingSelectSubjectPrefs=imageProcessingModeDevice`。

## scripts/compare.py（验收用，ffmpeg 封装）

| 子命令 | 用途 | 示例 |
|---|---|---|
| tiles | 大图切 N 块（原尺寸） | `compare.py tiles a.png --grid 3x2 --out tiles/` |
| zoom | 裁切 + 最近邻放大 + 可选网格与原图坐标标注（定坐标用） | `compare.py zoom a.png --rect 3000,780,3160,940 --scale 4 --grid 10 --out z.png` |
| hstack | 前后并排对比（可先裁同一区域） | `compare.py hstack before.png after.png --rect 3000,780,3160,940 --scale 3 --out cmp.png` |
| psnr_outside | 修改区（可多个 `--rect`）之外的 PSNR，期望 inf | `compare.py psnr_outside before.png after.png --rect 3060,796,3140,926` |
| diffbox | 变化像素外接框（无变化为 null） | `compare.py diffbox before.png after.png` |

前后两张图要用同一条导出路径（`export_png` 或 MCP `document.export_png`）。
