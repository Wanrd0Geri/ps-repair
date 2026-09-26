// 配方：filter_smart_blur
// 用途：特殊模糊（保边平滑）：抹 AI 图里的细碎噪点、脏纹理，同时保留明显边缘。
// 参数：
//   doc_id       int      默认=当前文档
//   radius       number   默认=3      0.1-100
//   threshold    number   默认=25     0.1-100，越小越保边
//   quality      str      默认="high"   low/medium/high
//   mode         str      默认="normal" normal/edge_only/overlay_edge
//   selection    选区     默认=沿用当前选区；无选区=整层（蒙版全显）
//   layer_id / source / expand_px / feather_px / label   同 content_aware_fill
// 产出：图层「修_filter_smart_blur_<label>」= 源图层副本（滤镜后）+ 选区蒙版；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分；滤镜只在“蒙版外接框 + 余量”内计算，大图也快。

function run(args) {
  var doc = getDoc(args);
  var r = Number(opt(args, 'radius', 3)), t = Number(opt(args, 'threshold', 25));
  var q = { low: 'LOW', medium: 'MEDIUM', high: 'HIGH' }[opt(args, 'quality', 'high')];
  var m = { normal: 'NORMAL', edge_only: 'EDGEONLY', overlay_edge: 'OVERLAYEDGE' }[opt(args, 'mode', 'normal')];
  if (!q || !m) fail('BAD_ARG', 'quality 或 mode 取值不对');
  return filterFlow(doc, args, 'filter_smart_blur', r * 3, function (layer) {
    layer.applySmartBlur(r, t, SmartBlurQuality[q], SmartBlurMode[m]);
  });
}
