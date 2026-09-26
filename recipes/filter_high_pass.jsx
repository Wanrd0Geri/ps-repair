// 配方：filter_high_pass
// 用途：高反差保留锐化：副本做高反差保留，混合模式叠加/柔光，只在选区里加清晰度（如主体边缘、招牌字）。
// 参数：
//   doc_id       int      默认=当前文档
//   radius       number   默认=2          0.1-1000 像素，越大越“粗”
//   blend        str      默认="overlay"  overlay/soft_light/hard_light/linear_light
//   opacity      number   默认=100
//   desaturate   bool     默认=true       先去色，避免锐化出彩边
//   selection    选区     默认=沿用当前选区；无选区=整层（蒙版全显）
//   layer_id / source / expand_px / feather_px / label   同 content_aware_fill
// 产出：图层「修_filter_high_pass_<label>」（高反差副本 + 混合模式 + 选区蒙版）；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py）
// 费用/限制：本地、不扣积分；过度锐化会放大 AI 伪纹理，先小半径低不透明度试。

function run(args) {
  var doc = getDoc(args);
  var r = Number(opt(args, 'radius', 2));
  if (!(r >= 0.1 && r <= 1000)) fail('BAD_ARG', 'radius 0.1-1000');
  var mode = blendMode(opt(args, 'blend', 'overlay'));
  var info = filterFlow(doc, args, 'filter_high_pass', r * 3, function (layer) {
    if (opt(args, 'desaturate', true)) layer.desaturate();
    layer.applyHighPass(r);
    layer.blendMode = mode;
    layer.opacity = Number(opt(args, 'opacity', 100));
  });
  var layer = findLayer(doc, info.id);
  var out = layerInfo(layer);
  out.used_selection = info.used_selection; out.filter_rect = info.filter_rect;
  return out;
}
