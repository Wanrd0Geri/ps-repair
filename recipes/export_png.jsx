// 配方：export_png
// 用途：把文档当前合成结果导出成 PNG（验收对比、交付预览）。
// 参数：
//   doc_id   int   默认=当前文档
//   path     str   必填   新路径，必须以 .png 结尾且文件不存在（永不覆盖）；缺目录会自动建
// 产出：一个 PNG 文件（不改文档；文档本身不会被“另存为”指向新文件）
// 验证：2026-09-25 PS 27.10.0 已验证，与 MCP 导出逐位一致（2026-09-25 复核）。结论：本配方用 doc.saveAs(PNGSaveOptions, asCopy=true,
//   Extension.LOWERCASE)，与 Higgsfield MCP document.export_png 同一调用；在 sRGB 与 Adobe RGB 文档上
//   解码后 RGBA 像素 MD5 完全相同（文件字节只差 XMP 元数据里的时间戳/ID）。在 duplicate（含合并副本）上
//   导出也与原文档像素相同。对照：Save for Web PNG-24 在 sRGB 文档上一致，但会把非 sRGB 文档转成 sRGB
//   （Adobe RGB 文档 PSNR 31 dB）；Export As/快速导出（exportDocumentAsFileTypePressed）报“命令‘快速导出文档’
//   当前不可用”；exportSelectionAsFileTypePressed 只导出选中图层（裁到图层边界），都不能用来验收。
//   FINDINGS 里的“44 dB 漂移”不是导出路径造成的：那次比较的合并副本含上一轮远山雾化修改
//   （差异外接框 x519–924, y648–952），同一路径导出的未改文档与源文件像素 MD5 相同。
// 费用/限制：本地、不扣积分；PNG 不嵌 ICC 配置文件（像素值原样写出）；16 位文档会写 16 位 PNG；
//   PS 默认不压缩 PNG，3488×1480 约 15 MB。

function run(args) {
  var doc = getDoc(args);
  var path = opt(args, 'path', '');
  if (!path) fail('BAD_ARG', 'path 必填（新路径）');
  if (!/\.png$/.test(path)) fail('BAD_ARG', 'path 必须以小写 .png 结尾：' + path);
  var f = new File(path);
  if (f.exists) fail('OUTPUT_EXISTS', '文件已存在，换个新路径：' + path);
  if (!f.parent.exists && !f.parent.create()) fail('DIR_CREATE_FAILED', f.parent.fsName);
  doc.saveAs(f, new PNGSaveOptions(), true, Extension.LOWERCASE);
  if (!new File(path).exists) fail('EXPORT_FAILED', '导出后没找到文件：' + path);
  return { path: f.fsName, doc_id: doc.id, width: num(doc.width), height: num(doc.height), bits: enumName(doc.bitsPerChannel) };
}
